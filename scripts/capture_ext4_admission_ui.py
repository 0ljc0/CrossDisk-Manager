"""任务11：仅用普通合成镜像验证禁用状态与只读浏览。"""
import hashlib
import logging
from pathlib import Path
import sys
import tempfile
from PySide6.QtWidgets import QApplication
from app.core.browser import Location
from app.core.config import AppConfig, ConfigStore
from app.core.ext4_write import EXT4_WRITE_DISABLED
from app.ui.main_window import MainWindow


def main():
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project / 'tests'))
    from ext4_fixture import make_image
    from test_inventory import sample, parse
    from test_inventory_ui import FakeService, wait_scan
    from test_native_ui import wait_directory
    application = QApplication([])
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        image = make_image(directory / 'readonly.ext4')
        before = hashlib.sha256(image.read_bytes()).digest()
        window = MainWindow(AppConfig(window_width=1500, window_height=850), ConfigStore(directory / 'config.json'),
            logging.getLogger('ext4-admission'), inventory_service=FakeService(parse(sample.__wrapped__())))
        window.show()
        wait_scan(window)
        identifier = window.inventory.partitions[5].id
        window.source.ext4[identifier]['image'] = str(image)
        window.navigate(Location(identifier, 'home'))
        wait_directory(window)
        assert EXT4_WRITE_DISABLED in window.properties.text()
        assert not window.windows_write_action.isEnabled()
        assert all(not a.isEnabled() for a in window.write_actions)
        window.grab().save(str(project / 'docs/screenshots/task11-readonly.png'))
        assert hashlib.sha256(image.read_bytes()).digest() == before
        window.close()
        print('ext4-image readonly browsing and disabled write UI passed; SHA-256 unchanged; no real Ubuntu access.')


if __name__ == '__main__':
    main()
