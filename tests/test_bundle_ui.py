import hashlib
import logging
import struct
import time

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.config import AppConfig, ConfigStore
from app.core.browser import Location
from app.ui.main_window import MainWindow
from ext4_fixture import make_image
from test_inventory import sample, parse
from test_inventory_ui import FakeService, wait_scan
from test_native_ui import wait_directory
from scripts.validate_bundle import check


def wait_bundle(dialog):
    deadline=time.monotonic()+10
    while dialog.worker and time.monotonic()<deadline:QTest.qWait(10)
    assert dialog.worker is None


def test_gui_stages_exports_marks_and_discards_without_touching_image(tmp_path,sample,monkeypatch):
    app=QApplication.instance() or QApplication([])
    image=make_image(tmp_path/"test.img")
    raw=bytearray(image.read_bytes())
    for inode in (14,15,16):
        pos=5*1024+(inode-1)*256
        struct.pack_into("<H",raw,pos+2,1000);struct.pack_into("<H",raw,pos+24,1000)
    image.write_bytes(raw);before=hashlib.sha256(raw).hexdigest()
    window=MainWindow(AppConfig(),ConfigStore(tmp_path/"config.json"),logging.getLogger("bundle-ui"),
                      inventory_service=FakeService(parse(sample)))
    window.show();wait_scan(window)
    partition=next(iter(window.source.ext4));window.source.ext4[partition]["image"]=str(image)
    window.navigate(Location(partition,"home/demo"));wait_directory(window)
    assert window.bundle_action.isEnabled()
    window.configure_bundle();dialog=window.bundle_dialogs[partition];wait_bundle(dialog)
    assert dialog.backend and "尚未" in dialog.status.text()
    local=tmp_path/"content.txt";local.write_bytes(b"pending text")
    dialog.start("replace_file",path="sample.txt",source=str(local));wait_bundle(dialog)
    assert len(dialog.operations)==1
    row=next(i for i,e in enumerate(window.file_model.entries) if e.name=="sample.txt")
    assert "待修改" in window.file_model.index(row,5).data()
    assert all(not action.isEnabled() for action in window.write_actions)
    dialog.start("create_file",path="new.txt",source=str(local),metadata=dict(uid=1000,gid=1000,mode=420));wait_bundle(dialog)
    assert dialog.table.rowCount()==2
    dialog.start("export",destination=str(tmp_path/"export"));wait_bundle(dialog)
    assert check(tmp_path/"export")["package_valid"]
    assert dialog.exported_id==dialog.bundle_id
    # A rejected operation keeps the existing draft and marks an actionable error.
    dialog.start("create_file",path="../escape",source=str(local),metadata=dict(uid=1000,gid=1000,mode=420));wait_bundle(dialog)
    assert len(dialog.operations)==2 and "未暂存" in dialog.status.text()
    dialog.start("cancel",id=dialog.operations[0]["id"]);wait_bundle(dialog)
    assert "待修改" not in window.file_model.index(row,5).data()
    monkeypatch.setattr(QMessageBox,"question",lambda *a,**k:QMessageBox.StandardButton.No)
    assert not dialog.close()  # Unsaved draft cannot silently disappear.
    monkeypatch.setattr(QMessageBox,"question",lambda *a,**k:QMessageBox.StandardButton.Yes)
    assert dialog.close() and not window.bundle_dialogs
    window.close();app.processEvents()
    assert hashlib.sha256(image.read_bytes()).hexdigest()==before


def test_demo_has_no_ext4_staging_entry(tmp_path):
    app=QApplication.instance() or QApplication([])
    window=MainWindow(AppConfig(),ConfigStore(tmp_path/"demo.json"),logging.getLogger("bundle-demo"))
    assert not window.bundle_action.isEnabled()
    window.close();app.processEvents()
