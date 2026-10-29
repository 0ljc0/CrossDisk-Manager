"""只读扫描本机并截取任务 03 界面，配置写入临时目录。"""

import logging
import tempfile
from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.config import AppConfig, ConfigStore
from app.services.disk_inventory import DiskInventoryService
from app.ui.main_window import MainWindow


def main() -> None:
    application = QApplication([])
    with tempfile.TemporaryDirectory() as temporary:
        window = MainWindow(AppConfig(window_width=1200, window_height=800),
            ConfigStore(Path(temporary) / "config.json"), logging.getLogger("inventory-check"),
            inventory_service=DiskInventoryService())
        window.show()
        for _ in range(800):
            QTest.qWait(50)
            if window.worker is None and window.refresh_action.isEnabled():
                break
        if window.inventory is None:
            window.close()
            raise RuntimeError("实际磁盘清单扫描失败")
        inventory = window.inventory
        target = next((p for p in inventory.partitions if p.category.startswith("Linux")),
                      next(iter(inventory.partitions), None))
        if target:
            from app.core.browser import Location
            window.navigate(Location(target.id))
        QTest.qWait(100)
        output = Path("docs/screenshots/task03-inventory.png")
        output.parent.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(output))
        print(f"Live UI: {len(inventory.disks)} disks, {len(inventory.partitions)} partitions, {len(inventory.volumes)} volumes")
        window.close()
        application.processEvents()


if __name__ == "__main__":
    main()
