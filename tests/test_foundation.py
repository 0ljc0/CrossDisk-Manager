import logging
import os
import subprocess
import sys

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.core.config import AppConfig, ConfigStore, user_data_dir
from app.core.logging_setup import setup_logging
from app.ui.main_window import MainWindow


def test_defaults_and_roundtrip(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    assert store.load().read_only is True
    config = AppConfig(theme="dark", window_width=1200, show_hidden_files=True)
    store.save(config)
    assert store.load() == config


@pytest.mark.parametrize("changes", [{"read_only": False}, {"window_width": -1},
                                      {"show_hidden_files": "false"}, {"language": "unknown"}])
def test_invalid_config_rejected(changes):
    with pytest.raises(ValueError):
        AppConfig(**changes)


def test_corrupt_config_preserved(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError):
        ConfigStore(path).load()
    assert path.read_text(encoding="utf-8") == "broken"


def test_user_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert user_data_dir() == tmp_path / "CrossDiskManager"


def test_logging(tmp_path):
    logger = setup_logging(tmp_path / "logs")
    logger.error("测试异常：ValueError")
    assert "测试异常：ValueError" in (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def test_window_open_close_and_save(tmp_path):
    application = QApplication.instance() or QApplication([])
    store = ConfigStore(tmp_path / "config.json")
    window = MainWindow(AppConfig(), store, logging.getLogger("test"))
    window.show()
    application.processEvents()
    assert window.isVisible()
    assert "跨分区文件管理器" in window.windowTitle()
    window.resize(1100, 700)
    QTimer.singleShot(50, window.close)
    application.exec()
    assert not window.isVisible()
    assert store.load().window_width == 1100
    assert store.load().read_only is True


def test_module_entrypoint(tmp_path):
    # 使用真实 Windows Qt 平台和事件循环，仅将自动关闭计时器放入测试进程。
    script = '''
import runpy
from PySide6.QtCore import QTimer
from app.ui.main_window import MainWindow
original_show = MainWindow.show
def show(self):
    original_show(self)
    QTimer.singleShot(150, self.close)
MainWindow.show = show
runpy.run_module("app.main", run_name="__main__")
'''
    environment = dict(os.environ, LOCALAPPDATA=str(tmp_path))
    result = subprocess.run([sys.executable, "-c", script], env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    root = tmp_path / "CrossDiskManager"
    assert (root / "config.json").exists()
    assert "应用正常退出" in (root / "logs" / "app.log").read_text(encoding="utf-8")
