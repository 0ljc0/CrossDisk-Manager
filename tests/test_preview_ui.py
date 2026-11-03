from test_native_ui import bind_test_root
"""真实子进程预览 Windows 临时文件和 ext4 镜像，不读取 Ubuntu 实盘。"""

import logging
import hashlib

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtGui import QImage

from app.core.browser import VirtualPath
from app.core.config import AppConfig, ConfigStore
from app.core.preview import TEXT_LIMIT, PreviewResult
from app.ui.main_window import MainWindow
from ext4_fixture import make_image, SAMPLE
from test_inventory import sample, parse
from test_inventory_ui import FakeService, wait_scan
from test_native_ui import wait_directory


def wait_preview(window):
    for _ in range(1000):
        QTest.qWait(20)
        if window.preview_worker is None and window.pending_preview is None:
            return
    raise AssertionError("预览任务没有结束")


def select(window, name):
    index = next(window.proxy.index(i, 0) for i in range(window.proxy.rowCount())
                 if window.proxy.index(i, 0).data() == name)
    window.table.setCurrentIndex(index)
    wait_preview(window)
    return index


def test_preview_gui_encodings_more_image_binary_and_ext4(tmp_path, sample):
    application = QApplication.instance() or QApplication([])
    source = tmp_path / "sources"
    source.mkdir()
    (source / "code.py").write_text("# 只读代码\nprint('never execute')\n", encoding="utf-8")
    (source / "gb.log").write_bytes("中文日志".encode("gb18030"))
    (source / "large.log").write_bytes(b"line\n" * (TEXT_LIMIT // 5 + 10))
    (source / "program.exe").write_bytes(b"MZ" + bytes(32))
    picture = QImage(60, 40, QImage.Format.Format_RGB32)
    picture.fill(0xff5577aa)
    assert picture.save(str(source / "photo.png"))
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    image = make_image(tmp_path / "ext4.img")
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("preview"),
                        inventory_service=FakeService(parse(sample)))
    window.show()
    wait_scan(window)
    win_id, ext_id = window.inventory.partitions[2].id, window.inventory.partitions[5].id
    bind_test_root(window, win_id, source)
    window.source.ext4[ext_id]["image"] = str(image)
    window.partitions = {p.id: p for p in window.source.partitions()}
    window.navigate(VirtualPath(win_id))
    wait_directory(window)
    select(window, "code.py")
    assert window.preview_panel.text.isReadOnly()
    assert "never execute" in window.preview_panel.text.toPlainText()
    select(window, "gb.log")
    assert window.preview_result is None and window.preview_panel.encoding.isEnabled()
    window.preview_panel.encoding.setCurrentIndex(4)  # GB18030。
    wait_preview(window)
    assert window.preview_result.text == "中文日志"
    select(window, "large.log")
    assert window.preview_result.truncated and window.preview_panel.more.isEnabled()
    length = len(window.preview_result.text)
    window.preview_panel.more.click()
    wait_preview(window)
    assert len(window.preview_result.text) > length
    select(window, "photo.png")
    assert window.preview_result.kind == "image" and not window.preview_panel.pixmap.isNull()
    index = select(window, "program.exe")
    window.table.doubleClicked.emit(index)
    wait_preview(window)
    assert window.preview_result.kind == "unsupported" and window.preview_result.bytes_read == 0
    old_id = window.preview_request_id
    window.navigate(VirtualPath(ext_id, "home/demo"))
    wait_directory(window)
    window.preview_ready(old_id, PreviewResult("text", win_id, "code.py", 1, "", "Windows", text="STALE"))
    assert window.preview_result is None
    select(window, "sample.txt")
    assert window.preview_result.backend_source == "ext4"
    assert window.preview_result.text == SAMPLE.decode()
    assert window.preview_result.read_only
    assert all("编辑" not in b.text() for b in window.preview_panel.findChildren(QPushButton))
    assert all(not action.isEnabled() for action in window.write_actions)
    window.close()
    wait_preview(window)
    wait_directory(window)
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()} == before
    application.processEvents()


def test_preview_switch_and_close_cancel_active_process(tmp_path, sample):
    application = QApplication.instance() or QApplication([])
    (tmp_path / "code.txt").write_text("read only", encoding="utf-8")
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("cancel-preview"),
                        inventory_service=FakeService(parse(sample)))
    window.show()
    wait_scan(window)
    win_id = window.inventory.partitions[2].id
    bind_test_root(window, win_id, tmp_path)
    window.partitions = {p.id: p for p in window.source.partitions()}
    window.navigate(VirtualPath(win_id))
    wait_directory(window)
    index = next(window.proxy.index(i, 0) for i in range(window.proxy.rowCount()) if window.proxy.index(i, 0).data() == "code.txt")
    window.table.setCurrentIndex(index)
    stale_id = window.preview_request_id
    window.navigate(VirtualPath(window.inventory.partitions[0].id))
    wait_preview(window)
    window.preview_failed(stale_id, "STALE ERROR")
    assert "STALE" not in window.preview_panel.message.text()
    window.navigate(VirtualPath(win_id))
    wait_directory(window)
    index = next(window.proxy.index(i, 0) for i in range(window.proxy.rowCount()) if window.proxy.index(i, 0).data() == "code.txt")
    window.table.setCurrentIndex(index)
    assert window.preview_worker is not None
    window.close()
    wait_preview(window)
    assert not window.isVisible()
    application.processEvents()


def test_invalid_thumbnail_result_is_friendly():
    import base64
    import struct
    from app.ui.preview_panel import PreviewPanel
    application = QApplication.instance() or QApplication([])
    panel = PreviewPanel()
    result = PreviewResult("image", "fixture", "bad.png", 1, "", "Windows", image_png="invalid-base64")
    panel.show_result(result, TEXT_LIMIT)
    assert "缩略图无法显示" in panel.message.text()
    from dataclasses import replace
    fake = b"\x89PNG\r\n\x1a\n" + bytes(4) + b"IHDR" + struct.pack(">II", 30000, 30000)
    panel.show_result(replace(result, image_png=base64.b64encode(fake).decode()), TEXT_LIMIT)
    assert "缩略图无法显示" in panel.message.text()
    assert panel.pixmap.isNull()
    panel.close()
    application.processEvents()
