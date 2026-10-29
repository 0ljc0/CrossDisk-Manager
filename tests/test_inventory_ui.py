"""后台扫描的界面测试，不查询真实磁盘。"""

import logging
import time

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.config import AppConfig, ConfigStore
from app.core.inventory import DiskInventory, InventoryError
from app.ui.main_window import MainWindow
from app.ui.browser_models import DISK_ROLE
from test_inventory import sample, parse


class FakeService:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def scan(self):
        self.calls += 1
        time.sleep(0.08)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def wait_scan(window):
    for _ in range(100):
        QTest.qWait(20)
        if window.worker is None and window.refresh_action.isEnabled():
            return
    pytest.fail("扫描线程没有结束")


def test_background_scan_tree_properties_and_refresh(tmp_path, sample):
    application = QApplication.instance() or QApplication([])
    service = FakeService(parse(sample))
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("ui"),
                        inventory_service=service)
    window.show()
    ticks = []
    QTimer.singleShot(20, lambda: ticks.append(True))
    wait_scan(window)
    assert ticks  # 查询等待期间 GUI 事件循环仍在响应。
    root = window.partition_model.index(0, 0)
    assert window.partition_model.rowCount(root) == 6
    window.tree.setCurrentIndex(root)
    assert root.data(DISK_ROLE)
    assert "测试磁盘" in window.properties.text()
    window.tree.setCurrentIndex(window.partition_model.index(5, 0, root))
    assert "起始偏移" in window.properties.text()
    assert "未识别" in window.properties.text()
    assert all(not a.isEnabled() for a in window.write_actions)
    assert window.file_model.rowCount() == 0
    service.result = DiskInventory((), (), ())  # 拔出后的空清单不能保留旧设备。
    window.scan_action.trigger()
    wait_scan(window)
    assert not window.partitions
    assert window.partition_model.rowCount() == 0
    assert "未发现" in window.message.text()
    window.close()
    application.processEvents()


@pytest.mark.parametrize("message", ["找不到 Windows PowerShell", "权限不足", "磁盘扫描超时"])
def test_scan_failure_display_and_retry(tmp_path, message):
    application = QApplication.instance() or QApplication([])
    service = FakeService(InventoryError(message))
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("ui"),
                        inventory_service=service)
    window.show()
    wait_scan(window)
    assert message in window.message.text()
    service.result = DiskInventory((), (), ())
    window.refresh_action.trigger()
    wait_scan(window)
    assert service.calls == 2
    window.close()
    application.processEvents()


def test_close_during_scan_waits_without_destroying_worker(tmp_path):
    application = QApplication.instance() or QApplication([])
    service = FakeService(DiskInventory((), (), ()))
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("ui"),
                        inventory_service=service)
    window.show()
    QTest.qWait(20)
    window.close()
    assert window.close_pending
    wait_scan(window)
    assert not window.isVisible()
    application.processEvents()
