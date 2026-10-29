"""任务 04 本机只读验收与截图；配置只保存在临时目录。"""

import logging
import tempfile
from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.config import AppConfig, ConfigStore
from app.services.disk_inventory import DiskInventoryService
from app.ui.main_window import MainWindow


def wait_idle(window) -> None:
    for _ in range(2000):
        QTest.qWait(20)
        if window.worker is None and window.directory_worker is None and window.pending_directory is None:
            return
    raise RuntimeError("界面只读查询未结束")


def open_address(window, address: str) -> None:
    window.address.setText(address)
    window.address.returnPressed.emit()
    wait_idle(window)


def main() -> None:
    application = QApplication([])
    with tempfile.TemporaryDirectory() as temporary:
        window = MainWindow(AppConfig(window_width=1280, window_height=800),
            ConfigStore(Path(temporary) / "config.json"), logging.getLogger("native-validation"),
            inventory_service=DiskInventoryService())
        window.show()
        wait_idle(window)
        assert window.inventory is not None
        open_address(window, "C:\\Users")
        assert not window.load_failed
        ordinary = len(window.file_model.entries)
        window.hidden_action.setChecked(True)
        wait_idle(window)
        hidden = len(window.file_model.entries)
        assert hidden >= ordinary
        print(f"C:\\Users: visible={ordinary}, including hidden={hidden}")
        output = Path("docs/screenshots")
        output.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(output / "task04-users.png"))
        open_address(window, "C:\\Users\\All Users")
        assert window.load_failed and "链接" in window.message.text()
        print("Existing junction: blocked without following")
        open_address(window, "C:\\System Volume Information")
        assert window.load_failed and "访问被拒绝" in window.message.text()
        print("Restricted folder: access denied, application responsive")
        open_address(window, str(Path.cwd()))
        assert not window.load_failed
        count = len(window.file_model.entries)
        print(f"D drive project: {count} entries")
        folder_index = next(window.proxy.index(row, 0) for row in range(window.proxy.rowCount())
                            if window.proxy.index(row, 0).data() == "app")
        window.table.doubleClicked.emit(folder_index)
        wait_idle(window)
        assert window.location.relative_path.endswith("/app")
        window.back_action.trigger()
        wait_idle(window)
        assert len(window.file_model.entries) == count
        assert all(not action.isEnabled() for action in window.write_actions)
        assert window.grab().save(str(output / "task04-project.png"))
        print("Double-click and back: OK; writes disabled")
        window.close()
        wait_idle(window)
        application.processEvents()


if __name__ == "__main__":
    main()
