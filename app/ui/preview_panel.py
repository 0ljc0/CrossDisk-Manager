"""纯文本/缩略图只读展示；没有编辑、执行或外部打开按钮。"""

import base64
import binascii
import struct

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase, QPixmap
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from app.core.preview import ENCODINGS, MAX_TEXT_LIMIT, PreviewResult


class PreviewPanel(QWidget):
    encoding_changed = Signal()
    more_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("只读预览"))
        controls = QHBoxLayout()
        self.encoding = QComboBox()
        self.encoding.addItems(["自动编码", *ENCODINGS[1:]])
        self.encoding.setToolTip("手选编码会重新只读加载；不会修改源文件编码")
        self.encoding.currentIndexChanged.connect(lambda: self.encoding_changed.emit())
        controls.addWidget(self.encoding)
        self.more = QPushButton("查看更多")
        self.more.clicked.connect(self.more_requested)
        controls.addWidget(self.more)
        layout.addLayout(controls)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        self.pages = QStackedWidget()
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.setMaximumBlockCount(41000)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.pages.addWidget(self.text)
        self.pages.addWidget(self.image)
        layout.addWidget(self.pages)
        self.pixmap = QPixmap()
        self.clear()

    def clear(self, message: str = "选择普通文件以预览") -> None:
        self.text.clear()
        self.image.clear()
        self.pixmap = QPixmap()
        self.pages.setCurrentWidget(self.text)
        self.message.setText(message)
        self.message.setToolTip("")
        self.more.setEnabled(False)
        self.encoding.setEnabled(False)

    def show_result(self, result: PreviewResult, byte_limit: int, partition_name: str = "") -> None:
        self.clear()
        self.message.setToolTip(result.partition_id)
        message = result.message + ("\n已达到本次预览安全上限" if result.truncated and byte_limit >= MAX_TEXT_LIMIT else "")
        self.message.setText(message + f"\n来源：{result.backend_source} · {partition_name or result.partition_id}\n相对路径：{result.relative_path}\n大小：{result.size} B · 修改：{result.modified}\n只读" +
                             (f" · 编码：{result.encoding}" if result.encoding else ""))
        if result.kind == "text":
            self.text.setPlainText(result.text)
        elif result.kind == "image":
            try:
                if len(result.image_png) > 6 * 1024 * 1024:
                    raise ValueError("缩略图过大")
                raw = base64.b64decode(result.image_png, validate=True)
                if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
                    raise ValueError("缩略图头无效")
                width, height = struct.unpack_from(">II", raw, 16)
                if not (0 < width <= 1024 and 0 < height <= 768) or len(raw) > 4 * 1024 * 1024:
                    raise ValueError("缩略图超出安全边界")
                valid = self.pixmap.loadFromData(raw, "PNG")
            except (ValueError, binascii.Error, struct.error):
                valid = False
            if not valid:
                self.message.setText("缩略图无法显示")
                return
            self.pages.setCurrentWidget(self.image)
            self.resize_image()
        self.encoding.setEnabled(result.kind == "text")
        self.more.setEnabled(result.kind == "text" and result.truncated and byte_limit < MAX_TEXT_LIMIT)

    def resize_image(self) -> None:
        if not self.pixmap.isNull():
            self.image.setPixmap(self.pixmap.scaled(self.image.size().boundedTo(self.pixmap.size()), Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resize_image()
