"""通用只读后端协议，不定义写接口。"""

from typing import BinaryIO, ContextManager, Protocol, runtime_checkable

from app.core.browser import DirectoryPage, FileEntry, ReadOnlyCapabilities


@runtime_checkable
class FileSystemBackend(Protocol):
    def list_dir(self, relative_path: str = "", *, offset: int = 0, page_size: int = 200,
                 show_hidden: bool = False, fingerprint: str = "") -> DirectoryPage: ...

    def stat(self, relative_path: str = "") -> FileEntry: ...

    def open_read(self, relative_path: str) -> ContextManager[BinaryIO]: ...

    def get_capabilities(self) -> ReadOnlyCapabilities: ...
