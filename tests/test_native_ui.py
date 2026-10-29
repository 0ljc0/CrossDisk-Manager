"""原生目录查询的分页、导航、错误与取消，不写入被浏览数据。"""

import json
import logging
import subprocess
from types import SimpleNamespace

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.backends.inventory_browser import InventoryBrowserSource
from app.core.browser import Location
from app.core.config import AppConfig, ConfigStore
from app.jobs.directory_worker import DirectoryWorker
from app.ui.main_window import MainWindow
from test_inventory import sample, parse
from test_inventory_ui import FakeService, wait_scan


def wait_directory(window):
    for _ in range(300):
        QTest.qWait(20)
        if window.directory_worker is None and window.pending_directory is None:
            return
    raise AssertionError("目录加载未结束")


def test_async_paging_navigation_error_and_hidden(tmp_path, sample):
    application = QApplication.instance() or QApplication([])
    folder = tmp_path / "目录"
    folder.mkdir()
    (folder / "子目录").mkdir()
    for number in range(405):
        (folder / f"中文-{number}.txt").touch()
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("native-ui"),
                        inventory_service=FakeService(parse(sample)))
    window.show()
    wait_scan(window)
    partition_id = window.inventory.partitions[2].id  # 普通数据分区，不能伪造 EFI 的 browsable 标志。
    # 用可丢弃目录替换根，测试 GUI 与真实子进程，不接触任何原始磁盘。
    window.source.roots[partition_id] = str(folder)
    from dataclasses import replace
    window.partitions[partition_id] = replace(window.partitions[partition_id], browsable=True)
    window.navigate(Location(partition_id))
    ticks = []
    QTimer.singleShot(10, lambda: ticks.append(True))
    wait_directory(window)
    assert ticks and len(window.file_model.entries) == 200
    assert window.more_button.isVisible()
    window.more_button.click()
    wait_directory(window)
    assert len(window.file_model.entries) == 400
    window.more_button.click()
    wait_directory(window)
    assert len(window.file_model.entries) == 406
    assert not window.more_button.isVisible()
    index = next(window.proxy.index(i, 0) for i in range(window.proxy.rowCount())
                 if window.proxy.index(i, 0).data() == "子目录")
    window.table.doubleClicked.emit(index)
    wait_directory(window)
    assert window.location.relative_path == "子目录"
    assert "目录为空" in window.message.text()
    window.back_action.trigger()
    wait_directory(window)
    assert window.location.relative_path == ""
    window.navigate(Location(partition_id, "不存在"))
    wait_directory(window)
    assert "路径不存在" in window.message.text()
    window.navigate(Location(partition_id))
    window.navigate(Location(partition_id, "子目录"))
    wait_directory(window)
    assert window.location.relative_path == "子目录" and not window.file_model.entries
    assert all(not action.isEnabled() for action in window.write_actions)
    window.close()
    wait_directory(window)
    application.processEvents()


def test_worker_timeout_and_cancel_without_network(monkeypatch):
    application = QApplication.instance() or QApplication([])
    class StalledProcess:
        returncode = None
        killed = False
        def communicate(self, payload=None, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("mock-query", timeout)
            return "", ""
        def poll(self):
            return 0 if self.killed else None
        def kill(self):
            self.killed = True
    process = StalledProcess()
    monkeypatch.setattr("app.jobs.directory_worker.subprocess.Popen", lambda *a, **kw: process)
    worker = DirectoryWorker(1, Location("test"), "C:\\", False, timeout=0.05)
    messages = []
    worker.failed.connect(lambda number, message: messages.append(message))
    worker.start()
    while worker.isRunning():
        QTest.qWait(10)
    application.processEvents()
    assert process.killed and "超时" in messages[0]
    process.killed = False
    worker = DirectoryWorker(2, Location("test"), "C:\\", False)
    worker.start()
    worker.requestInterruption()
    while worker.isRunning():
        QTest.qWait(10)
    assert process.killed


def test_query_maps_denied_and_locked_errors(monkeypatch, capsys):
    import io
    from app.jobs import native_query
    request = dict(partition_id="test", root="C:\\", relative_path="", offset=0,
                   show_hidden=False, fingerprint="", backend_spec=dict(kind="Windows", partition=dict(
                       id="test", name="test", filesystem="NTFS", status="只读", browsable=True,
                       writable=False, reason="test", category="普通数据")))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(request)))
    monkeypatch.setattr("app.jobs.native_query.NativeWindowsBackend.list_dir",
                        lambda *a, **kw: (_ for _ in ()).throw(PermissionError("私密路径")))
    assert native_query.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert "访问被拒绝" in result["error"] and "私密路径" not in result["error"]
