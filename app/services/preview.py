"""只使用后端 open_read；不执行内容、不写源缓存、不使用系统文件关联。"""

import base64
import codecs
from pathlib import PurePosixPath

from app.core.preview import (ENCODINGS, IMAGE_LIMIT, MAX_PIXELS, MAX_TEXT_LIMIT, TEXT_LIMIT, TEXT_TYPES, PreviewResult)
from app.core.virtual_path import VirtualPath
from app.core.capability_policy import CapabilityPolicy
from app.services.backend_access import open_backend

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def image_format(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"BM"):
        return "bmp"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return ""


def decode_text(data: bytes, encoding: str, truncated: bool) -> tuple[str, str]:
    if encoding not in ENCODINGS:
        raise ValueError("不支持的文本编码")
    if data.startswith((b"MZ", b"\x7fELF", b"PK\x03\x04", b"%PDF")) or image_format(data):
        raise ValueError("文件头表明这是二进制文件，拒绝按文本展示")
    selected = encoding
    if selected == "auto":
        if data.startswith(codecs.BOM_UTF8):
            selected = "utf-8-sig"
        elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            selected = "utf-16"
        else:
            head = data[:4096]
            even, odd = head[::2], head[1::2]
            if odd and odd.count(0) / len(odd) > 0.3 and even.count(0) / max(1, len(even)) < 0.1:
                selected = "utf-16-le"
            elif even and even.count(0) / len(even) > 0.3 and odd.count(0) / max(1, len(odd)) < 0.1:
                selected = "utf-16-be"
            else:
                selected = "utf-8"
    try:
        # 截断在多字节字符中间时保留完整字符，不把边界半个字符当损坏文件。
        text = codecs.getincrementaldecoder(selected)(errors="strict").decode(data, final=not truncated)
    except UnicodeError as exc:
        raise ValueError("文本编码无法确认或内容损坏，可手选正确编码重试；二进制文件不会强制转为文本") from exc
    if "\x00" in text or sum(ord(c) < 32 and c not in "\n\r\t\f" for c in text) > max(0, len(text) // 100):
        raise ValueError("检测到二进制控制字符，不直接显示为文本")
    return text.lstrip("\ufeff"), selected


def thumbnail(data: bytes) -> str:
    import os
    # Qt 环境变量可覆盖 allocationLimit，子进程固定为安全值。
    os.environ["QT_IMAGEIO_MAXALLOC"] = "64"
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
    from PySide6.QtGui import QImageReader
    QImageReader.setAllocationLimit(64)
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    reader.setDecideFormatFromContent(True)
    size = reader.size()
    if (not size.isValid() or size.width() > 16384 or size.height() > 16384
            or size.width() * size.height() > MAX_PIXELS):
        raise ValueError("图片损坏、尺寸未知或超过像素安全上限，停止解码")
    if size.width() > 1024 or size.height() > 768:
        reader.setScaledSize(size.scaled(QSize(1024, 768), Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError("图片损坏或当前 Qt 解码器不支持该格式")
    output = QBuffer()
    output.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(output, "PNG") or output.size() > 4 * 1024 * 1024:
        raise ValueError("无法生成安全大小的图片缩略图")
    return base64.b64encode(bytes(output.data())).decode("ascii")


def query_preview(request: dict) -> PreviewResult:
    path = VirtualPath(request["partition_id"], request["relative_path"])
    limit = request.get("byte_limit", TEXT_LIMIT)
    if type(limit) is not int or not TEXT_LIMIT <= limit <= MAX_TEXT_LIMIT:
        raise ValueError("文本预览读取上限无效")
    encoding = request.get("encoding", "auto")
    if encoding not in ENCODINGS:
        raise ValueError("不支持的文本编码")
    with open_backend(request, operation="open_read") as backend:
        if not backend.get_capabilities().stat:
            raise ValueError("后端不能提供安全预览需要的文件属性")
        entry = backend.stat(path.path)
        reason = CapabilityPolicy().entry_reason(entry, entry.backend_source)
        if reason:
            raise ValueError(reason)
        if entry.is_directory is not False or entry.size is None or entry.size < 0:
            raise ValueError("只能预览大小已知的普通文件")
        metadata = dict(partition_id=path.partition_id, relative_path=path.path, size=entry.size,
                        modified=entry.modified, backend_source=entry.backend_source)
        extension = PurePosixPath(path.path).suffix.lower()
        if extension not in TEXT_TYPES | IMAGE_TYPES:
            return PreviewResult("unsupported", **metadata, message="不支持此文件类型；仅展示属性，不执行或外部打开")
        with backend.open_read(path.path) as stream:
            header = stream.read(4096)
            if extension in IMAGE_TYPES:
                if not image_format(header):
                    return PreviewResult("unsupported", **metadata, bytes_read=len(header), message="图片文件头不匹配或已损坏")
                if entry.size > IMAGE_LIMIT:
                    return PreviewResult("unsupported", **metadata, bytes_read=len(header), message="图片超过 16 MiB 数据上限，未加载完整图片")
                data = header + stream.read(max(0, IMAGE_LIMIT + 1 - len(header)))
                if len(data) > IMAGE_LIMIT:
                    raise ValueError("图片在读取期间变大，超过安全上限")
                return PreviewResult("image", **metadata, image_png=thumbnail(data), bytes_read=len(data), message="只读图片缩略图")
            data = header + stream.read(max(0, limit + 1 - len(header)))
        truncated = entry.size > limit or len(data) > limit
        text, selected = decode_text(data[:limit], encoding, truncated)
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n").replace("\u2029", "\n")
        factor = limit // TEXT_LIMIT
        display_limit = 250_000 * factor
        if len(text) > display_limit:
            text, truncated = text[:display_limit], True
        position = 0
        for _ in range(10_000 * factor):
            position = text.find("\n", position)
            if position < 0:
                break
            position += 1
        else:
            if position < len(text):
                text, truncated = text[:position], True
        message = "预览已截断，可选择查看更多（仍受安全上限限制）" if truncated else "只读文本预览"
        return PreviewResult("text", **metadata, text=text, encoding=selected, truncated=truncated,
                             bytes_read=len(data), message=message)
