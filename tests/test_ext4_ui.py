"""GUI 通过真实子进程浏览镜像；不触碰真实物理分区。"""

import logging
from dataclasses import replace

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.config import AppConfig, ConfigStore
from app.core.browser import Location
from app.ui.main_window import MainWindow
from ext4_fixture import make_image, SAMPLE
from scripts.ext4_readonly import validate_sample
from app.backends.ext4_readonly import Ext4ReadOnlyBackend
from test_inventory import sample, parse
from test_inventory_ui import FakeService, wait_scan
from test_native_ui import wait_directory


def test_ext4_image_gui_and_sample_export(tmp_path, sample):
    application = QApplication.instance() or QApplication([])
    image = make_image(tmp_path / "ext4-test.img")
    window = MainWindow(AppConfig(), ConfigStore(tmp_path / "config.json"), logging.getLogger("ext4-ui"),
                        inventory_service=FakeService(parse(sample)))
    window.show()
    wait_scan(window)
    partition_id = next(iter(window.source.ext4))
    window.source.ext4[partition_id]["image"] = str(image)
    window.navigate(Location(partition_id))
    wait_directory(window)
    assert not window.load_failed
    assert window.file_model.entries[0].name == "home"
    assert window.source.ext4[partition_id]["fingerprint"]
    assert "ext4 UUID" in window.properties.text()
    window.address.setText("/home")
    window.address.returnPressed.emit()
    wait_directory(window)
    assert window.file_model.entries[0].name == "demo"
    window.navigate(Location(partition_id, "home/demo"))
    wait_directory(window)
    assert len(window.file_model.entries) == 3
    window.hidden_action.setChecked(True)
    wait_directory(window)
    assert len(window.file_model.entries) == 4
    link = next(window.proxy.index(i, 0) for i in range(window.proxy.rowCount())
                if window.proxy.index(i, 0).data() == "loop")
    window.table.doubleClicked.emit(link)
    assert "禁止" in window.statusBar().currentMessage()
    assert all(not action.isEnabled() for action in window.write_actions)
    window.close()
    wait_directory(window)
    application.processEvents()
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        count, digest = validate_sample(backend, "home/demo/sample.txt")
        assert count == len(SAMPLE) and len(digest) == 64
