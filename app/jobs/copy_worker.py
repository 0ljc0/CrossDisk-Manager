"""串行复制队列：协作暂停/取消，不强杀写入线程。"""
import threading
from PySide6.QtCore import QThread, Signal
from app.services.copy_service import copy_job


class CopyWorker(QThread):
    progress = Signal(object)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job
        self.pause_flag = threading.Event()
        self.result = None

    def run(self):
        self.result = copy_job(self.job, self.progress.emit, self.isInterruptionRequested, self.pause_flag.is_set)
