"""仅在 pytest Windows 临时目录中验证受限写入。"""
from dataclasses import replace
import ctypes
import os
from pathlib import Path
import pytest
from app.backends.windows_native import NativeWindowsBackend
from app.services.windows_write import WriteContext, read_text
from app.core.capability_policy import CapabilityPolicy
from app.core.inventory import DiskInventory
from test_inventory import sample, parse


@pytest.fixture
def writable(tmp_path, sample):
    # 使用真实临时目录所在卷 GUID，但元数据/清单为明确测试样本。
    buffer = ctypes.create_unicode_buffer(1024)
    assert ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(str(tmp_path.drive) + '\\', buffer, 1024)
    root = buffer.value
    scope = str(tmp_path)[3:].replace('\\', '/')
    inventory = parse(sample)
    partition = replace(inventory.partitions[2], is_boot=False, volume_path=root, volume_status='OK')
    disk = inventory.disks[0]
    snapshot = DiskInventory((disk,), (partition,), ())
    backend = NativeWindowsBackend(partition.id, root, write_context=WriteContext(partition, disk, scope, lambda: snapshot))
    return backend, scope, tmp_path


def test_create_save_backup_rename_move_delete(writable):
    backend, scope, tmp = writable
    backend.create_dir(scope + '/folder')
    backend.create_file(scope + '/hello.txt')
    assert (tmp / 'folder').is_dir()
    original = read_text(backend, scope + '/hello.txt')
    saved = backend.write_file(scope + '/hello.txt', '你好\n'.encode(), original['version'])
    assert saved['version'] == read_text(backend, scope + '/hello.txt')['version']
    assert (tmp / 'hello.txt').read_text(encoding='utf-8') == '你好\n'
    assert list(tmp.glob('*.bak'))[0].read_bytes() == b''
    backend.rename(scope + '/hello.txt', scope + '/renamed.txt')
    backend.move(scope + '/renamed.txt', scope + '/folder/moved.txt')
    backend.delete(scope + '/folder/moved.txt', permanent=True, confirmed=True)
    backend.delete(scope + '/folder', permanent=True, confirmed=True)
    assert not (tmp / 'folder').exists()


def test_conflicts_preserve_original_and_editor_version(writable):
    backend, scope, tmp = writable
    (tmp / 'a.txt').write_bytes(b'original')
    version = read_text(backend, scope + '/a.txt')['version']
    (tmp / 'a.txt').write_bytes(b'external edit')
    with pytest.raises(ValueError, match='冲突'):
        backend.write_file(scope + '/a.txt', b'our edit', version)
    assert (tmp / 'a.txt').read_bytes() == b'external edit'
    assert not list(tmp.glob('*.partial'))
    with pytest.raises(FileExistsError):
        backend.create_file(scope + '/a.txt')
    (tmp / 'b.txt').write_bytes(b'keep')
    with pytest.raises(FileExistsError):
        backend.rename(scope + '/a.txt', scope + '/b.txt')
    assert (tmp / 'b.txt').read_bytes() == b'keep'
    with pytest.raises(ValueError, match='二次确认'):
        backend.delete(scope + '/a.txt', permanent=True)


@pytest.mark.parametrize('failure', [PermissionError(), OSError(28, 'disk full'), OSError(32, 'locked')])
def test_replace_errors_preserve_original(writable, monkeypatch, failure):
    backend, scope, tmp = writable
    (tmp / 'a.txt').write_bytes(b'original')
    version = read_text(backend, scope + '/a.txt')['version']
    def fail(*args):
        raise failure
    monkeypatch.setattr('app.services.windows_write._replace_with_backup', fail)
    with pytest.raises(OSError):
        backend.write_file(scope + '/a.txt', b'new', version)
    assert (tmp / 'a.txt').read_bytes() == b'original'
    assert not list(tmp.glob('*.partial'))


def test_scope_protection_and_disabled_default(writable):
    backend, scope, tmp = writable
    for path in (scope, 'outside.txt', scope + '/../escape', scope + '/Windows/a', scope + '/a:stream'):
        with pytest.raises(ValueError):
            backend.create_file(path)
    with pytest.raises(ValueError):
        NativeWindowsBackend(backend.partition_id, backend.root).create_file(scope + '/a')
    context = backend.write_context
    for field in (dict(hidden=True), dict(is_boot=True), dict(filesystem='未识别'), dict(category='EFI'), dict(volume_status='Locked')):
        with pytest.raises(ValueError):
            CapabilityPolicy().require_windows_write(replace(context.partition, **field), context.disk)
    for field in (dict(offline=True), dict(read_only=True), dict(identity_stable=False)):
        with pytest.raises(ValueError):
            CapabilityPolicy().require_windows_write(context.partition, replace(context.disk, **field))


def test_recycle_default_and_no_permanent_fallback(writable, monkeypatch):
    backend, scope, tmp = writable
    (tmp / 'a.txt').write_bytes(b'keep')
    calls = []
    def recycle(path):
        calls.append(path)
        raise ValueError('回收站不可用')
    monkeypatch.setattr('app.services.windows_write.recycle', recycle)
    with pytest.raises(ValueError):
        backend.delete(scope + '/a.txt')
    assert calls and (tmp / 'a.txt').read_bytes() == b'keep'


def test_real_lock_and_flush_failure_preserve_source(writable, monkeypatch):
    backend, scope, tmp = writable
    (tmp / 'a.txt').write_bytes(b'original')
    version = read_text(backend, scope + '/a.txt')['version']
    with backend._guard(scope) as folder:
        with backend._handle(folder + '\\a.txt', read=True, share=0x1):
            with pytest.raises(OSError):
                backend.write_file(scope + '/a.txt', b'new', version)
    def disk_full(fd):
        raise OSError(28, 'disk full')
    monkeypatch.setattr('app.services.windows_write.os.fsync', disk_full)
    with pytest.raises(OSError):
        backend.write_file(scope + '/a.txt', b'new', version)
    assert (tmp / 'a.txt').read_bytes() == b'original'
    assert not list(tmp.glob('*.partial'))


def test_editor_worker_conflict_keeps_edited_text(writable, monkeypatch):
    import time
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtTest import QTest
    from app.ui.write_dialog import WriteDialog
    application = QApplication.instance() or QApplication([])
    backend, scope, tmp = writable
    (tmp / 'a.txt').write_bytes(b'original')
    dialog = WriteDialog(backend)
    dialog.path.setText('a.txt')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    def wait():
        for _ in range(300):
            QTest.qWait(10)
            time.sleep(.005)
            if dialog.worker is None:
                return
        raise AssertionError('编辑后台任务未结束')
    dialog.action('read_text')
    wait()
    assert dialog.text.toPlainText() == 'original'
    dialog.text.setPlainText('our edit')
    (tmp / 'a.txt').write_bytes(b'external edit')
    dialog.action('write_file')
    wait()
    assert '冲突' in dialog.status.text()
    assert dialog.text.toPlainText() == 'our edit'
    assert (tmp / 'a.txt').read_bytes() == b'external edit'
    dialog.text.document().setModified(False)
    dialog.close()
