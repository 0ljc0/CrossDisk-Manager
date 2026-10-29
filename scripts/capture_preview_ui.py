"""任务 07：D 盘代码/Markdown、图片与 ext4 镜像文本预览；不读取 Ubuntu 实盘。"""

import hashlib
import logging
from pathlib import Path
import sys
import tempfile

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.browser import VirtualPath
from app.core.config import AppConfig, ConfigStore
from app.core.inventory import DiskInfo, DiskInventory, PartitionInfo
from app.services.disk_inventory import DiskInventoryService, LINUX_DATA
from app.ui.main_window import MainWindow


def wait_idle(window) -> None:
    for _ in range(3000):
        QTest.qWait(20)
        if (window.worker is None and window.directory_worker is None and window.pending_directory is None
                and window.preview_worker is None and window.pending_preview is None):
            return
    raise RuntimeError("只读预览没有结束")


def select(window, name) -> None:
    index = next(window.proxy.index(i, 0) for i in range(window.proxy.rowCount())
                 if window.proxy.index(i, 0).data() == name)
    window.table.setCurrentIndex(index)
    wait_idle(window)
    assert window.preview_result is not None


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project / "tests"))
    from ext4_fixture import make_image, SAMPLE
    application = QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        image = make_image(root / "ext4.img")
        inventory = DiskInventoryService().scan()
        disk = DiskInfo("preview-image-disk", 999, "测试镜像（非 Ubuntu 实盘）", image.stat().st_size,
                        "12345678-1234-1234-1234-123456789abc", "fixture", "GPT", "镜像", False, True, True)
        part = PartitionInfo("preview-image-ext4", disk.id, 999, 1, "11111111-2222-3333-4444-555555555555",
                             LINUX_DATA, 0, disk.size, False, "", "", "未识别", "待验证", "Linux 镜像", "只读镜像", "", True)
        class SnapshotService:
            def scan(self):
                return DiskInventory(inventory.disks + (disk,), inventory.partitions + (part,), inventory.volumes)
        window = MainWindow(AppConfig(window_width=1600, window_height=900), ConfigStore(root / "config.json"),
                            logging.getLogger("preview-check"), inventory_service=SnapshotService())
        window.show()
        window.splitter.setSizes([260, 650, 690])
        window.right_splitter.setSizes([180, 650])
        wait_idle(window)
        window.source.ext4[part.id]["image"] = str(image)
        output = project / "docs/screenshots"
        output.mkdir(parents=True, exist_ok=True)
        for file, name in ((project / "app/main.py", "python"), (project / "README.md", "markdown"),
                           (project / "docs/screenshots/task06-windows.png", "image")):
            before = hashlib.sha256(file.read_bytes()).hexdigest()
            modified = file.stat().st_mtime_ns
            window.navigate(window.source.resolve_address(str(file.parent)))
            wait_idle(window)
            select(window, file.name)
            assert window.preview_result.kind == ("image" if name == "image" else "text")
            assert hashlib.sha256(file.read_bytes()).hexdigest() == before and file.stat().st_mtime_ns == modified
            assert window.grab().save(str(output / f"task07-{name}.png"))
            print(f"D drive {name} preview: OK; source hash and mtime unchanged")
        window.navigate(VirtualPath(part.id, "home/demo"))
        wait_idle(window)
        select(window, "sample.txt")
        assert window.preview_result.text == SAMPLE.decode()
        assert window.grab().save(str(output / "task07-ext4-image-text.png"))
        print("ext4 image /home/demo/sample.txt: 28-byte read-only preview OK; no Ubuntu real partition opened")
        window.close()
        wait_idle(window)
        application.processEvents()


if __name__ == "__main__":
    main()
