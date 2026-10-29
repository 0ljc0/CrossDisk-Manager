"""经过身份与格式检查的 pytsk3 只读访问；没有源写入接口。"""

import hashlib
import io
import re
import struct
import zlib
from uuid import UUID
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.core.browser import DirectoryPage, FileEntry, ReadOnlyCapabilities
from app.services.disk_inventory import DiskInventoryService, LINUX_DATA


class Ext4Error(RuntimeError):
    """可直接展示的去敏错误。"""


def validate_path(path: str) -> tuple[str, ...]:
    if not path:
        return ()
    parts = path.split("/")
    if any(p in ("", ".", "..") or "\x00" in p or "\\" in p for p in parts):
        raise Ext4Error("Ubuntu 路径无效，必须使用分区内相对路径，禁止路径遍历")
    return tuple(parts)


def verify_identity(expected: dict, inventory):
    """编号仅用作当次参数，GUID/大小/偏移/类型等必须与当前清单一致。"""
    disk = next((d for d in inventory.disks if d.id == expected["disk"]["id"]), None)
    part = next((p for p in inventory.partitions if p.id == expected["partition"]["id"]), None)
    if disk is None or part is None or disk.offline or not disk.identity_stable or not disk.guid or not part.guid:
        raise Ext4Error("分区身份已变化或不可确认，请重新扫描并选择，未打开原始设备")
    for key in ("guid", "unique_id", "size", "partition_style"):
        if getattr(disk, key) != expected["disk"][key]:
            raise Ext4Error("磁盘身份不一致，拒绝访问")
    for key in ("disk_id", "guid", "gpt_type", "offset", "size", "label", "filesystem", "hidden", "is_system", "is_boot"):
        if getattr(part, key) != expected["partition"][key]:
            raise Ext4Error("分区 GUID、卷标、偏移、容量或文件系统发生变化，拒绝访问")
    if (part.gpt_type != LINUX_DATA or part.is_system or disk.partition_style != "GPT"
            or part.offset < 0 or part.offset + part.size > disk.size):
        raise Ext4Error("仅允许已确认身份的 Linux 数据分区；LVM/EFI/Recovery 等不受支持")
    return disk, part


class Ext4Stream(io.RawIOBase):
    def __init__(self, backend, file_object, size: int) -> None:
        super().__init__()
        self.backend, self.file_object, self.size, self.position = backend, file_object, size, 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        self._checkClosed()
        self.backend._check_open()
        count = min(len(buffer), self.size - self.position, 1024 * 1024)
        if count <= 0:
            return 0
        try:
            data = self.file_object.read_random(self.position, count)
        except Exception as exc:
            raise Ext4Error("ext4 文件读取失败或 inode 已损坏") from exc
        if not data or len(data) > count:
            raise Ext4Error("ext4 文件读取提前结束或返回长度异常")
        buffer[:len(data)] = data
        self.position += len(data)
        return len(data)

    def close(self) -> None:
        self.file_object = None
        super().close()


class Ext4ReadOnlyBackend:
    def __init__(self, image_path: str, offset: int, size: int, *, expected_fs: str = "", _verified_device: tuple | None = None) -> None:
        if image_path.startswith(("\\\\.\\", "\\\\?\\")):
            if not _verified_device or not re.fullmatch(r"\\\\\.\\PhysicalDrive[0-9]+", image_path):
                raise Ext4Error("原始设备必须经 from_partition 身份复核后打开；禁止其他设备命名空间")
        try:
            import pytsk3
        except ImportError as exc:
            raise Ext4Error("缺少 pytsk3，请使用项目 requirements.txt 安装依赖") from exc
        self.tsk = pytsk3
        self.image = self.bounded = self.fs = None
        self.streams = []
        self.offset, self.size = offset, size
        if type(offset) is not int or type(size) is not int or offset < 0 or size < 2048:
            raise Ext4Error("分区访问边界无效")
        try:
            self.image = pytsk3.Img_Info(image_path)
            if self.image.get_size() < offset + size:
                raise Ext4Error("镜像或磁盘容量与预期不一致")
            if _verified_device:
                self._verify_gpt(self.image, *_verified_device)
            # 只允许 libtsk 在选定分区边界内读取，即使 inode 损坏也不能读入相邻分区。
            class BoundedImage(pytsk3.Img_Info):
                def __init__(self, source, start, length):
                    self.source, self.start, self.end = source, start, start + length
                    pytsk3.Img_Info.__init__(self, url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)
                def get_size(self):
                    return self.end
                def read(self, position, length):
                    if position < self.start or length < 0 or position + length > self.end:
                        raise OSError("读取越过选定分区边界")
                    return self.source.read(position, length)
            self.bounded = BoundedImage(self.image, offset, size)
            first = self.image.read(offset, 1024)
            sb = self.image.read(offset + 1024, 1024)
            self.probe = self._probe(first, sb, size)
            if expected_fs and self.probe["fingerprint"] != expected_fs:
                raise Ext4Error("ext4 UUID、卷标或特征发生变化，疑似错盘，请重新扫描")
            self.fs = pytsk3.FS_Info(self.bounded, offset=offset, type=pytsk3.TSK_FS_TYPE_EXT4)
            if self.fs.info.ftype != pytsk3.TSK_FS_TYPE_EXT4 or self.fs.info.block_size * self.fs.info.block_count > size:
                raise Ext4Error("文件系统探测与 ext4 分区边界不一致")
        except Ext4Error:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise Ext4Error("无法只读打开 ext4；若权限不足，请使用经授权的独立管理员读取进程，勿提升整个 GUI；损坏或不兼容格式也会被拒绝") from exc

    @staticmethod
    def _verify_gpt(image, disk, part) -> None:
        """打开设备后再核对原始 GPT，防止查询与打开之间设备编号复用。仅读元数据。"""
        if image.get_size() != disk.size:
            raise Ext4Error("打开的设备容量已变化，拒绝读取文件系统")
        for sector in (512, 4096):
            header = image.read(sector, sector)
            if header[:8] != b"EFI PART":
                continue
            length = struct.unpack_from("<I", header, 12)[0]
            if not 92 <= length <= sector:
                break
            check = bytearray(header[:length])
            expected_crc = struct.unpack_from("<I", check, 16)[0]
            struct.pack_into("<I", check, 16, 0)
            if zlib.crc32(check) != expected_crc or str(UUID(bytes_le=header[56:72])) != disk.guid:
                break
            lba, count, entry_size, table_crc = struct.unpack_from("<QIII", header, 72)
            table_size = count * entry_size
            first_usable = struct.unpack_from("<Q", header, 40)[0]
            if (entry_size < 128 or entry_size > 4096 or not 0 < table_size <= 1024 * 1024
                    or lba < 2 or lba * sector + table_size > first_usable * sector
                    or lba * sector + table_size > disk.size):
                break
            table = image.read(lba * sector, table_size)
            if len(table) != table_size or zlib.crc32(table) != table_crc:
                break
            matches = []
            for position in range(0, table_size, entry_size):
                entry = table[position:position + entry_size]
                if str(UUID(bytes_le=entry[16:32])) == part.guid:
                    matches.append(entry)
            if len(matches) == 1:
                entry = matches[0]
                first, last = struct.unpack_from("<QQ", entry, 32)
                if (str(UUID(bytes_le=entry[:16])) == part.gpt_type and first * sector == part.offset
                        and last >= first and (last - first + 1) * sector == part.size):
                    return
            break
        raise Ext4Error("打开设备后的 GPT GUID、校验和、分区位置或容量不匹配，疑似错盘，已停止")

    @staticmethod
    def _probe(first: bytes, sb: bytes, size: int) -> dict:
        if first.startswith(b"LUKS\xba\xbe") or b"LABELONE" in first:
            raise Ext4Error("检测到 LUKS/LVM，当前后端不支持，已停止")
        if len(sb) != 1024 or sb[56:58] != b"\x53\xef":
            raise Ext4Error("不是已验证的 ext4，未知格式/LUKS/LVM 均不支持")
        incompat, ro = struct.unpack_from("<II", sb, 96)
        if not incompat & 0x40 or incompat & ~(0x2 | 0x40 | 0x80 | 0x200 | 0x2000) or ro & (0x200 | 0x8000):
            raise Ext4Error("ext4 特征不受支持或需日志恢复（含加密、inline、casefold、bigalloc 等），已停止")
        if struct.unpack_from("<H", sb, 58)[0] != 1:
            raise Ext4Error("ext4 状态不干净或存在错误，拒绝自动恢复或写入")
        log_size = struct.unpack_from("<I", sb, 24)[0]
        if log_size > 6:
            raise Ext4Error("ext4 块大小无效")
        blocks = struct.unpack_from("<I", sb, 4)[0]
        if incompat & 0x80:
            blocks |= struct.unpack_from("<I", sb, 0x150)[0] << 32
        if blocks == 0 or blocks * (1024 << log_size) > size:
            raise Ext4Error("ext4 超级块声明的大小越过分区边界")
        identity = sb[104:136] + struct.pack("<III", incompat, ro, log_size)
        return dict(uuid=sb[104:120].hex(), label=sb[120:136].split(b"\0")[0].decode("utf-8", "replace"),
                    filesystem="ext4", fingerprint=hashlib.sha256(identity).hexdigest())

    @classmethod
    def from_partition(cls, expected: dict, *, expected_fs: str = "", service=None):
        service = service if service is not None else DiskInventoryService()
        disk, part = verify_identity(expected, service.scan())
        # 数字来自本次身份复核后的当前清单，而非初始的磁盘/分区编号。
        backend = cls(rf"\\.\PhysicalDrive{disk.number}", part.offset, part.size, expected_fs=expected_fs, _verified_device=(disk, part))
        if part.label and backend.probe["label"] != part.label:
            backend.close()
            raise Ext4Error("ext4 卷标与扫描结果不一致，拒绝访问")
        return backend

    @classmethod
    def from_image(cls, path: str, *, offset: int = 0, size: int | None = None, expected_fs: str = ""):
        if path.startswith(("\\\\.\\", "\\\\?\\")) or ":" in Path(path).name:
            raise Ext4Error("镜像模式禁止设备路径和备用数据流")
        resolved = Path(path).resolve(strict=True)
        if not resolved.is_file():
            raise Ext4Error("镜像必须是普通文件")
        return cls(str(resolved), offset, resolved.stat().st_size - offset if size is None else size, expected_fs=expected_fs)

    def _check_open(self) -> None:
        if self.fs is None:
            raise Ext4Error("ext4 后端已关闭")

    def _open(self, relative_path: str):
        self._check_open()
        parts = validate_path(relative_path)
        path = ""
        file_object = self.fs.open_meta(inode=self.fs.info.root_inum)
        for index, part in enumerate(parts):
            path += "/" + part
            try:
                file_object = self.fs.open(path=path)
            except Exception as exc:
                raise Ext4Error("ext4 路径不存在或 inode 无法读取") from exc
            meta = file_object.info.meta
            if meta is None or not meta.flags & self.tsk.TSK_FS_META_FLAG_ALLOC:
                raise Ext4Error("ext4 inode 损坏或未分配")
            if meta.type == self.tsk.TSK_FS_META_TYPE_LNK:
                if index < len(parts) - 1:
                    raise Ext4Error("禁止跟随 ext4 符号链接，防止越界或循环")
            elif index < len(parts) - 1 and meta.type != self.tsk.TSK_FS_META_TYPE_DIR:
                raise Ext4Error("ext4 路径组件不是目录")
        return file_object

    def _entry(self, name: str, file_object) -> FileEntry:
        meta = file_object.info.meta
        if meta is None or not meta.flags & self.tsk.TSK_FS_META_FLAG_ALLOC:
            return FileEntry(name, None, size=None, error="inode 损坏或未分配", backend_source="ext4", access_status="属性不可读取")
        try:
            modified = datetime.fromtimestamp(meta.mtime).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError, OverflowError):
            modified = "时间无效"
        return FileEntry(name, meta.type == self.tsk.TSK_FS_META_TYPE_DIR, int(meta.size), modified,
                         name.startswith("."), meta.type == self.tsk.TSK_FS_META_TYPE_LNK,
                         bool(meta.mode & 0o444), bool(meta.mode & 0o222), "", "ext4", "属性已读取")

    def stat(self, relative_path: str = "") -> FileEntry:
        return self._entry(relative_path.rsplit("/", 1)[-1] or "/", self._open(relative_path))

    def list_dir(self, relative_path: str = "", *, offset: int = 0, page_size: int = 200,
                 show_hidden: bool = False, fingerprint: str = "") -> DirectoryPage:
        if type(offset) is not int or offset < 0 or not 1 <= page_size <= 1000:
            raise Ext4Error("ext4 分页参数无效")
        directory = self._open(relative_path)
        if directory.info.meta.type != self.tsk.TSK_FS_META_TYPE_DIR:
            raise Ext4Error("目标不是 ext4 目录或是禁止跟随的链接")
        current = self.probe["fingerprint"] + f":{directory.info.meta.addr}:{directory.info.meta.mtime}"
        if fingerprint and fingerprint != current:
            raise Ext4Error("ext4 目录或卷身份已变化，请重新扫描")
        entries, scanned = [], 0
        try:
            iterator = directory.as_directory()
            for index, item in enumerate(iterator):
                if index < offset:
                    continue
                scanned += 1
                info = item.info.name
                if info is None or not info.flags & self.tsk.TSK_FS_NAME_FLAG_ALLOC:
                    continue
                raw = info.name
                if raw in (b".", b"..", b"$OrphanFiles"):
                    continue
                name = raw.decode("utf-8", "replace")
                record = self._entry(name, item)
                try:
                    raw.decode("utf-8", "strict")
                    validate_path(name)
                except (UnicodeError, Ext4Error):
                    from dataclasses import replace
                    record = replace(record, error="文件名编码或字符不支持，仅展示元数据")
                if show_hidden or not record.hidden:
                    entries.append(record)
                if len(entries) >= page_size or scanned >= 2000:
                    return DirectoryPage(tuple(entries), offset + scanned, current)
            return DirectoryPage(tuple(entries), None, current)
        except Ext4Error:
            raise
        except Exception as exc:
            raise Ext4Error("ext4 目录损坏或读取失败") from exc

    @contextmanager
    def open_read(self, relative_path: str):
        file_object = self._open(relative_path)
        if file_object.info.meta.type != self.tsk.TSK_FS_META_TYPE_REG:
            raise Ext4Error("仅允许读取普通 ext4 文件，不跟随链接")
        stream = io.BufferedReader(Ext4Stream(self, file_object, int(file_object.info.meta.size)), buffer_size=65536)
        self.streams.append(stream)
        try:
            yield stream
        finally:
            stream.close()
            if stream in self.streams:
                self.streams.remove(stream)

    def get_capabilities(self) -> ReadOnlyCapabilities:
        return ReadOnlyCapabilities()

    def close(self) -> None:
        for stream in getattr(self, "streams", ()):
            stream.close()
        self.streams.clear()
        self.fs = None  # FS_Info 没有 close 方法；先释放文件系统，再释放镜像。
        import gc
        gc.collect()
        if self.bounded is not None:
            self.bounded.close()
            self.bounded.source = None
            self.bounded = None
        if self.image is not None:
            self.image.close()
            self.image = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
