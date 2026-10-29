"""只读后端验证；测试数据只在可丢弃临时目录中准备。"""

import ctypes
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from app.backends.windows_native import NativeWindowsBackend, normalize_root, validate_relative, readable_error
from app.backends.inventory_browser import InventoryBrowserSource
from test_inventory import sample, parse


@pytest.fixture
def backend(tmp_path):
    (tmp_path / "中文 空格").mkdir()
    (tmp_path / "中文 空格" / "说明.txt").write_bytes("只读样本".encode())
    return NativeWindowsBackend("test-partition", str(tmp_path))


def test_list_stat_and_read_only_stream(backend):
    page = backend.list_dir()
    assert page.entries[0].name == "中文 空格"
    assert page.entries[0].is_directory
    info = backend.stat("中文 空格/说明.txt")
    assert info.size == len("只读样本".encode())
    assert not info.is_directory
    with backend.open_read("中文 空格/说明.txt") as stream:
        assert stream.read() == "只读样本".encode()
        assert stream.readable() and not stream.writable()
    assert backend.get_capabilities().write is False
    assert not hasattr(backend, "unlink") and not hasattr(backend, "write_text")


@pytest.mark.parametrize("path", ["../x", "a/../x", "/x", "C:/x", "a\\b", "a//b", "x:stream",
                                  "CON", "NUL.txt", "COM1.log", "a.", "a ", "a\x00b"])
def test_relative_boundaries(backend, path):
    with pytest.raises(ValueError):
        backend.list_dir(path)


@pytest.mark.parametrize("root", [r"\\.\PhysicalDrive0", r"\\?\GLOBALROOT\Device\Harddisk0",
                                  r"\\.\C:", "C:", "relative", r"\\server\IPC$", r"\\server\C$"])
def test_device_roots_rejected(root):
    with pytest.raises(ValueError):
        normalize_root(root)


def test_root_formats():
    assert normalize_root("C:\\Users").startswith("\\\\?\\C:")
    assert normalize_root(r"\\server\share") == "\\\\?\\UNC\\server\\share\\"
    assert normalize_root("\\\\?\\Volume{12345678-1234-1234-1234-123456789abc}\\").startswith("\\\\?\\Volume{")


def test_hidden_attribute_and_link_metadata(backend, tmp_path):
    hidden = tmp_path / "隐藏.txt"
    hidden.write_bytes(b"sample")
    set_attributes = ctypes.windll.kernel32.SetFileAttributesW
    set_attributes.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    assert set_attributes(str(hidden), 2)
    assert "隐藏.txt" not in {e.name for e in backend.list_dir().entries}
    assert "隐藏.txt" in {e.name for e in backend.list_dir(show_hidden=True).entries}
    info = SimpleNamespace(st_file_attributes=0x400, st_mode=stat.S_IFDIR | stat.S_IREAD,
                           st_size=0, st_mtime=0)
    assert backend._entry("循环链接", info).is_link


def test_paging_and_directory_change(backend, tmp_path):
    for i in range(420):
        (tmp_path / f"file-{i}.txt").touch()
    first = backend.list_dir(page_size=200)
    assert len(first.entries) == 200 and first.next_offset == 200
    second = backend.list_dir(offset=first.next_offset, fingerprint=first.fingerprint)
    third = backend.list_dir(offset=second.next_offset, fingerprint=first.fingerprint)
    assert len(third.entries) == 21 and third.next_offset is None
    names = [e.name for e in first.entries + second.entries + third.entries]
    assert len(names) == len(set(names)) == 421
    with pytest.raises(ValueError, match="发生变化"):
        backend.list_dir(offset=200, fingerprint="obsolete")


def test_long_path(backend, tmp_path):
    root = Path(normalize_root(str(tmp_path)))
    parts = ["中文长目录" * 8] * 5
    deep = root.joinpath(*parts)
    deep.mkdir(parents=True)
    (deep / "样本.txt").write_bytes(b"read-only")
    relative = "/".join(parts + ["样本.txt"])
    assert len(str(deep)) > 260
    assert backend.stat(relative).size == 9
    with backend.open_read(relative) as stream:
        assert stream.read() == b"read-only"


def test_link_loop_blocked(backend, tmp_path):
    try:
        (tmp_path / "循环").symlink_to(tmp_path, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"当前令牌不能创建测试符号链接：{getattr(exc, 'winerror', None)}")
    assert backend.stat("循环").is_link
    with pytest.raises(ValueError, match="链接"):
        backend.list_dir("循环")
    with pytest.raises(ValueError, match="链接"):
        with backend.open_read("循环/中文 空格/说明.txt"):
            pytest.fail("不应跟随链接")


def test_missing_and_error_mapping(backend, monkeypatch):
    with pytest.raises(FileNotFoundError):
        backend.list_dir("不存在")
    assert "访问被拒绝" in readable_error(PermissionError())
    assert "不存在" in readable_error(FileNotFoundError())
    sharing = OSError()
    sharing.winerror = 32
    assert "被占用" in readable_error(sharing)
    monkeypatch.setattr(backend, "_handle", lambda *a, **kw: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(PermissionError):
        backend.list_dir()


def test_exclusively_locked_file_is_not_bypassed(backend, tmp_path):
    from ctypes import wintypes
    path = str(tmp_path / "中文 空格" / "说明.txt")
    create = ctypes.windll.kernel32.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = ctypes.windll.kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    handle = create(path, 0x80000000, 0, None, 3, 0, None)  # 只读独占句柄，无写权限。
    assert handle != ctypes.c_void_p(-1).value
    try:
        with pytest.raises(OSError) as caught:
            with backend.open_read("中文 空格/说明.txt"):
                pytest.fail("不应绕过文件锁")
        assert "被占用" in readable_error(caught.value)
    finally:
        close(handle)


def test_inventory_binding_and_address_routing(sample):
    volume = "\\\\?\\Volume{12345678-aaaa-bbbb-cccc-123456789abc}\\"
    sample["Volumes"][0]["Path"] = volume
    source = InventoryBrowserSource(parse(sample))
    location = source.resolve_address("C:\\用户 资料")
    assert source.roots[location.partition_id] == volume
    assert location.relative_path == "用户 资料"
    assert source.resolve_address(volume + "Users").partition_id == location.partition_id
    assert all(not p.writable for p in source.partitions())
    assert sum(p.browsable for p in source.partitions()) == 2  # Windows 卷和需探测的 Linux 候选。
    unc = source.resolve_address(r"\\server\share\中文目录")
    assert unc.relative_path == "中文目录" and unc.partition_id.startswith("unc-")
    with pytest.raises(ValueError):
        source.resolve_address(r"C:\..\Windows")
    with pytest.raises(ValueError):
        source.resolve_address(r"\\.\PhysicalDrive0")
