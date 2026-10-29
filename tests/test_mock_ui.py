"""任务 02 的界面行为测试，完全使用内存模拟数据。"""

import logging

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.browser import Location
from app.core.config import AppConfig, ConfigStore
from app.ui.main_window import MainWindow


@pytest.fixture
def window(tmp_path):
    application = QApplication.instance() or QApplication([])
    widget = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("ui-test"))
    widget.show()
    QTest.qWait(120)
    yield widget
    widget.close()
    application.processEvents()


def wait_load():
    QTest.qWait(120)


def select_partition(window, partition_id):
    root = window.partition_model.index(0, 0)
    row = list(window.partitions).index(partition_id)
    window.tree.setCurrentIndex(window.partition_model.index(row, 0, root))
    wait_load()


def test_tree_navigation_and_history(window):
    assert window.splitter.count() == 3
    assert window.file_model.rowCount() == 3
    index = next(window.proxy.index(row, 0) for row in range(window.proxy.rowCount())
                 if window.proxy.index(row, 0).data() == "用户文档")
    window.table.doubleClicked.emit(index)
    assert "加载" in window.message.text()
    wait_load()
    assert window.address.text() == "mock-c:/用户文档"
    assert window.file_model.rowCount() == 2
    window.back_action.trigger()
    wait_load()
    assert window.location == Location("mock-c")
    window.forward_action.trigger()
    wait_load()
    window.up_action.trigger()
    wait_load()
    assert window.location == Location("mock-c")
    assert not window.up_action.isEnabled()
    select_partition(window, "mock-ubuntu")
    assert window.address.text() == "mock-ubuntu:/"
    assert window.file_model.entries[0].name == "home"


@pytest.mark.parametrize("partition_id", ["mock-c", "mock-d", "mock-ubuntu", "mock-efi",
                                         "mock-recovery", "mock-msr", "mock-admin", "mock-unknown"])
def test_capabilities_disable_writes(window, partition_id):
    select_partition(window, partition_id)
    assert all(not action.isEnabled() and action.toolTip() for action in window.write_actions)
    partition = window.partitions[partition_id]
    assert partition.status in window.properties.text()
    if not partition.browsable:
        assert window.pages.currentWidget() == window.message
        reason = window.block_reason
        assert reason in window.message.text()
        window.search.setText("x")
        assert reason in window.message.text()


def test_empty_filter_hidden_refresh_and_address(window):
    window.search.setText("不存在")
    assert "没有匹配" in window.message.text()
    window.search.clear()
    assert window.proxy.rowCount() == 3
    window.hidden_action.setChecked(True)
    wait_load()
    assert window.file_model.rowCount() == 4
    window.address.setText("mock-c:/空目录")
    window.address.returnPressed.emit()
    wait_load()
    assert "目录为空" in window.message.text()
    window.refresh_action.trigger()
    wait_load()
    assert window.location == Location("mock-c", "空目录")
    window.address.setText("mock-c:/../secret")
    window.address.returnPressed.emit()
    assert "格式无效" in window.statusBar().currentMessage()
    assert window.location.relative_path == "空目录"
    window.address.setText("mock-c:/不存在")
    window.address.returnPressed.emit()
    wait_load()
    assert "路径不存在" in window.message.text()


def test_rapid_navigation_ignores_stale_load(window):
    window.navigate(Location("mock-ubuntu"))
    window.navigate(Location("mock-efi"))
    wait_load()
    assert window.file_model.rowCount() == 0
    assert "EFI 引导分区" in window.message.text()


def test_theme_geometry_restore(window):
    window.theme_actions["dark"].trigger()
    window.resize(1280, 800)
    window.close()
    config = window.store.load()
    assert config.theme == "dark"
    assert (config.window_width, config.window_height) == (1280, 800)
    reopened = MainWindow(config, window.store, window.logger)
    assert reopened.theme_actions["dark"].isChecked()
    assert reopened.size().width() == 1280
    reopened.close()


def test_file_properties(window):
    index = next(window.proxy.index(row, 0) for row in range(window.proxy.rowCount())
                 if window.proxy.index(row, 0).data().endswith(".txt"))
    window.table.setCurrentIndex(index)
    assert "2,048 B" in window.properties.text()
    assert "模拟" in window.properties.text()
