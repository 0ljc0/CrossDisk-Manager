"""独立的 Windows 数据目录编辑窗口，磁盘操作全部在线程执行。"""
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPlainTextEdit,
    QLabel, QPushButton, QMessageBox, QInputDialog)
from app.backends.windows_native import readable_error


class WriteWorker(QThread):
    result = Signal(object)

    def __init__(self, backend, operation, path, arguments, parent=None):
        super().__init__(parent)
        self.arguments = backend, operation, path, arguments

    def run(self):
        backend, operation, path, arguments = self.arguments
        try:
            value = backend._write(operation, path, **arguments)
            self.result.emit(dict(ok=True, value=value, operation=operation, path=path))
        except Exception as exc:
            self.result.emit(dict(ok=False, message=readable_error(exc)))


class WriteDialog(QDialog):
    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.worker = None
        self.version = None
        self.loaded_path = None
        self.setWindowTitle("Windows 受控写入与 UTF-8 编辑")
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("仅操作配置目录内子项：" + backend.write_context.scope + "\n不提供自动撤销；保存保留同目录 .bak 备份。"))
        self.path = QLineEdit()
        self.path.setPlaceholderText("相对配置目录的文件或目录路径，例如 notes/sample.txt")
        layout.addWidget(self.path)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        self.buttons = []
        for text, operation in (("新建目录", 'create_dir'), ("新建空文件", 'create_file'), ("打开文本", 'read_text'),
            ("保存", 'write_file'), ("重命名", 'rename'), ("同卷移动", 'move'), ("回收站", 'delete'), ("永久删除", 'permanent')):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, op=operation: self.action(op))
            buttons.addWidget(button)
            self.buttons.append(button)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        self.status = QLabel("先新建文件或打开不超过 2 MiB 的 UTF-8 文本。永久删除仅支持文件/空目录。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def action(self, operation):
        if self.worker:
            return
        scope = self.backend.write_context.scope
        path = scope + '/' + self.path.text()
        arguments = {}
        if operation == 'write_file':
            if self.version is None or path != self.loaded_path:
                self.status.setText("请先打开当前文件，保存必须携带原版本")
                return
            arguments = dict(data=self.text.toPlainText().encode('utf-8'), version=self.version)
        if operation in ('rename', 'move'):
            target, ok = QInputDialog.getText(self, '目标（不覆盖）', '目标相对配置目录的完整路径：')
            if not ok:
                return
            arguments['target'] = scope + '/' + target
        if operation != 'read_text':
            label = {'create_dir': '新建目录', 'create_file': '新建空文件', 'write_file': '保存文本并备份',
                     'rename': '重命名', 'move': '移动', 'delete': '移至回收站', 'permanent': '永久删除'}[operation]
            if QMessageBox.question(self, '确认操作', f'{label}：{path}\n继续？') != QMessageBox.StandardButton.Yes:
                return
        if operation == 'permanent':
            if QMessageBox.warning(self, '二次确认：不可恢复', '此操作绕过回收站，不能撤销。确定永久删除？',
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            operation, arguments = 'delete', dict(permanent=True, confirmed=True)
        if operation == 'read_text' and self.text.document().isModified():
            if QMessageBox.question(self, '未保存内容', '放弃当前未保存编辑并打开文件？') != QMessageBox.StandardButton.Yes:
                return
        self.worker = WriteWorker(self.backend, operation, path, arguments, self)
        self.worker.result.connect(self.ready)
        self.worker.finished.connect(self.worker_finished)
        for button in self.buttons:
            button.setEnabled(False)
        self.path.setEnabled(False)
        self.text.setReadOnly(True)
        self.status.setText("正在后台复核磁盘身份与权限并执行操作…")
        self.worker.start()

    def ready(self, result):
        if not result['ok']:
            self.status.setText(result['message'])
            return
        value = result['value']
        if result['operation'] == 'read_text':
            self.text.setPlainText(value['text'])
            self.version, self.loaded_path = value['version'], result['path']
            self.text.document().setModified(False)
        elif result['operation'] == 'write_file':
            self.version = value['version']
            self.text.document().setModified(False)
        elif (result['operation'] in ('rename', 'move', 'delete') and self.loaded_path and
              (self.loaded_path.casefold() == result['path'].casefold() or
               self.loaded_path.casefold().startswith(result['path'].casefold().rstrip('/') + '/'))):
            self.version = None
            self.loaded_path = None
        self.status.setText(value.get('message', '文本已打开；保存时检查版本并保留备份'))

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.path.setEnabled(True)
        self.text.setReadOnly(self.version is None)
        for button in self.buttons:
            button.setEnabled(True)

    def closeEvent(self, event):
        if self.worker:
            self.status.setText("写入进行中，请等待完成后关闭")
            event.ignore()
        elif self.text.document().isModified() and QMessageBox.question(self, '未保存编辑', '放弃未保存编辑并关闭？') != QMessageBox.StandardButton.Yes:
            event.ignore()
        else:
            event.accept()
