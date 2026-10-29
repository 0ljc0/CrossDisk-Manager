"""非模态导出队列，来源只读，目标只允许 Windows。"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget
from app.jobs.copy_worker import CopyWorker


class CopyDialog(QDialog):
    idle = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Windows 复制与导出队列")
        self.resize(780, 420)
        self.pending = []
        self.worker = None
        self.last_job = None
        self.stopping = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("仅新建目标，不覆盖；目录冲突跳过整个目录。时间戳和属性不保留。\n暂停/取消在读取块之间生效；已完成文件及已创建目录保留。"))
        self.rows = QListWidget()
        layout.addWidget(self.rows)
        self.status = QLabel("就绪；总字节为已发现文件量，遍历中会增加")
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        for text, callback in (("暂停/继续", self.pause), ("取消当前及等待任务", self.cancel), ("重试最后任务", self.retry)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)

    def enqueue(self, job):
        self.pending.append(job)
        self.rows.addItem("等待：" + job.source["relative_path"])
        self.show()
        self.start_next()

    def start_next(self):
        if self.worker or not self.pending:
            return
        self.last_job = self.pending.pop(0)
        self.worker = CopyWorker(self.last_job, self)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.finished_job)
        self.worker.start()

    def update_progress(self, value):
        self.status.setText(f"{value['state']} | 完成 {value['completed']} / 失败 {value['failed']} / 跳过 {value['skipped']}\n"
                            f"已传输 {value['bytes']} / 已发现 {value['total_bytes']} 字节；{value['message']}")

    def finished_job(self):
        result = self.worker.result or dict(state="失败")
        self.rows.addItem(result['state'] + "：" + self.last_job.source['relative_path'])
        self.worker.deleteLater()
        self.worker = None
        if self.stopping:
            self.hide()
        else:
            self.start_next()
        if not self.worker:
            self.idle.emit()

    def pause(self):
        if self.worker:
            flag = self.worker.pause_flag
            flag.clear() if flag.is_set() else flag.set()
            self.status.setText("继续请求已发送" if not flag.is_set() else "暂停请求已发送；等待当前读取完成")

    def cancel(self):
        self.pending.clear()
        if self.worker:
            self.worker.requestInterruption()

    def retry(self):
        if not self.worker and self.last_job:
            self.enqueue(self.last_job)

    def closeEvent(self, event):
        if self.worker:
            self.stopping = True
            self.cancel()
            event.ignore()
        else:
            event.accept()
