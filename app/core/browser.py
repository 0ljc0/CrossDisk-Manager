"""界面数据契约；路径独立于 Windows 本地文件路径。"""

from dataclasses import dataclass
from typing import Protocol
from app.core.virtual_path import VirtualPath


Location = VirtualPath  # 保留旧导入名、位置参数和 relative_path 关键字。


@dataclass(frozen=True)
class Partition:
    id: str
    name: str
    filesystem: str
    status: str
    browsable: bool
    writable: bool
    reason: str
    category: str = "未知类型"
    backend_name: str = ""
    volume_path: str = ""  # Windows/UNC 上下文绑定根；空值不授予访问。


@dataclass(frozen=True)
class FileEntry:
    name: str
    is_directory: bool | None
    size: int | None = None
    modified: str = ""
    hidden: bool = False
    is_link: bool | None = None
    readable: bool | None = None
    writable: bool | None = None
    error: str = ""
    backend_source: str = "未知"
    access_status: str = "未知"


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
