"""仅打印分区和挂载卷的自动关联诊断信息，不写磁盘。"""
from __future__ import annotations

import ctypes
import os

from storage_scan import scan_storage
from volume_links import probe_drives, resolve_verified_links, drive_mode_text


def mounted_roots():
    if os.name != 'nt':
        raise SystemExit('仅可在 Windows 中运行。')
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    return [f'{chr(65 + i)}:\\' for i in range(26)
            if mask & (1 << i) and os.path.isdir(f'{chr(65 + i)}:\\')]


def main():
    data = scan_storage()
    drives = probe_drives(mounted_roots())
    links = resolve_verified_links(data['partitions'], drives)
    for d in drives:
        print(f'{d.root} FS={d.filesystem or "未知"} 卷标={d.label or "-"}')
        print(f'  {drive_mode_text(d)}')
        print(f'  extent={d.extent}  {d.extent_note}')
    print('\n物理分区关联（未找到时不会猜测）：')
    for p in data['partitions']:
        k = (int(p['disk_number']), int(p['partition_number']))
        print(f'  磁盘{k[0]} 分区{k[1]}: {links.get(k, ("未验证", ""))[0]}')


if __name__ == '__main__':
    main()
