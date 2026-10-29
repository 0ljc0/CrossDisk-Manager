"""界面视觉检查：从项目根目录执行 python -m scripts.capture_mock_ui。"""

import logging
import tempfile
from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.config import AppConfig, ConfigStore
from app.ui.main_window import MainWindow


def main() -> None:
    application = QApplication([])
    output = Path("docs/screenshots")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        window = MainWindow(AppConfig(), ConfigStore(Path(temporary) / "config.json"),
                            logging.getLogger("visual-check"))
        window.show()
        for name, width, height, theme in (
            ("task02-default", 1000, 680, "light"),
            ("task02-1080p", 1920, 1080, "light"),
            ("task02-2k", 2560, 1440, "dark"),
            ("task02-4k", 3840, 2160, "light"),
        ):
            window.set_theme(theme)
            window.resize(width, height)
            QTest.qWait(180)
            image = window.grab()
            assert image.save(str(output / f"{name}.png"))
            print(f"{name}: requested logical={width}x{height}, actual image={image.width()}x{image.height()} (DPR={image.devicePixelRatio()})")
        window.close()
        application.processEvents()


if __name__ == "__main__":
    main()
