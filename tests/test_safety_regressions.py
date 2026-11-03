from contextlib import contextmanager
from dataclasses import asdict, replace
from types import SimpleNamespace
import ntpath
from unittest.mock import patch
import pytest
from PySide6.QtWidgets import QApplication
from app.backends.windows_native import NativeWindowsBackend, normalize_root
from app.services.backend_access import open_backend
from app.services import copy_service
from app.core.copy_job import CopyJob
from app.ui.write_dialog import WriteDialog
from test_inventory import sample, parse
from test_search import native_source


def test_mismatched_root_rejected_before_backend(tmp_path, sample, monkeypatch):
    partition = replace(parse(sample).partitions[2], volume_path=str(tmp_path / 'declared'))
    request = dict(partition_id=partition.id, root=str(tmp_path / 'other'),
                   backend_spec=dict(kind='Windows', partition=asdict(partition)))
    def forbidden(*args):
        pytest.fail('身份不一致时不得构造后端')
    monkeypatch.setattr('app.services.backend_access.NativeWindowsBackend', forbidden)
    with pytest.raises(ValueError, match='根|身份'):
        with open_backend(request):
            pass


def test_nested_copy_holds_parent_guard(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    (source / 'folder/inner').mkdir(parents=True)
    target = tmp_path / 'target'
    target.mkdir()
    active = []
    original_guard, original_mkdir = NativeWindowsBackend._guard, copy_service.os.mkdir
    @contextmanager
    def guard(self, path):
        with original_guard(self, path) as full:
            if self.partition_id == 'target':
                active.append(path)
            try:
                yield full
            finally:
                if self.partition_id == 'target':
                    active.pop()
    def mkdir(path, *args, **kwargs):
        plain = str(path).removeprefix('\\\\?\\')
        if plain.lower().startswith(str(target).lower()):
            parent = ntpath.relpath(ntpath.dirname(plain), str(tmp_path)).replace('\\', '/')
            assert parent in active, '创建嵌套目录时父目录没有保护句柄'
        return original_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(copy_service, 'check_target', lambda request: request['relative_path'])
    monkeypatch.setattr(NativeWindowsBackend, '_guard', guard)
    monkeypatch.setattr(copy_service.os, 'mkdir', mkdir)
    job = CopyJob(dict(native_source(source, 'source'), relative_path='folder'),
                  dict(native_source(tmp_path, 'target'), relative_path='target'))
    result = copy_service.copy_job(job)
    assert result['failed'] == 0, result
    assert (target / 'folder/inner').is_dir()


@pytest.mark.parametrize('operation', ['create_dir', 'create_file', 'rename', 'move', 'delete'])
def test_unrelated_operation_preserves_editor_version(operation):
    application = QApplication.instance() or QApplication([])
    dialog = WriteDialog(SimpleNamespace(write_context=SimpleNamespace(scope='scope')))
    dialog.loaded_path, dialog.version = 'scope/a.txt', 'original-token'
    dialog.path.setText('a.txt')
    dialog.text.setPlainText('unsaved edit')
    dialog.text.document().setModified(True)
    dialog.ready(dict(ok=True, operation=operation, path='scope/unrelated', value=dict(message='done')))
    try:
        assert dialog.version == 'original-token'
        assert dialog.text.toPlainText() == 'unsaved edit'
        assert dialog.text.document().isModified()
    finally:
        dialog.text.document().setModified(False)
        dialog.close()
