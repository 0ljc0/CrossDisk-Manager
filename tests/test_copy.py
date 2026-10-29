"""复制发布、失败清理与 Windows/ext4 源验证。"""
from dataclasses import asdict
import hashlib
import os
import time
import pytest
from app.core.copy_job import CopyJob
from app.services import copy_service as service
from test_search import native_source
from ext4_fixture import make_image
from test_inventory import sample, parse
from app.backends.ext4_readonly import Ext4ReadOnlyBackend


@pytest.fixture
def paths(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    # 测试普通临时目录，生产路径仍要求 Volume GUID。
    monkeypatch.setattr(service, "check_target", lambda request: request['relative_path'])
    return source, target


def job_for(source, target, name="data.bin", **kwargs):
    return CopyJob(dict(native_source(source), relative_path=name),
                   dict(native_source(target.parent), relative_path=target.name), **kwargs)


def test_copy_hash_and_no_overwrite(paths):
    source, target = paths
    data = os.urandom(2 * 1024 * 1024 + 17)
    (source / "data.bin").write_bytes(data)
    job = job_for(source, target)
    result = service.copy_job(job)
    assert result['completed'] == 1 and result['state'] == '完成'
    assert hashlib.sha256((target / 'data.bin').read_bytes()).digest() == hashlib.sha256(data).digest()
    (source / 'data.bin').write_bytes(b'new')
    assert service.copy_job(job)['skipped'] == 1
    assert (target / 'data.bin').read_bytes() == data
    assert service.copy_job(job_for(source, target, conflict='error'))['state'] == '失败'


def test_cancel_cleanup_and_retry_directory(paths):
    source, target = paths
    (source / 'folder').mkdir()
    (source / 'folder' / 'large.bin').write_bytes(b'x' * (4 * 1024 * 1024))
    job = job_for(source, target, 'folder')
    cancel = [False]
    def progress(value):
        if value['bytes']:
            cancel[0] = True
    assert service.copy_job(job, progress, lambda: cancel[0])['state'] == '已取消'
    assert not list(target.rglob('*.partial'))
    assert not (target / 'folder' / 'large.bin').exists()
    assert service.copy_job(job)['completed'] == 1


def test_space_and_permission_failure_preserve_targets(paths, monkeypatch):
    source, target = paths
    (source / 'data.bin').write_bytes(b'abc')
    monkeypatch.setattr(service.shutil, 'disk_usage', lambda path: type('Usage', (), dict(free=0))())
    events = []
    assert service.copy_job(job_for(source, target), events.append)['state'] == '失败'
    assert any('空间不足' in e['message'] for e in events)
    assert not list(target.iterdir())
    monkeypatch.setattr(service.shutil, 'disk_usage', lambda path: (_ for _ in ()).throw(PermissionError()))
    assert service.copy_job(job_for(source, target))['failed'] == 1


def test_publish_race_never_overwrites(paths, monkeypatch):
    source, target = paths
    (source / 'data.bin').write_bytes(b'abc')
    original = service.os.rename
    def race(a, b):
        with open(b, 'xb') as writer:
            writer.write(b'existing')
        original(a, b)
    monkeypatch.setattr(service.os, 'rename', race)
    assert service.copy_job(job_for(source, target))['state'] == '失败'
    assert (target / 'data.bin').read_bytes() == b'existing'
    assert not list(target.glob('*.partial'))


def test_ext4_home_export(paths, tmp_path, sample):
    _, target = paths
    image = make_image(tmp_path / 'image.ext4', include_python=True)
    before = hashlib.sha256(image.read_bytes()).digest()
    inventory = parse(sample)
    partition, disk = inventory.partitions[5], inventory.disks[0]
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        fingerprint = backend.probe['fingerprint']
        with backend.open_read('home/demo/script.py') as reader:
            expected = reader.read()
    request = dict(partition_id=partition.id, relative_path='home/demo', root='',
                   backend_spec=dict(kind='ext4', image=str(image), fingerprint=fingerprint,
                                     partition=asdict(partition), disk=asdict(disk)))
    job = CopyJob(request, dict(native_source(target.parent), relative_path=target.name))
    result = service.copy_job(job)
    assert result['completed'] >= 1 and result['failed'] == 0
    assert (target / 'demo' / 'script.py').read_bytes() == expected
    assert hashlib.sha256(image.read_bytes()).digest() == before


def test_target_guards():
    for target in ({}, dict(backend_spec=dict(kind='ext4')), dict(backend_spec=dict(kind='Windows'), root='D:\\')):
        with pytest.raises(ValueError):
            service.check_target(target)
    for path in ('', 'Windows/x', 'folder/../x', 'EFI/x', 'folder/a:stream'):
        with pytest.raises(ValueError):
            service.check_target(dict(backend_spec=dict(kind='Windows'), root='\\\\?\\Volume{test}\\', relative_path=path))


def test_qt_queue_pause_cancel_and_retry(paths):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from app.ui.copy_dialog import CopyDialog
    application = QApplication.instance() or QApplication([])
    source, target = paths
    (source / 'data.bin').write_bytes(b'x' * (8 * 1024 * 1024))
    dialog = CopyDialog()
    job = job_for(source, target)
    dialog.pending.append(job)
    dialog.start_next()
    dialog.worker.pause_flag.set()
    QTest.qWait(50)
    assert dialog.worker is not None
    dialog.cancel()
    for _ in range(200):
        QTest.qWait(10)
        time.sleep(.01)
        if not dialog.worker:
            break
    assert dialog.worker is None
    assert not (target / 'data.bin').exists()
    dialog.retry()
    for _ in range(300):
        QTest.qWait(10)
        time.sleep(.01)
        if not dialog.worker:
            break
    assert dialog.worker is None and (target / 'data.bin').stat().st_size == 8 * 1024 * 1024
    dialog.close()
