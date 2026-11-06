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
    parser.add_argument("--smoke-test", action="store_true", help="只读启动自检，自动退出")
    parser.add_argument("--bundle-smoke", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.bundle_smoke and (not args.smoke_test or args.demo):
        parser.error("--bundle-smoke requires --smoke-test without --demo")
    application = QApplication(sys.argv)
    application.setApplicationName("CrossDisk Manager")
    if args.bundle_smoke:
        from app.ui.bundle_smoke import run
        return run(application,args.bundle_smoke)
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
    if args.smoke_test:
        from PySide6.QtCore import QTimer
        import time
        started = time.monotonic()
        smoke = {'navigated': False}
        def finish_smoke():
            if args.demo:
                window.close()
                application.exit(0)
            elif window.inventory is not None and window.worker is None:
                if not smoke['navigated']:
                    from app.core.runtime import runtime_directory
                    try:
                        location = window.source.resolve_address(str(runtime_directory()))
                        window.navigate(location)
                        smoke['navigated'] = True
                    except (ValueError, OSError):
                        window.close()
                        application.exit(4)
                elif not window.loading and window.directory_worker is None:
                    result = 4 if window.load_failed else 0
                    window.close()
                    application.exit(result)
            elif time.monotonic() - started > 40:
                window.close()
                application.exit(3)
        timer = QTimer(window)
        timer.timeout.connect(finish_smoke)
        timer.start(200)
    logger.info("应用启动：默认只读浏览，Windows 写入需独立授权，ext4 禁写")
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
