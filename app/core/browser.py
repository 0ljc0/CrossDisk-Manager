"""界面数据契约；路径独立于 Windows 本地文件路径。"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Location:
    partition_id: str
    relative_path: str = ""

    @property
    def address(self) -> str:
        return f"{self.partition_id}:/{self.relative_path}"


@dataclass(frozen=True)
class Partition:
    id: str
    name: str
    filesystem: str
    status: str
    browsable: bool
    writable: bool
    reason: str


@dataclass(frozen=True)
class FileEntry:
    name: str
    is_directory: bool
    size: int = 0
    modified: str = "2026-10-29 10:00"
    hidden: bool = False
    is_link: bool = False
    readable: bool = False
    writable: bool = False
    error: str = ""


@dataclass(frozen=True)
class DirectoryPage:
    entries: tuple[FileEntry, ...]
    next_offset: int | None
    fingerprint: str
    source_info: dict | None = None


@dataclass(frozen=True)
class ReadOnlyCapabilities:
    list_dir: bool = True
    stat: bool = True
    open_read: bool = True
    write: bool = False
    read: bool = True


class BrowserSource(Protocol):
    """列表适配协议；真实 GUI 查询必须使用后台分页。"""

    def partitions(self) -> tuple[Partition, ...]: ...

    def list_directory(self, location: Location) -> tuple[FileEntry, ...]: ...
