"""任务12：运行时分派、去敏日志与候选版本边界。"""
import logging
import sys
from pathlib import Path
import pytest
from app.core.runtime import worker_command, runtime_directory
from app.core.logging_setup import setup_logging, install_exception_hook


def test_frozen_worker_dispatch_is_fixed(monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', r'D:\Program Files\CrossDisk\CrossDiskManager.exe')
    assert worker_command('native') == [sys.executable, '--worker', 'native']
    assert worker_command('search') == [sys.executable, '--worker', 'search']
    assert runtime_directory() == Path(sys.executable).parent
    with pytest.raises(ValueError):
        worker_command('arbitrary.py')


def test_source_dispatch_unchanged(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    assert worker_command('native')[1:] == ['-B', '-m', 'app.jobs.native_query']
    assert (runtime_directory() / 'app/main.py').is_file()


def test_log_viewer_is_bounded_and_missing_is_clear(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from app.ui.log_dialog import LogDialog
    application = QApplication.instance() or QApplication([])
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    dialog = LogDialog()
    assert '尚未创建' in dialog.text.toPlainText()
    log = tmp_path / 'CrossDiskManager/logs/app.log'
    log.parent.mkdir(parents=True)
    log.write_bytes(b'old content\n' * 10000 + b'latest status')
    dialog.refresh()
    assert len(dialog.text.toPlainText()) <= 65536
    assert dialog.text.toPlainText().endswith('latest status')
    assert dialog.text.isReadOnly()
    dialog.close()


def test_exception_log_does_not_capture_secret_message(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    logger = setup_logging(tmp_path)
    old_hook = sys.excepthook
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: None)
    try:
        install_exception_hook(logger)
        error = ValueError('token=secret D:\\sensitive\\private.txt FILE_CONTENT')
        sys.excepthook(type(error), error, None)
        for handler in logger.handlers:
            handler.flush()
        text = (tmp_path / 'app.log').read_text(encoding='utf-8')
        assert 'ValueError' in text
        assert all(value not in text for value in ('token', 'secret', 'private', 'FILE_CONTENT'))
    finally:
        sys.excepthook = old_hook
