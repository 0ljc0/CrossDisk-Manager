"""只读查询 Windows 已挂载卷与物理分区的关联。

IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS 只查询卷的物理位置，不能证明驱动具有写能力。
当 Paragon 不暴露卷的物理 extent 时，严禁凭 E: 盘符或 ext4 容量猜测映射。
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000
FILE_READ_ONLY_VOLUME = 0x00080000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


@dataclass(frozen=True)
class DriveInfo:
    root: str
    filesystem: str = ''
    label: str = ''
    read_only_flag: bool | None = None
    # 唯一物理 extent (disk number, disk byte offset, extent length)
    extent: tuple[int, int, int] | None = None
    extent_note: str = ''


def drive_mode_text(drive: DriveInfo) -> str:
    """Windows 卷标志是观察信息；不能当成第三方驱动真实挂载模式证明。"""
    if drive.read_only_flag is True:
        return 'Windows 报告卷为只读'
    if drive.read_only_flag is False:
        return 'Windows 未标记只读（不代表实际可写）'
    return 'Windows 卷只读标志未知'


def _get_volume_info(root: str) -> tuple[str, str, bool | None]:
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = kernel.GetVolumeInformationW
    fn.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                   ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                   ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD]
    fn.restype = wintypes.BOOL
    label = ctypes.create_unicode_buffer(261)
    fs = ctypes.create_unicode_buffer(261)
    serial, maximum, flags = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
    ok = fn(root, label, len(label), ctypes.byref(serial), ctypes.byref(maximum),
            ctypes.byref(flags), fs, len(fs))
    if not ok:
        return '', '', None
    return fs.value, label.value, bool(flags.value & FILE_READ_ONLY_VOLUME)


def _get_single_extent(root: str) -> tuple[tuple[int, int, int] | None, str]:
    """仅支持单 extent 卷。驱动拒绝查询时返回未验证，不猜测物理分区。"""
    class DiskExtent(ctypes.Structure):
        _fields_ = [('DiskNumber', wintypes.DWORD),
                    ('StartingOffset', ctypes.c_int64),
                    ('ExtentLength', ctypes.c_int64)]

    class VolumeExtents(ctypes.Structure):
        _fields_ = [('NumberOfDiskExtents', wintypes.DWORD),
                    ('Extents', DiskExtent * 16)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    ioctl = kernel.DeviceIoControl
    ioctl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
                      wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                      ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    ioctl.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # C: -> \\.\C:，访问权限为 0：仅设备查询、不打开原始磁盘写句柄。
    volume_device = '\\\\.\\' + root[:2]
    handle = create(volume_device, 0, 0x01 | 0x02 | 0x04, None, 3, 0, None)
    if handle in (None, INVALID_HANDLE_VALUE):
        return None, '驱动或权限不允许查询物理卷映射'
    try:
        result = VolumeExtents()
        returned = wintypes.DWORD(0)
        ok = ioctl(handle, IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS, None, 0,
                   ctypes.byref(result), ctypes.sizeof(result), ctypes.byref(returned), None)
        if not ok:
            return None, '卷驱动未提供物理 extent 信息'
        count = int(result.NumberOfDiskExtents)
        if count != 1:
            return None, f'卷具有 {count} 个 extent，自动关联已禁用'
        extent = result.Extents[0]
        if extent.StartingOffset < 0 or extent.ExtentLength <= 0:
            return None, '卷 extent 信息无效'
        return (int(extent.DiskNumber), int(extent.StartingOffset),
                int(extent.ExtentLength)), '物理 extent 查询成功'
    finally:
        close(handle)


def probe_drives(roots: list[str]) -> list[DriveInfo]:
    if os.name != 'nt':
        return [DriveInfo(root=r, extent_note='仅支持 Windows') for r in roots]
    drives = []
    for root in roots:
        try:
            fs, label, flag = _get_volume_info(root)
            extent, note = _get_single_extent(root)
            drives.append(DriveInfo(root, fs, label, flag, extent, note))
        except OSError as exc:
            drives.append(DriveInfo(root, extent_note=f'查询失败：{exc}'))
    return drives


def _letter(part: dict) -> str:
    raw = str(part.get('drive_letter') or '').strip().upper().rstrip(':')
    return raw if len(raw) == 1 and raw.isalpha() else ''


def _reported_letter_matches(part: dict, root: str) -> bool:
    drive_letter = root[:1].upper()
    if _letter(part) == drive_letter:
        return True
    access_paths = part.get('access_paths') or []
    if isinstance(access_paths, str):
        access_paths = [access_paths]
    return any(str(p).replace('/', '\\').upper().startswith(drive_letter + ':\\')
               for p in access_paths)


def resolve_verified_links(partitions: list[dict], drives: list[DriveInfo]) -> dict[tuple[int, int], tuple[str, str]]:
    """返回 {(磁盘号, 分区号): (盘符根路径, 证据)}；冲突或不唯一即不关联。"""
    proposals: dict[tuple[int, int], list[tuple[str, str]]] = {}
    for drive in drives:
        root = drive.root
        if not (len(root) == 3 and root[1:] == ':\\'):
            continue
        if drive.extent is not None:
            disk_no, offset, length = drive.extent
            candidates = [p for p in partitions
                          if int(p.get('disk_number', -1)) == disk_no
                          and int(p.get('offset', -1)) == offset
                          and 0 < length <= int(p.get('size') or 0)]
            method = '卷物理 extent 与分区偏移量匹配'
        else:
            candidates = [p for p in partitions if _reported_letter_matches(p, root)]
            method = 'Windows 分区对象明确报告该盘符'
        if len(candidates) != 1:
            continue
        p = candidates[0]
        key = (int(p['disk_number']), int(p['partition_number']))
        proposals.setdefault(key, []).append((root, method))
    return {key: links[0] for key, links in proposals.items() if len(links) == 1}
