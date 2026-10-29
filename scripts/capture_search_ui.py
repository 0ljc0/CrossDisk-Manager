"""任务 08：搜索选定 C/D 目录及 ext4 镜像 /home；不扫描 Ubuntu 实盘。"""

from dataclasses import replace
import hashlib
import logging
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.core.browser import VirtualPath
from app.core.config import AppConfig, ConfigStore
from app.core.inventory import DiskInfo, DiskInventory, PartitionInfo
from app.services.disk_inventory import DiskInventoryService, LINUX_DATA
from app.ui.main_window import MainWindow
from scripts.capture_preview_ui import wait_idle


def wait_search(dialog) -> None:
    from PySide6.QtTest import QTest
    for _ in range(1500):
        QTest.qWait(20)
        if dialog.worker is None:
            return
    raise RuntimeError("搜索未结束")


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project / "tests"))
    from ext4_fixture import make_image
    application = QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        c_fixture = root / "c-files"
        c_fixture.mkdir()
        (c_fixture / "c_sample.py").write_text("# metadata only\n", encoding="utf-8")
        image = make_image(root / "ext4.img", include_python=True)
        before = hashlib.sha256(image.read_bytes()).hexdigest()
        real_inventory = DiskInventoryService().scan()
        disk = DiskInfo("search-image-disk", 999, "测试镜像（非 Ubuntu 实盘）", image.stat().st_size,
                        "12345678-1234-1234-1234-123456789abc", "fixture", "GPT", "镜像", False, True, True)
        part = PartitionInfo("search-image-ext4", disk.id, 999, 1, "11111111-2222-3333-4444-555555555555",
                             LINUX_DATA, 0, disk.size, False, "", "", "未识别", "待验证", "Linux 镜像", "只读镜像", "", True)
        class SnapshotService:
            def scan(self):
                return DiskInventory(real_inventory.disks + (disk,), real_inventory.partitions + (part,), real_inventory.volumes)
        window = MainWindow(AppConfig(window_width=1600, window_height=850), ConfigStore(root / "config.json"),
                            logging.getLogger("search-check"), inventory_service=SnapshotService())
        window.show()
        wait_idle(window)
        window.source.ext4[part.id]["image"] = str(image)
        window.navigate(VirtualPath(part.id, "home"))
        wait_idle(window)
        c_location = window.source.resolve_address(str(c_fixture))
        d_location = window.source.resolve_address(str(project / "app"))
        assert c_location.partition_id != d_location.partition_id
        selected = {c_location.partition_id: c_location.path, d_location.partition_id: d_location.path, part.id: "home"}
        window.open_search()
        dialog = window.search_dialog
        def narrowed(scope):
            sources, skipped = window.build_search_sources(2)
            return [dict(s, relative_path=selected[s["partition_id"]]) for s in sources if s["partition_id"] in selected], skipped
        dialog.source_builder = narrowed
        dialog.resize(1450, 850)
        dialog.scope.setCurrentIndex(2)
        dialog.scope.setItemText(2, "验收：C 临时目录 / D 项目 app / ext4 镜像 home")
        dialog.pattern.setText("*.py")
        dialog.start_button.click()
        wait_search(dialog)
        assert dialog.stats["complete"]
        assert {r.partition_id for r in dialog.model.results} == set(selected)
        assert any(r.entry.name == "script.py" and r.entry.backend_source == "ext4" for r in dialog.model.results)
        output = project / "docs/screenshots"
        output.mkdir(parents=True, exist_ok=True)
        assert dialog.grab().save(str(output / "task08-search.png"))
        ext_row = next(i for i, result in enumerate(dialog.model.results) if result.partition_id == part.id)
        dialog.table.setCurrentIndex(dialog.model.index(ext_row, 0))
        dialog.table.scrollTo(dialog.model.index(ext_row, 0))
        application.processEvents()
        assert dialog.grab().save(str(output / "task08-search-ext4.png"))
        print(f"Scoped C/D/ext4-image *.py search: {dialog.model.rowCount()} results; {dialog.stats['entries']} metadata entries")
        result = next(r for r in dialog.model.results if r.partition_id == d_location.partition_id)
        window.locate_search_result(result)
        wait_idle(window)
        assert window.location.partition_id == d_location.partition_id
        assert window.location.path == VirtualPath(result.partition_id, result.relative_path).parent.path
        assert window.grab().save(str(output / "task08-locate.png"))
        print("Stable-partition result location: OK")
        assert hashlib.sha256(image.read_bytes()).hexdigest() == before
        print("Image hash unchanged; no real Ubuntu partition searched; no index created")
        window.close()
        wait_idle(window)
        application.processEvents()


if __name__ == "__main__":
    main()
