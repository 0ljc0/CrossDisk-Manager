from test_native_ui import bind_test_root
"""后台逐行搜索、范围、取消、定位与即时筛选。"""

import logging
from dataclasses import asdict

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.browser import VirtualPath
from app.core.config import AppConfig, ConfigStore
from app.core.search import SearchLimits, SearchQuery
from app.jobs.search_worker import SearchWorker
from app.ui.main_window import MainWindow
from ext4_fixture import make_image
from test_inventory import sample, parse
from test_inventory_ui import FakeService, wait_scan
from test_native_ui import wait_directory
from test_search import native_source


def wait_search(dialog):
    for _ in range(1500):
        QTest.qWait(20)
        if dialog.worker is None:
            return
    raise AssertionError("搜索进程未结束")


def test_ui_local_filter_global_sources_and_locate(tmp_path, sample):
    application = QApplication.instance() or QApplication([])
    source = tmp_path / "windows"
    source.mkdir()
    (source / "native.py").touch()
    (source / "skip.md").touch()
    image = make_image(tmp_path / "ext4.img", include_python=True)
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("search-ui"),
                        inventory_service=FakeService(parse(sample)))
    window.show()
    wait_scan(window)
    win_id, ext_id = window.inventory.partitions[2].id, window.inventory.partitions[5].id
    bind_test_root(window, win_id, source)
    window.source.ext4[ext_id]["image"] = str(image)
    sources, excluded = window.build_search_sources(2)
    assert ext_id not in [s["partition_id"] for s in sources]  # 不能自动搜索未验证 ext4。
    assert any("尚未验证" in message for message in excluded)
    window.partitions = {p.id: p for p in window.source.partitions()}
    window.navigate(VirtualPath(win_id))
    wait_directory(window)
    window.search.setText("*.py")
    assert window.proxy.rowCount() == 1
    window.search.clear()
    window.local_extensions.setText(".md")
    assert window.proxy.rowCount() == 1
    window.local_extensions.clear()
    window.local_type.setCurrentIndex(2)  # 当前目录没有子目录。
    assert window.proxy.rowCount() == 0
    window.local_type.setCurrentIndex(0)
    window.navigate(VirtualPath(ext_id, "home"))
    wait_directory(window)
    window.open_search()
    dialog = window.search_dialog
    dialog.scope.setCurrentIndex(2)
    dialog.pattern.setText("*.py")
    ticks = []
    QTimer.singleShot(10, lambda: ticks.append(True))
    dialog.start_button.click()
    wait_search(dialog)
    assert ticks and dialog.stats["complete"]
    assert {r.entry.name for r in dialog.model.results} == {"native.py", "script.py"}
    assert {r.partition_id for r in dialog.model.results} == {win_id, ext_id}
    assert "EFI" in dialog.errors.toPlainText()  # 被排除的保护分区也有说明。
    index = next(dialog.model.index(i, 0) for i, r in enumerate(dialog.model.results) if r.partition_id == ext_id)
    dialog.table.doubleClicked.emit(index)
    wait_directory(window)
    assert window.location == VirtualPath(ext_id, "home/demo")
    assert all(not action.isEnabled() for action in window.write_actions)
    # 分区失效后不能根据旧编号定位。
    result = dialog.model.results[0]
    window.partitions.pop(result.partition_id)
    window.locate_search_result(result)
    assert "已失效" in window.message.text()
    old_generation = dialog.generation
    dialog.invalidate()
    dialog.handle_event(old_generation, dict(event="results", results=[]))
    assert dialog.model.rowCount() == 0
    window.close()
    application.processEvents()


def test_real_worker_cancel_is_responsive_and_partial(tmp_path):
    application = QApplication.instance() or QApplication([])
    for number in range(1500):
        (tmp_path / f"file-{number}.py").touch()
    worker = SearchWorker(1, [native_source(tmp_path)], SearchQuery("*.py"), SearchLimits())
    events = []
    worker.event_received.connect(lambda generation, event: events.append(event))
    # 在首批结果已经返回后取消，验证部分结果保留；此槽仅操作线程标志，不接触 GUI。
    worker.event_received.connect(lambda generation, event: worker.requestInterruption()
                                  if event["event"] == "results" else None, Qt.ConnectionType.DirectConnection)
    worker.start()
    for _ in range(500):
        QTest.qWait(20)
        if not worker.isRunning():
            break
    assert not worker.isRunning()
    application.processEvents()
    final = next(e for e in reversed(events) if e["event"] == "finished")
    assert final["stats"]["cancelled"] and not final["stats"]["complete"]
    assert final["stats"]["matches"] > 0
    from app.ui.search_dialog import SearchDialog
    dialog = SearchDialog(lambda _: ([], []))
    dialog.handle_event(dialog.generation, final)
    assert dialog.progress.value() == 0 and "部分完成" in dialog.status.text()
    dialog.close()
    worker.deleteLater()


def test_dialog_close_cancels_worker(tmp_path, sample):
    application = QApplication.instance() or QApplication([])
    (tmp_path / "one.py").touch()
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("search-close"),
                        inventory_service=FakeService(parse(sample)))
    window.show()
    wait_scan(window)
    identifier = window.inventory.partitions[2].id
    bind_test_root(window, identifier, tmp_path)
    window.partitions = {p.id: p for p in window.source.partitions()}
    window.navigate(VirtualPath(identifier))
    wait_directory(window)
    window.open_search()
    dialog = window.search_dialog
    dialog.start_button.click()
    assert dialog.worker is not None
    window.close()
    wait_search(dialog)
    assert not window.isVisible()
    application.processEvents()
