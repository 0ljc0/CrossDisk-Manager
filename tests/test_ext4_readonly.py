"""真实 pytsk3 + 合成普通镜像；不自动读取任何真实 Ubuntu 分区。"""

from dataclasses import asdict, replace
import hashlib
import struct
import zlib
from uuid import UUID
from types import SimpleNamespace

import pytest

from app.backends.ext4_readonly import Ext4ReadOnlyBackend, Ext4Error, verify_identity
from ext4_fixture import make_image, SAMPLE
from test_inventory import sample, parse


@pytest.fixture
def image(tmp_path):
    return make_image(tmp_path / "ext4-test.img")


def test_real_image_root_home_and_stream(image, tmp_path):
    before = hashlib.sha256(image.read_bytes()).hexdigest()
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        assert backend.probe["filesystem"] == "ext4"
        assert backend.probe["label"] == "CDM-TEST"
        assert [e.name for e in backend.list_dir().entries] == ["home"]
        assert [e.name for e in backend.list_dir("home").entries] == ["demo"]
        assert "中文 空格.txt" in [e.name for e in backend.list_dir("home/demo").entries]
        assert not any(e.name in (".", "..") for e in backend.list_dir().entries)
        assert backend.stat("home/demo/sample.txt").size == len(SAMPLE)
        assert backend.stat("home/demo/sample.txt").writable  # Unix 属性与后端只读能力分离。
        assert backend.get_capabilities().read and not backend.get_capabilities().write
        assert all(not hasattr(backend, name) for name in ("write", "rename", "remove"))
        destination = tmp_path / "new-export.txt"
        digest = hashlib.sha256()
        with backend.open_read("home/demo/sample.txt") as stream, destination.open("xb") as target:
            assert not stream.writable()
            while chunk := stream.read(7):
                digest.update(chunk)
                target.write(chunk)
        assert destination.read_bytes() == SAMPLE
        assert digest.hexdigest() == hashlib.sha256(SAMPLE).hexdigest()
        with pytest.raises(FileExistsError):
            destination.open("xb")
    assert hashlib.sha256(image.read_bytes()).hexdigest() == before
    backend.close()  # 幂等。
    with pytest.raises(Ext4Error, match="已关闭"):
        backend.stat()
    image.rename(tmp_path / "released.img")  # 无残留镜像句柄。


def test_links_hidden_and_paging(image):
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        page = backend.list_dir("home/demo", page_size=2)
        other = backend.list_dir("home/demo", offset=page.next_offset, fingerprint=page.fingerprint)
        assert len(page.entries + other.entries) == 3
        assert any(e.name == ".hidden" for e in backend.list_dir("home/demo", show_hidden=True).entries)
        assert backend.stat("home/demo/loop").is_link
        for path in ("home/demo/loop", "home/demo/loop/sample.txt"):
            with pytest.raises(Ext4Error):
                backend.list_dir(path)
            with pytest.raises(Ext4Error):
                with backend.open_read(path):
                    pytest.fail("不能跟随链接")
        with pytest.raises(Ext4Error, match="已变化"):
            backend.list_dir("home/demo", fingerprint="obsolete")


@pytest.mark.parametrize("path", ["../etc", "home/../etc", "/home", "home//demo", "home\\demo", "home\x00"])
def test_path_boundaries(image, path):
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        with pytest.raises(Ext4Error):
            backend.list_dir(path)


@pytest.mark.parametrize("change", ["luks", "lvm", "unknown", "encryption", "unclean", "bounds"])
def test_unsupported_format_rejected(image, change):
    data = bytearray(image.read_bytes())
    if change == "luks":
        data[:6] = b"LUKS\xba\xbe"
    elif change == "lvm":
        data[512:520] = b"LABELONE"
    elif change == "unknown":
        data[1080:1082] = b"\x00\x00"
    elif change == "encryption":
        struct.pack_into("<I", data, 1024 + 96, 0x10042)
    elif change == "unclean":
        struct.pack_into("<H", data, 1024 + 58, 2)
    else:
        struct.pack_into("<I", data, 1024 + 4, 2**31)
    image.write_bytes(data)
    with pytest.raises(Ext4Error):
        Ext4ReadOnlyBackend.from_image(str(image))
    image.rename(image.with_suffix(".released"))


def test_filesystem_label_change_rejected(image):
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        identity = backend.probe["fingerprint"]
    data = bytearray(image.read_bytes())
    data[1024 + 120] = ord("X")
    image.write_bytes(data)
    with pytest.raises(Ext4Error, match="卷标"):
        Ext4ReadOnlyBackend.from_image(str(image), expected_fs=identity)


def test_partition_offset_image_bounds(image, tmp_path):
    content = image.read_bytes()
    container = tmp_path / "offset.img"
    container.write_bytes(bytes(1024 * 1024) + content)
    with Ext4ReadOnlyBackend.from_image(str(container), offset=1024 * 1024, size=len(content)) as backend:
        assert backend.stat("home/demo/sample.txt").size == len(SAMPLE)
        with pytest.raises(OSError):
            backend.bounded.read(0, 512)
        with pytest.raises(OSError):
            backend.bounded.read(1024 * 1024 + len(content) - 1, 512)


def test_identity_changes_rejected_before_device_open(sample, monkeypatch):
    inventory = parse(sample)
    expected = dict(disk=asdict(inventory.disks[0]), partition=asdict(inventory.partitions[5]))
    disk, part = verify_identity(expected, inventory)
    assert part.gpt_type == expected["partition"]["gpt_type"]
    for field, value in (("offset", part.offset + 1024), ("label", "changed"), ("guid", "changed")):
        modified = replace(inventory, partitions=tuple(replace(p, **{field: value}) if p.id == part.id else p
                                                      for p in inventory.partitions))
        with pytest.raises(Ext4Error):
            verify_identity(expected, modified)
    with pytest.raises(Ext4Error):
        verify_identity(expected, replace(inventory, disks=()))
    renumbered = replace(inventory, disks=(replace(disk, number=8),),
                         partitions=tuple(replace(p, disk_number=8, number=p.number + 10) for p in inventory.partitions))
    assert verify_identity(expected, renumbered)[0].number == 8
    import pytsk3
    monkeypatch.setattr(pytsk3, "Img_Info", lambda *a, **kw: pytest.fail("错盘时不得打开设备"))
    with pytest.raises(Ext4Error):
        Ext4ReadOnlyBackend.from_partition(expected, service=SimpleNamespace(scan=lambda: replace(inventory, disks=())))


def test_corrupt_inode_and_failed_read(image):
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        assert backend._entry("bad", SimpleNamespace(info=SimpleNamespace(meta=None))).error
        with pytest.raises(Ext4Error, match="不存在"):
            backend.stat("home/missing")
        with backend.open_read("home/demo/sample.txt") as stream:
            stream.raw.file_object = SimpleNamespace(read_random=lambda *a: b"")
            with pytest.raises(Ext4Error, match="提前结束"):
                stream.read(10)


@pytest.mark.parametrize("device", [r"\\.\PhysicalDrive0", r"\\?\GLOBALROOT\Device\Harddisk0", r"\\?\Volume{12345678-1234-1234-1234-123456789abc}"])
def test_direct_device_open_is_forbidden(device):
    with pytest.raises(Ext4Error, match="身份复核"):
        Ext4ReadOnlyBackend(device, 0, 4096)


@pytest.mark.parametrize("sector", [512, 4096])
def test_opened_device_gpt_identity_check(sector):
    from app.services.disk_inventory import LINUX_DATA
    disk = SimpleNamespace(size=8 * 1024 * 1024, guid="12345678-1234-1234-1234-123456789abc")
    part = SimpleNamespace(offset=1024 * 1024, size=4 * 1024 * 1024,
                           guid="11111111-2222-3333-4444-555555555555", gpt_type=LINUX_DATA)
    raw = bytearray(disk.size)
    table = bytearray(128 * 128)
    table[:16] = UUID(LINUX_DATA).bytes_le
    table[16:32] = UUID(part.guid).bytes_le
    struct.pack_into("<QQ", table, 32, part.offset // sector, (part.offset + part.size) // sector - 1)
    raw[2 * sector:2 * sector + len(table)] = table
    header = bytearray(sector)
    header[:8] = b"EFI PART"
    struct.pack_into("<II", header, 8, 0x10000, 92)
    struct.pack_into("<Q", header, 40, 1024 * 1024 // sector)
    header[56:72] = UUID(disk.guid).bytes_le
    struct.pack_into("<QIII", header, 72, 2, 128, 128, zlib.crc32(table))
    struct.pack_into("<I", header, 16, zlib.crc32(header[:92]))
    raw[sector:2 * sector] = header
    image = SimpleNamespace(get_size=lambda: disk.size, read=lambda offset, size: bytes(raw[offset:offset + size]))
    Ext4ReadOnlyBackend._verify_gpt(image, disk, part)
    part.offset += sector
    with pytest.raises(Ext4Error, match="疑似错盘"):
        Ext4ReadOnlyBackend._verify_gpt(image, disk, part)
    part.offset -= sector
    raw[2 * sector] ^= 1
    with pytest.raises(Ext4Error, match="校验和"):
        Ext4ReadOnlyBackend._verify_gpt(image, disk, part)
