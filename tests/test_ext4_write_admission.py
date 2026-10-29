"""拒绝路径不得触发任何设备/文件/进程 I/O；UI 保持只读。"""
from dataclasses import replace
import logging
import pytest
from PySide6.QtWidgets import QApplication
from app.core.ext4_write import (Ext4WritableAdapter, UnsupportedWriteError,
                                EXT4_WRITE_DISABLED, ext4_admission_status)
from app.core.browser import Location, ReadOnlyCapabilities
from app.core.config import AppConfig, ConfigStore
from app.core.capability_policy import CapabilityPolicy
from app.services.ext4_write_access import get_ext4_write_backend
from app.ui.main_window import MainWindow
from test_inventory import sample, parse
from test_inventory_ui import FakeService, wait_scan
from test_native_ui import wait_directory
from ext4_fixture import make_image


@pytest.mark.parametrize('operation,args,kwargs', [
    ('create_dir', (Location('linux', 'home/test/new'),), {}),
    ('create_file', (Location('linux', 'home/test/new'),), {}),
    ('write_file', (Location('linux', 'home/test/a'), b'content', 'version'), {}),
    ('rename', (Location('linux', 'home/test/a'), Location('linux', 'home/test/b')), {}),
    ('move', (Location('linux', 'home/test/a'), Location('other', 'etc/passwd')), {}),
    ('delete', (Location('linux', 'home/test/a'),), dict(confirmed=True)),
    ('flush', (), {}),
])
def test_all_mutations_rejected_without_io(operation, args, kwargs, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('拒绝后端不应进行任何 I/O 或执行挂载命令')
    monkeypatch.setattr('builtins.open', forbidden)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    monkeypatch.setattr('os.open', forbidden)
    monkeypatch.setattr('ctypes.WinDLL', forbidden)
    adapter = get_ext4_write_backend()
    assert isinstance(adapter, Ext4WritableAdapter)
    assert not adapter.get_capabilities().write
    assert adapter.get_capabilities().operations == ()
    with pytest.raises(UnsupportedWriteError, match='写入禁用'):
        getattr(adapter, operation)(*args, **kwargs)
    adapter.close()


def test_claims_and_configuration_do_not_grant_write(sample, monkeypatch):
    monkeypatch.setenv('CROSSDISK_EXT4_WRITE_ENABLED', '1')
    monkeypatch.setenv('CROSSDISK_EXT4_DRIVER', 'Paragon')
    part = parse(sample).partitions[5]
    caps = replace(ReadOnlyCapabilities(), write=True)
    decision = CapabilityPolicy().evaluate(part, caps, 'ext4')
    assert decision.browse and not decision.write and decision.reason == EXT4_WRITE_DISABLED
    status = ext4_admission_status()
    assert not status.enabled and len(status.missing) == 6
    assert not get_ext4_write_backend().get_capabilities().write


def test_readonly_image_ui_and_admission_message(tmp_path, sample, monkeypatch):
    import hashlib
    from PySide6.QtWidgets import QMessageBox
    application = QApplication.instance() or QApplication([])
    image = make_image(tmp_path / 'readonly.ext4')
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / 'config.json'), logging.getLogger('admission'),
                        inventory_service=FakeService(parse(sample)))
    window.show()
    wait_scan(window)
    identifier = window.inventory.partitions[5].id
    window.source.ext4[identifier]['image'] = str(image)
    window.navigate(Location(identifier, 'home'))
    wait_directory(window)
    assert window.file_model.rowCount() > 0
    assert all(not action.isEnabled() for action in window.write_actions)
    assert not window.windows_write_action.isEnabled()
    assert EXT4_WRITE_DISABLED in window.properties.text()
    assert not window.partitions[identifier].writable
    messages = []
    monkeypatch.setattr(QMessageBox, 'information', lambda parent, title, message: messages.append(message))
    window.show_ext4_admission()
    assert messages and EXT4_WRITE_DISABLED in messages[0] and 'Linux 重挂载' in messages[0]
    assert hashlib.sha256(image.read_bytes()).hexdigest() == digest
    window.close()
