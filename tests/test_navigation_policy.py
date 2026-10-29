"""任务 06：统一路径、保护先于能力、跨后端导航与过期结果。"""

from dataclasses import asdict, replace
import logging
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.core.backend import FileSystemBackend
from app.core.browser import DirectoryPage, FileEntry, Location, Partition, ReadOnlyCapabilities
from app.core.capability_policy import CapabilityPolicy
from app.core.config import AppConfig, ConfigStore
from app.core.virtual_path import VirtualPath
from app.backends.windows_native import NativeWindowsBackend
from app.backends.ext4_readonly import Ext4ReadOnlyBackend
from app.services.backend_access import query_page
from app.ui.browser_models import FileTableModel
from app.ui.main_window import MainWindow
from ext4_fixture import make_image
from test_inventory import sample, parse
from test_inventory_ui import FakeService, wait_scan
from test_native_ui import wait_directory


def test_virtual_path_canonical_parent_child_and_legacy():
    path = VirtualPath("linux", "/home/./demo/../user//")
    assert path.path == "home/user"
    assert path.relative_path == "home/user"
    assert path.parent == VirtualPath("linux", "home")
    assert path.parent.child("中文") == VirtualPath("linux", "home/中文")
    assert [p.path for p in path.breadcrumbs()] == ["", "home", "home/user"]
    assert Location("linux", relative_path="home") == VirtualPath("linux", "home")
    assert VirtualPath("windows", "home") != VirtualPath("linux", "home")


@pytest.mark.parametrize("path", ["..", "../../home", "home/../../etc", "home\\demo", "home\0x"])
def test_virtual_path_escape_rejected(path):
    with pytest.raises(ValueError):
        VirtualPath("linux", path)


def test_classification_precedes_capabilities_and_nicknames(sample):
    inventory = parse(sample)
    policy = CapabilityPolicy()
    for index, reason in ((0, "EFI"), (1, "MSR"), (4, "Recovery")):
        partition = replace(inventory.partitions[index], category="普通数据", label="用户数据")
        provider = Mock(side_effect=AssertionError("不应调用后端能力"))
        decision = policy.evaluate(partition, provider, "Windows")
        assert not decision.browse and not decision.write and reason in decision.reason
        provider.assert_not_called()
    unknown = replace(inventory.partitions[2], gpt_type="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert not policy.evaluate(unknown, ReadOnlyCapabilities, "Windows").browse
    assert not policy.evaluate(inventory.partitions[2], None, "").browse
    forced_write = ReadOnlyCapabilities(write=True)
    assert policy.evaluate(inventory.partitions[2], forced_write, "Windows").write is False
    assert not policy.evaluate(inventory.partitions[5], ReadOnlyCapabilities, "Windows").browse


def test_worker_rejects_protected_partition_before_construction(sample, monkeypatch):
    inventory = parse(sample)
    partition = inventory.partitions[0]
    from app.backends.inventory_browser import InventoryBrowserSource
    source = InventoryBrowserSource(inventory)
    source.roots[partition.id] = "C:\\"  # 即使错误注册挂载路径，分类保护仍优先。
    assert next(p for p in source.partitions() if p.id == partition.id).browsable
    with pytest.raises(ValueError, match="EFI"):
        source.request_spec(partition.id)
    factory = Mock(side_effect=AssertionError("不能构造 EFI 后端"))
    monkeypatch.setattr("app.services.backend_access.NativeWindowsBackend", factory)
    request = dict(partition_id=partition.id, root="C:\\", relative_path="", offset=0,
                   show_hidden=False, fingerprint="", backend_spec=dict(kind="Windows", partition=asdict(partition)))
    with pytest.raises(ValueError, match="EFI"):
        query_page(request)
    factory.assert_not_called()


def test_unknown_fields_are_unknown_and_not_false():
    application = QApplication.instance() or QApplication([])
    model = FileTableModel()
    model.set_entries((FileEntry("unknown", None),))
    assert model.index(0, 1).data() == "未知"
    assert model.index(0, 2).data() == "未知"
    assert model.index(0, 3).data() == "未知"
    assert model.index(0, 4).data() == "读：未知 / 写：未知"
    assert model.index(0, 5).data() == "未知"
    assert model.index(0, 6).data() == "未知"
    assert "未知" in model.index(0, 0).data(Qt.ItemDataRole.ToolTipRole)


def test_backends_implement_same_protocol(tmp_path):
    assert isinstance(NativeWindowsBackend("temp", str(tmp_path)), FileSystemBackend)
    with Ext4ReadOnlyBackend.from_image(str(make_image(tmp_path / "ext4.img"))) as backend:
        assert isinstance(backend, FileSystemBackend)
        assert backend.stat("home").backend_source == "ext4"


def test_cross_backend_history_breadcrumbs_and_stale_result(tmp_path, sample):
    application = QApplication.instance() or QApplication([])
    windows = tmp_path / "windows"
    (windows / "Users").mkdir(parents=True)
    (windows / "Users" / "windows-only.txt").touch()
    image = make_image(tmp_path / "ext4.img")
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("navigation"),
                        inventory_service=FakeService(parse(sample)))
    window.show()
    wait_scan(window)
    win_id, ext_id = window.inventory.partitions[2].id, window.inventory.partitions[5].id
    window.source.roots[win_id] = str(windows)
    window.source.ext4[ext_id]["image"] = str(image)
    window.partitions = {p.id: p for p in window.source.partitions()}
    window.navigate(VirtualPath(win_id, "Users"))
    wait_directory(window)
    assert window.file_model.entries[0].name == "windows-only.txt"
    assert all(e.backend_source == "Windows" for e in window.file_model.entries)
    old_request = window.request_id
    window.navigate(VirtualPath(ext_id, "home"))
    assert not window.file_model.entries  # 加载前就清空，不能残留另一分区内容。
    window.directory_ready(old_request, DirectoryPage((FileEntry("STALE", False),), None, ""))
    window.directory_failed(old_request, "旧请求错误，不应显示")
    assert not window.file_model.entries
    assert "旧请求错误" not in window.message.text()
    wait_directory(window)
    assert window.file_model.entries[0].name == "demo"
    assert all(e.backend_source == "ext4" for e in window.file_model.entries)
    assert window.breadcrumb_buttons[-1].text() == "home"
    window.back_action.trigger()
    wait_directory(window)
    assert window.location == VirtualPath(win_id, "Users")
    assert "windows-only.txt" in window.file_model.entries[0].name
    window.forward_action.trigger()
    wait_directory(window)
    assert window.location == VirtualPath(ext_id, "home")
    window.breadcrumb_buttons[0].click()
    wait_directory(window)
    assert window.location == VirtualPath(ext_id)
    assert window.file_model.entries[0].name == "home"
    window.navigate(VirtualPath(win_id, "Users"))
    window.navigate(VirtualPath(ext_id, "home/demo"))
    wait_directory(window)
    assert all(e.backend_source == "ext4" for e in window.file_model.entries)
    assert all(not a.isEnabled() for a in window.write_actions)
    window.navigate(VirtualPath(window.inventory.partitions[0].id))
    assert "EFI" in window.message.text()
    assert not window.file_model.entries
    window.close()
    wait_directory(window)
    application.processEvents()
