"""预览只读、字节/像素边界、编码、伪装二进制和真实 Qt 图片解码。"""

import base64
from dataclasses import asdict
import hashlib
import struct
import zlib

import pytest
from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QImageReader

from app.core.browser import Partition
from app.core.preview import TEXT_LIMIT, MAX_TEXT_LIMIT
from app.services.preview import query_preview, decode_text, thumbnail


def request(tmp_path, name, **options):
    part = Partition("test", "临时目录", "NTFS", "只读", True, False, "fixture", "普通数据", "Windows", str(tmp_path))
    return dict(partition_id="test", root=str(tmp_path), relative_path=name,
                backend_spec=dict(kind="Windows", partition=asdict(part)), **options)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"])
def test_text_encodings(encoding):
    text = "hello 中文\nread only"
    decoded, _ = decode_text(text.encode(encoding), "auto", False)
    assert decoded == text


def test_manual_encoding_and_binary_rejection():
    raw = "中文日志".encode("gb18030")
    with pytest.raises(ValueError, match="手选"):
        decode_text(raw, "auto", False)
    assert decode_text(raw, "gb18030", False)[0] == "中文日志"
    for raw in (b"MZexecutable", b"\x7fELFbinary", b"PK\x03\x04zip", b"a\0\1\2\3"):
        with pytest.raises(ValueError):
            decode_text(raw, "cp1252", False)


def test_preview_does_not_execute_write_or_create_source_cache(tmp_path):
    source = tmp_path / "sample.py"
    source.write_text("from pathlib import Path\nPath('SHOULD_NOT_EXIST').touch()\n", encoding="utf-8")
    before = source.read_bytes()
    listing = set(tmp_path.iterdir())
    result = query_preview(request(tmp_path, source.name))
    assert result.kind == "text" and "SHOULD_NOT_EXIST" in result.text
    assert result.read_only and source.read_bytes() == before
    assert set(tmp_path.iterdir()) == listing
    assert result.backend_source == "Windows" and result.relative_path == source.name


def test_large_text_has_bounded_prefix_and_explicit_more(tmp_path):
    source = tmp_path / "large.log"
    source.write_bytes(b"a" * (TEXT_LIMIT + 100))
    result = query_preview(request(tmp_path, source.name))
    assert result.truncated and "预览已截断" in result.message
    assert result.bytes_read <= TEXT_LIMIT + 1 and len(result.text) <= 250_000
    more = query_preview(request(tmp_path, source.name, byte_limit=TEXT_LIMIT * 2))
    assert len(more.text) == 500_000  # 明确提高展示和读取上限，不自动读取完整大文件。
    assert more.truncated
    with pytest.raises(ValueError, match="上限"):
        query_preview(request(tmp_path, source.name, byte_limit=MAX_TEXT_LIMIT + 1))


def test_unknown_and_disguised_binary(tmp_path):
    (tmp_path / "program.exe").write_bytes(b"MZ" + bytes(64))
    result = query_preview(request(tmp_path, "program.exe"))
    assert result.kind == "unsupported" and result.bytes_read == 0
    (tmp_path / "fake.txt").write_bytes(b"MZ" + bytes(64))
    with pytest.raises(ValueError, match="二进制"):
        query_preview(request(tmp_path, "fake.txt"))
    (tmp_path / "bad.png").write_bytes(b"not image")
    assert "文件头不匹配" in query_preview(request(tmp_path, "bad.png")).message
    from app.core.preview import IMAGE_LIMIT
    with (tmp_path / "large.png").open("wb") as fixture:
        fixture.write(b"\x89PNG\r\n\x1a\n")
        fixture.truncate(IMAGE_LIMIT + 1)
    large = query_preview(request(tmp_path, "large.png"))
    assert large.kind == "unsupported" and large.bytes_read <= 4096
    assert "数据上限" in large.message


@pytest.mark.parametrize("format", ["PNG", "JPEG", "BMP", "WEBP"])
def test_supported_qt_images(tmp_path, format):
    if format.lower().encode() not in [bytes(f) for f in QImageReader.supportedImageFormats()]:
        pytest.skip("本机 Qt 没有该图片解码插件")
    image = QImage(1200, 900, QImage.Format.Format_RGB32)
    image.fill(0xff336699)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, format)
    data = bytes(buffer.data())
    file = tmp_path / ("sample." + format.lower())
    file.write_bytes(data)
    result = query_preview(request(tmp_path, file.name))
    assert result.kind == "image"
    thumbnail_image = QImage.fromData(base64.b64decode(result.image_png), "PNG")
    assert thumbnail_image.width() <= 1024 and thumbnail_image.height() <= 768
    assert file.read_bytes() == data


def test_image_pixel_limit_before_decode():
    header = struct.pack(">IIBBBBB", 20000, 20000, 8, 2, 0, 0, 0)
    def chunk(name, payload):
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload))
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")
    with pytest.raises(ValueError, match="像素|尺寸"):
        thumbnail(data)


def test_text_boundary_preserves_complete_multibyte_characters():
    assert decode_text("中文".encode()[:-1], "auto", True)[0] == "中"


def test_win32_preview_handles_never_request_write_access(tmp_path, monkeypatch):
    import ctypes
    source = tmp_path / "readonly.md"
    source.write_bytes(b"read-only source")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    before_modified = source.stat().st_mtime_ns
    original_factory = ctypes.WinDLL
    calls = []
    class TrackedFunction:
        def __init__(self, function):
            object.__setattr__(self, "function", function)
        def __setattr__(self, name, value):
            setattr(self.function, name, value)
        def __getattr__(self, name):
            return getattr(self.function, name)
        def __call__(self, *args):
            calls.append(args)
            return self.function(*args)
    class TrackedKernel:
        def __init__(self, library):
            self.library = library
        def __getattr__(self, name):
            if name == "WriteFile":
                pytest.fail("预览不应调用 WriteFile")
            function = getattr(self.library, name)
            return TrackedFunction(function) if name == "CreateFileW" else function
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: TrackedKernel(original_factory(*a, **kw)))
    assert query_preview(request(tmp_path, source.name)).text == "read-only source"
    assert calls
    for args in calls:
        assert args[1] in (0x80, 0x80000000)  # FILE_READ_ATTRIBUTES 或 GENERIC_READ。
        assert args[4] == 3  # OPEN_EXISTING，禁止创建/覆盖。
        assert not args[5] & 0x04000000  # 不允许 DELETE_ON_CLOSE。
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert source.stat().st_mtime_ns == before_modified


def test_preview_checks_read_capability_and_partition_policy(tmp_path, monkeypatch, capsys):
    import io
    import json
    from app.core.browser import FileEntry, ReadOnlyCapabilities
    from app.services import backend_access
    class NoRead:
        def list_dir(self, *args, **kwargs):
            pytest.fail("不应读取目录")
        def stat(self, *args, **kwargs):
            pytest.fail("不应读取属性")
        def open_read(self, *args, **kwargs):
            pytest.fail("不能忽略 open_read=False")
        def get_capabilities(self):
            return ReadOnlyCapabilities(open_read=False)
    monkeypatch.setattr(backend_access, "NativeWindowsBackend", lambda *a, **kw: NoRead())
    with pytest.raises(ValueError, match="能力"):
        query_preview(request(tmp_path, "sample.txt"))
    class DeniedRead(NoRead):
        def get_capabilities(self):
            return ReadOnlyCapabilities()
        def stat(self, *args, **kwargs):
            return FileEntry("sample.txt", False, 1, is_link=False, backend_source="Windows")
        def open_read(self, *args, **kwargs):
            raise PermissionError("secret-source-path")
    monkeypatch.setattr(backend_access, "NativeWindowsBackend", lambda *a, **kw: DeniedRead())
    from app.jobs import native_query
    payload = dict(request(tmp_path, "sample.txt"), task="preview")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert native_query.main() == 0
    error = json.loads(capsys.readouterr().out)["error"]
    assert "访问被拒绝" in error and "secret-source-path" not in error
    protected = request(tmp_path, "sample.txt")
    protected["backend_spec"]["partition"]["category"] = "EFI"
    monkeypatch.setattr(backend_access, "NativeWindowsBackend", lambda *a, **kw: pytest.fail("EFI 不应构造后端"))
    with pytest.raises(ValueError, match="EFI"):
        query_preview(protected)


def test_carriage_return_line_limit_keeps_prefix(tmp_path):
    (tmp_path / "cr.log").write_bytes(b"first\r" + b"line\r" * 20000)
    result = query_preview(request(tmp_path, "cr.log"))
    assert result.truncated and result.text.startswith("first\n")
    assert result.text.count("\n") == 10000
