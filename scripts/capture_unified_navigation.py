"""任务 06：真实 C:\\Users 与合成 ext4 镜像切换；不读取真实 Ubuntu 分区。"""

from dataclasses import replace
import logging
from pathlib import Path
import sys
import tempfile

from PySide6.QtWidgets import QApplication

from app.core.browser import VirtualPath
from app.core.config import AppConfig, ConfigStore
from app.core.inventory import DiskInfo, DiskInventory, PartitionInfo
from app.services.disk_inventory import DiskInventoryService, LINUX_DATA
from app.ui.main_window import MainWindow
from scripts.capture_ext4_image_ui import wait_idle


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from ext4_fixture import make_image
    application = QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        image = make_image(root / "ext4.img")
        real_inventory = DiskInventoryService().scan()  # 只有 Storage 元数据。
        disk = DiskInfo("test-image-disk", 999, "测试镜像（非 Ubuntu 实盘）", image.stat().st_size,
                        "12345678-1234-1234-1234-123456789abc", "fixture", "GPT", "镜像", False, True, True)
        part = PartitionInfo("test-image-ext4", disk.id, 999, 1, "11111111-2222-3333-4444-555555555555",
                             LINUX_DATA, 0, disk.size, False, "", "", "未识别", "待验证", "Linux 镜像", "只读镜像", "", True)
        inventory = DiskInventory(real_inventory.disks + (disk,), real_inventory.partitions + (part,), real_inventory.volumes)
        class SnapshotService:
            def scan(self):
                return inventory
        window = MainWindow(AppConfig(window_width=1600, window_height=850), ConfigStore(root / "config.json"),
                            logging.getLogger("unified-check"), inventory_service=SnapshotService())
        window.show()
        wait_idle(window)
        window.source.ext4[part.id]["image"] = str(image)
        windows = window.source.resolve_address("C:\\Users")
        output = Path("docs/screenshots")
        output.mkdir(parents=True, exist_ok=True)
        window.navigate(windows)
        wait_idle(window)
        assert not window.load_failed and all(e.backend_source == "Windows" for e in window.file_model.entries)
        assert window.grab().save(str(output / "task06-windows.png"))
        window.navigate(VirtualPath(part.id, "home"))
        wait_idle(window)
        assert not window.load_failed and window.file_model.entries[0].name == "demo"
        assert all(e.backend_source == "ext4" for e in window.file_model.entries)
        assert window.grab().save(str(output / "task06-ext4-image.png"))
        window.back_action.trigger()
        wait_idle(window)
        assert window.location == windows and all(e.backend_source == "Windows" for e in window.file_model.entries)
        window.forward_action.trigger()
        wait_idle(window)
        assert window.location == VirtualPath(part.id, "home")
        window.breadcrumb_buttons[0].click()
        wait_idle(window)
        assert window.location == VirtualPath(part.id)
        assert all(not action.isEnabled() for action in window.write_actions)
        window.close()
        wait_idle(window)
        application.processEvents()
        print("Unified GUI: C:\\Users <-> ext4 image /home; history, breadcrumbs and read-only policy OK")
        print("No real Ubuntu partition opened; image metadata and GUI config used temporary files")


if __name__ == "__main__":
    main()
