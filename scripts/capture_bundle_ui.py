"""Developer-only screenshot using a disposable synthetic image, never real devices."""
import logging
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tests"))

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox
from app.ui.main_window import MainWindow
from app.core.config import AppConfig, ConfigStore
from app.core.browser import Location
from ext4_fixture import make_image
from test_inventory import sample, parse
from test_inventory_ui import FakeService, wait_scan
from test_native_ui import wait_directory
from test_bundle_ui import wait_bundle


def main():
    app=QApplication.instance() or QApplication([])
    if not QFontDatabase.families():
        font=QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
        if font<0:raise RuntimeError("Screenshot requires a CJK font")
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0],10))
    workspace=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="bundle-layout-",dir=workspace) as temporary:
        root=Path(temporary).resolve()
        assert root.is_relative_to(workspace)
        image=make_image(root/"preview.img")
        window=MainWindow(AppConfig(),ConfigStore(root/"config.json"),logging.getLogger("bundle-layout"),
                          inventory_service=FakeService(parse(sample.__wrapped__())))
        window.show();wait_scan(window)
        partition=next(iter(window.source.ext4));window.source.ext4[partition]["image"]=str(image)
        window.navigate(Location(partition,"home/demo"));wait_directory(window)
        window.configure_bundle();dialog=window.bundle_dialogs[partition];wait_bundle(dialog)
        source=root/"new.txt";source.write_bytes(b"preview content")
        dialog.start("create_file",path="notes.txt",source=str(source),metadata=dict(uid=1000,gid=1000,mode=420));wait_bundle(dialog)
        dialog.start("mkdir",path="documents",metadata=dict(uid=1000,gid=1000,mode=493));wait_bundle(dialog)
        app.processEvents()
        output=workspace/"docs/screenshots/phase6-bundle-panel.png"
        assert dialog.grab().save(str(output))
        # Only the known synthetic test draft is discarded here.
        dialog.exported_id=dialog.bundle_id
        dialog.close();window.close();app.processEvents()
        print(output)


if __name__=="__main__":main()
