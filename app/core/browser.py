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


class BrowserSource(Protocol):
    """只提供列表查询；本阶段唯一实现为内存模拟数据。"""

    def partitions(self) -> tuple[Partition, ...]: ...

    def list_directory(self, location: Location) -> tuple[FileEntry, ...]: ...
