"""统一只读文件系统适配器。所有写方法显式拒绝。

已挂载的 NTFS / ext4 统一通过 Windows 文件 API 读取；不修改驱动和分区。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Capabilities:
    read: bool = True
    create: bool = False
    edit: bool = False
    delete: bool = False
    rename: bool = False
    reason: str = 'CrossDisk Manager V0.3 全局只读策略'


@dataclass(frozen=True)
class FileEntry:
    name: str
    path: Path
    is_dir: bool
    size: int
    modified: str


class ReadOnlyMountedAdapter:
    """挂载卷的只读抽象。只处理挂载后的路径，不直接操作扇区。"""
    capabilities = Capabilities()

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _within_root(self, path: str | Path) -> Path:
        target = Path(path)
        try:
            r = os.path.normcase(os.path.realpath(self.root))
            t = os.path.normcase(os.path.realpath(target))
            if os.path.commonpath([r, t]) != r:
                raise PermissionError('访问路径超出当前选中的挂载卷')
        except ValueError as exc:
            raise PermissionError('路径与挂载卷不属于同一个根目录') from exc
        return target

    def list_dir(self, path: str | Path, limit: int = 5000) -> tuple[list[FileEntry], bool]:
        target = self._within_root(path)
        items = []
        truncated = False
        with os.scandir(target) as it:
            for entry in it:
                if len(items) >= limit:
                    truncated = True
                    break
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                    stats = entry.stat(follow_symlinks=False)
                    size = 0 if is_dir else stats.st_size
                    modified = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M')
                except (OSError, OverflowError, ValueError):
                    is_dir, size, modified = False, 0, '无法读取'
                items.append(FileEntry(entry.name, Path(entry.path), is_dir, size, modified))
        items.sort(key=lambda e: (not e.is_dir, e.name.casefold()))
        return items, truncated

    def stat(self, path: str | Path):
        return self._within_root(path).stat()

    def read_bytes(self, path: str | Path, limit: int) -> bytes:
        with self._within_root(path).open('rb') as src:
            return src.read(limit)

    def write_file(self, *_args, **_kwargs):
        raise PermissionError(self.capabilities.reason)

    def delete_file(self, *_args, **_kwargs):
        raise PermissionError(self.capabilities.reason)

    def create_directory(self, *_args, **_kwargs):
        raise PermissionError(self.capabilities.reason)

    def rename(self, *_args, **_kwargs):
        raise PermissionError(self.capabilities.reason)
