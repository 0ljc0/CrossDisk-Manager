"""记录去敏后的异常类型，不记录文件内容、路径或异常消息。"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from app.core.config import user_data_dir


def setup_logging(directory: Path | None = None) -> logging.Logger:
    directory = directory if directory is not None else user_data_dir() / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("crossdisk_manager")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    handler = RotatingFileHandler(directory / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def install_exception_hook(logger: logging.Logger) -> None:
    def hook(kind: type[BaseException], value: BaseException, tb: TracebackType | None) -> None:
        logger.error("未处理异常：%s", kind.__name__)
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is not None:
            QMessageBox.critical(None, "程序错误", "发生未处理异常，请查看应用日志中的异常类型。")
    sys.excepthook = hook
