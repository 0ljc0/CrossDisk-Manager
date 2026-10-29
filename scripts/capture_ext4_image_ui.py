"""合成 ext4 镜像的真实 pytsk3/GUI 验证；绝不访问物理分区。"""

from dataclasses import asdict
import logging
from pathlib import Path
import sys
import tempfile

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.browser import Location
from app.core.config import AppConfig, ConfigStore
from app.core.inventory import DiskInfo, DiskInventory, PartitionInfo
from app.services.disk_inventory import LINUX_DATA
from app.ui.main_window import MainWindow
from scripts.ext4_readonly import validate_sample
from app.backends.ext4_readonly import Ext4ReadOnlyBackend


def wait_idle(window) -> None:
    for _ in range(2000):
        QTest.qWait(20)
        if window.worker is None and window.directory_worker is None and window.pending_directory is None:
            return
    raise RuntimeError("镜像查询没有完成")


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from ext4_fixture import make_image
    application = QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        image = make_image(root / "ext4-test.img")
        disk = DiskInfo("image-disk", 0, "合成镜像（非真实磁盘）", image.stat().st_size,
                        "12345678-1234-1234-1234-123456789abc", "fixture", "GPT", "镜像", False, True, True)
        part = PartitionInfo("image-ext4", disk.id, 0, 1, "11111111-2222-3333-4444-555555555555",
                             LINUX_DATA, 0, disk.size, False, "", "", "未识别", "待验证", "Linux 镜像", "仅供测试", "", True)
        class ImageService:
            def scan(self):
                return DiskInventory((disk,), (part,), ())
        window = MainWindow(AppConfig(window_width=1280, window_height=800), ConfigStore(root / "config.json"),
                            logging.getLogger("ext4-image"), inventory_service=ImageService())
        window.setWindowTitle("CrossDisk Manager · ext4 合成镜像只读验收")
        window.show()
        wait_idle(window)
        window.source.ext4[part.id]["image"] = str(image)
        output = Path("docs/screenshots")
        output.mkdir(parents=True, exist_ok=True)
        for path, name in (("", "root"), ("home", "home"), ("home/demo", "files")):
            window.navigate(Location(part.id, path))
            wait_idle(window)
            assert not window.load_failed
            assert window.grab().save(str(output / f"task05-image-{name}.png"))
        window.close()
        wait_idle(window)
        application.processEvents()
        with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
            count, digest = validate_sample(backend, "home/demo/sample.txt")
            print(f"Image-only sample export: {count} bytes; SHA256={digest}")
        print("Image-only root/home/files screenshots verified; no physical disk opened")


if __name__ == "__main__":
    main()
