"""任务 01 最小窗口，不访问磁盘或分区。"""

import logging
from dataclasses import replace

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox
from PySide6.QtCore import Qt

from app.core.config import AppConfig, ConfigStore


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, store: ConfigStore, logger: logging.Logger) -> None:
        super().__init__()
        self.config = config
        self.store = store
        self.logger = logger
        self.setWindowTitle("CrossDisk Manager · 跨分区文件管理器")
        self.setMinimumSize(640, 480)
        self.resize(config.window_width, config.window_height)
        label = QLabel("CrossDisk Manager\n环境与项目骨架已就绪\n安全模式：只读")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(label)
        self.statusBar().showMessage("任务 01：尚未接入磁盘访问")

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self.store.save(replace(self.config, window_width=self.width(), window_height=self.height()))
        except OSError as exc:
            self.logger.error("配置保存失败：%s", type(exc).__name__)
            QMessageBox.warning(self, "配置保存失败", "无法保存窗口配置，本次设置不会保留。")
        self.logger.info("应用正常退出")
        event.accept()
