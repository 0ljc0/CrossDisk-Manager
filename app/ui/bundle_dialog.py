"""Independent ext4 staging panel; all source reads/export run off the UI thread."""
from copy import deepcopy
from pathlib import Path
import stat

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QComboBox, QTableWidget, QTableWidgetItem, QFileDialog,
    QInputDialog, QMessageBox)

from app.backends.offline_bundle import OfflineBundleBackend
from app.services.backend_access import open_backend

LABELS={"create_file":"待创建","replace_file":"待修改","delete_file":"待删除",
        "mkdir":"待创建目录","rename_file":"待重命名"}


class BundleWorker(QThread):
    result=Signal(object)

    def __init__(self,dialog,operation,arguments):
        super().__init__(dialog)
        self.dialog,self.operation,self.arguments=dialog,operation,arguments

    def run(self):
        owner=self.dialog
        try:
            # Reopen/revalidate the source for each command; no raw write API exists.
            with open_backend(owner.request) as reader:
                if owner.backend is None:
                    owner.backend=OfflineBundleBackend(reader,owner.root,workspace_parent=owner.workspace_parent)
                    owner.source_uuid=reader.probe["uuid"]
                if reader.probe["uuid"]!=owner.source_uuid:
                    raise ValueError("分区 UUID 已变化，请关闭暂存会话并重新扫描")
                owner.backend.reader=reader
                args=self.arguments
                value=None
                if self.operation in ("create_file","replace_file"):
                    source=Path(args["source"])
                    info=source.lstat()
                    if not stat.S_ISREG(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400:
                        raise ValueError("请选择普通本地文件，不支持链接或设备")
                    with source.open("rb") as stream:
                        if self.operation=="create_file":
                            owner.backend.create_file(args["path"],stream,args["metadata"])
                        else:owner.backend.replace_file(args["path"],stream)
                elif self.operation=="mkdir":owner.backend.create_directory(args["path"],args["metadata"])
                elif self.operation=="delete_file":owner.backend.delete_file(args["path"])
                elif self.operation=="rename_file":owner.backend.rename_file(args["path"],args["new_path"])
                elif self.operation=="cancel":owner.backend.cancel(args["id"])
                elif self.operation=="export":value=owner.backend.export_bundle(args["destination"])
                elif self.operation!="initialize":raise ValueError("未知暂存操作")
                operations=owner.backend.pending.operations()
                bundle_id=owner.backend.pending.manifest()["bundle_id"] if operations else None
                self.result.emit(dict(ok=True,operations=operations,bundle_id=bundle_id,value=value))
        except Exception as exc:
            self.result.emit(dict(ok=False,message=str(exc)))


class BundleDialog(QDialog):
    changed=Signal(object)
    closed=Signal()

    def __init__(self,request,root,workspace_parent,parent=None):
        super().__init__(parent)
        self.request=deepcopy(request)
        self.root=root
        self.workspace_parent=workspace_parent
        self.backend=None;self.worker=None;self.source_uuid=None
        self.operations=[];self.bundle_id=None;self.exported_id=None
        self.setWindowTitle("ext4 修改包 · 本地暂存")
        self.resize(880,560)
        layout=QVBoxLayout(self)
        self.notice=QLabel("这些操作仅保存在 Windows 修改包中，尚未修改 Ubuntu。\n暂存范围：/"+root)
        self.notice.setTextFormat(Qt.TextFormat.PlainText);self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.path=QLineEdit();self.path.setPlaceholderText("相对暂存范围的路径，例如 notes.txt")
        layout.addWidget(self.path)
        metadata=QHBoxLayout();layout.addLayout(metadata)
        self.uid=QSpinBox();self.uid.setRange(1,2147483647);self.uid.setValue(1000)
        self.gid=QSpinBox();self.gid.setRange(1,2147483647);self.gid.setValue(1000)
        self.mode=QComboBox();self.mode.addItems(["0644","0600","0640","0755","0700"])
        self.directory_mode=QComboBox();self.directory_mode.addItems(["0755","0700"])
        for text,widget in (("新建 UID",self.uid),("GID",self.gid),("文件权限",self.mode),("目录权限",self.directory_mode)):
            metadata.addWidget(QLabel(text));metadata.addWidget(widget)
        metadata.addStretch()
        self.buttons=[]
        actions=QHBoxLayout();layout.addLayout(actions)
        for text,op in (("从本地新建文件…","create_file"),("替换为本地文件…","replace_file"),
                        ("新建目录","mkdir"),("暂存删除","delete_file"),("暂存重命名…","rename_file")):
            button=QPushButton(text);button.clicked.connect(lambda checked=False,kind=op:self.action(kind))
            self.buttons.append(button);actions.addWidget(button)
        self.table=QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(["暂存状态","原路径","目标路径","内容大小"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.currentCellChanged.connect(self.select_pending)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        bottom=QHBoxLayout();layout.addLayout(bottom)
        cancel=QPushButton("取消选中操作");cancel.clicked.connect(self.cancel_selected)
        export=QPushButton("导出修改包…");export.clicked.connect(self.export)
        self.buttons.extend([cancel,export]);bottom.addWidget(cancel);bottom.addStretch();bottom.addWidget(export)
        self.status=QLabel("正在验证分区与暂存范围…")
        self.status.setTextFormat(Qt.TextFormat.PlainText);self.status.setWordWrap(True);layout.addWidget(self.status)

    def start(self,operation="initialize",**arguments):
        if self.worker:return
        self.path.setEnabled(False)
        for button in self.buttons:button.setEnabled(False)
        self.worker=BundleWorker(self,operation,arguments)
        self.worker.result.connect(self.ready)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def ready(self,result):
        if not result["ok"]:
            self.status.setText("未暂存："+result["message"])
            return
        self.operations=result["operations"];self.bundle_id=result["bundle_id"]
        if result["value"]:
            self.exported_id=self.bundle_id
            self.status.setText("修改包已导出至："+result["value"]["directory"]+"；尚未应用到 Ubuntu。")
        else:self.status.setText(f"待应用操作 {len(self.operations)} 项；尚未修改 Ubuntu。")
        self.notice.setText("仅本地暂存，Ubuntu 尚未修改。\n范围：/"+self.root+"\nUUID："+self.source_uuid)
        self.table.setRowCount(len(self.operations))
        for row,op in enumerate(self.operations):
            values=(LABELS[op["type"]],op["path"],op.get("new_path","—"),
                    str(op["payload"]["size"])+" B" if "payload" in op else "—")
            for column,value in enumerate(values):self.table.setItem(row,column,QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self.changed.emit(dict(root=self.root,operations=deepcopy(self.operations)))

    def worker_finished(self):
        self.worker.deleteLater();self.worker=None
        self.path.setEnabled(True)
        for button in self.buttons:button.setEnabled(self.backend is not None)

    def action(self,operation):
        if self.worker:return
        args=dict(path=self.path.text())
        if operation in ("create_file","replace_file"):
            source,_=QFileDialog.getOpenFileName(self,"选择要暂存的本地文件")
            if not source:return
            args["source"]=source
        if operation in ("create_file","mkdir"):
            mode=self.directory_mode if operation=="mkdir" else self.mode
            args["metadata"]=dict(uid=self.uid.value(),gid=self.gid.value(),mode=int(mode.currentText(),8))
        if operation=="rename_file":
            target,ok=QInputDialog.getText(self,"同目录重命名","目标相对暂存根目录的完整路径（不覆盖）：")
            if not ok:return
            args["new_path"]=target
        if operation=="delete_file" and QMessageBox.question(self,"暂存删除", "将该文件加入待删除列表？实际删除将在 Ubuntu 应用时执行。")!=QMessageBox.StandardButton.Yes:return
        self.start(operation,**args)

    def cancel_selected(self):
        row=self.table.currentRow()
        if not self.worker and 0<=row<len(self.operations):self.start("cancel",id=self.operations[row]["id"])

    def select_pending(self,row,column,previous_row,previous_column):
        if not self.worker and 0<=row<len(self.operations):self.path.setText(self.operations[row]["path"])

    def export(self):
        if self.worker:return
        if not self.operations:
            self.status.setText("没有待导出的操作。")
            return
        parent=QFileDialog.getExistingDirectory(self,"选择导出父目录")
        if not parent:return
        name,ok=QInputDialog.getText(self,"修改包目录名","输入尚不存在的新目录名：",text="CrossDisk_Bundle_"+self.bundle_id[:8])
        if not ok:return
        if not name or Path(name).name!=name or "/" in name or "\\" in name or name in (".",".."):
            self.status.setText("请输入单个普通目录名。")
            return
        self.start("export",destination=str(Path(parent)/name))

    def closeEvent(self,event):
        if self.worker:
            self.status.setText("正在读取或导出，请等待完成后关闭。")
            event.ignore();return
        if self.operations and self.bundle_id!=self.exported_id:
            if QMessageBox.question(self,"未导出的暂存操作","关闭将丢弃尚未导出的暂存操作，是否关闭？")!=QMessageBox.StandardButton.Yes:
                event.ignore();return
        try:
            if self.backend:self.backend.close()
        except (OSError,ValueError) as exc:
            self.status.setText("工作目录清理失败，已保留："+str(exc));event.ignore();return
        self.closed.emit();event.accept()
