"""本地去敏日志查看，仅读取固定应用日志的末尾，不打开任意文件。"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, QLabel
from app.core.config import user_data_dir


class LogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('本地应用日志')
        self.resize(850, 500)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('仅显示当前日志末尾 64 KiB；不上传日志。异常只记录类型，不记录文件内容。'))
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        refresh = QPushButton('刷新')
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        self.refresh()

    def refresh(self):
        try:
            with (user_data_dir() / 'logs/app.log').open('rb') as reader:
                reader.seek(0, 2)
                reader.seek(max(0, reader.tell() - 65536))
                self.text.setPlainText(reader.read(65536).decode('utf-8', errors='replace'))
        except OSError:
            self.text.setPlainText('日志尚未创建或当前用户无法读取。')
