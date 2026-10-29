"""从项目根目录执行 python -m app.main。"""

import sys
import argparse

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.config import ConfigStore
from app.core.logging_setup import install_exception_hook, setup_logging
from app.ui.main_window import MainWindow
from app.services.disk_inventory import DiskInventoryService


def main() -> int:
    parser = argparse.ArgumentParser(description="CrossDisk Manager")
    parser.add_argument("--demo", action="store_true", help="仅使用任务 02 的模拟数据")
    args = parser.parse_args()
    application = QApplication(sys.argv)
    application.setApplicationName("CrossDisk Manager")
    try:
        logger = setup_logging()
    except OSError:
        QMessageBox.critical(None, "启动失败", "无法创建用户日志目录，请检查当前用户权限。")
        return 1
    install_exception_hook(logger)
    store = ConfigStore()
    try:
        config = store.load()
    except (OSError, ValueError, TypeError) as exc:
        logger.error("配置读取失败：%s", type(exc).__name__)
        QMessageBox.critical(None, "启动失败", "用户配置无法读取或不符合只读安全要求，请检查 config.json。")
        return 1
    scheme = {"system": Qt.ColorScheme.Unknown, "light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}
    application.styleHints().setColorScheme(scheme[config.theme])
    window = MainWindow(config, store, logger,
                        inventory_service=None if args.demo else DiskInventoryService())
    window.show()
    logger.info("应用启动，安全模式：只读")
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
