"""元数据搜索契约：不包含文件内容或可执行查询。"""

from dataclasses import dataclass, field
from datetime import date, datetime
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

from app.core.browser import FileEntry


@dataclass(frozen=True)
class SearchQuery:
    name_pattern: str = "*"
    extensions: str = ""
    path_contains: str = ""
    entry_type: str = "all"
    min_size: int | None = None
    max_size: int | None = None
    modified_from: str = ""
    modified_to: str = ""
    case_sensitive: bool | None = None

    def __post_init__(self) -> None:
        if len(self.name_pattern) > 256 or len(self.extensions) > 256 or len(self.path_contains) > 512:
            raise ValueError("搜索条件过长")
        if self.entry_type not in ("all", "file", "directory", "link"):
            raise ValueError("文件类型筛选无效")
        if self.case_sensitive is not None and type(self.case_sensitive) is not bool:
            raise ValueError("大小写设置无效")
        for number in (self.min_size, self.max_size):
            if number is not None and (type(number) is not int or not 0 <= number <= 2**63 - 1):
                raise ValueError("大小必须是非负字节数")
        if self.min_size is not None and self.max_size is not None and self.min_size > self.max_size:
            raise ValueError("最小大小不能大于最大大小")
        for value in (self.modified_from, self.modified_to):
            if value:
                try:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError("日期必须使用标准格式")
                except ValueError as exc:
                    raise ValueError("日期格式必须为 YYYY-MM-DD") from exc
        if self.modified_from and self.modified_to and self.modified_from > self.modified_to:
            raise ValueError("开始日期不能晚于结束日期")

    def matches(self, entry: FileEntry, path: str, backend: str) -> bool:
        sensitive = backend == "ext4" if self.case_sensitive is None else self.case_sensitive
        def normalize(text):
            return text if sensitive else text.casefold()
        def match(value, pattern):
            value, pattern = normalize(value), normalize(pattern)
            return fnmatchcase(value, pattern) if any(c in pattern for c in "*?[") else pattern in value
        if not match(entry.name, self.name_pattern or "*"):
            return False
        if self.path_contains and not match(path, self.path_contains):
            return False
        extensions = [e.strip().lstrip("*.") for e in self.extensions.replace(";", ",").split(",") if e.strip()]
        if extensions and not any(normalize(entry.name).endswith("." + normalize(e)) for e in extensions):
            return False
        if self.entry_type == "link" and entry.is_link is not True:
            return False
        if self.entry_type == "directory" and (entry.is_directory is not True or entry.is_link is True):
            return False
        if self.entry_type == "file" and (entry.is_directory is not False or entry.is_link is True):
            return False
        if self.min_size is not None and (entry.size is None or entry.size < self.min_size):
            return False
        if self.max_size is not None and (entry.size is None or entry.size > self.max_size):
            return False
        if self.modified_from or self.modified_to:
            try:
                modified = datetime.fromisoformat(entry.modified).date().isoformat()
            except (TypeError, ValueError):
                return False
            if self.modified_from and modified < self.modified_from or self.modified_to and modified > self.modified_to:
                return False
        return True


@dataclass(frozen=True)
class SearchLimits:
    max_depth: int = 32
    max_results: int = 5000
    max_entries: int = 200000
    max_directories: int = 20000
    max_seconds: int = 300

    def __post_init__(self) -> None:
        for value, maximum in ((self.max_depth, 64), (self.max_results, 10000), (self.max_entries, 500000),
                               (self.max_directories, 50000), (self.max_seconds, 600)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("搜索预算无效或超过安全上限")


@dataclass(frozen=True)
class SearchResult:
    partition_id: str
    partition_name: str
    relative_path: str
    entry: FileEntry


@dataclass
class SearchStats:
    sources_total: int = 0
    sources_done: int = 0
    directories: int = 0
    entries: int = 0
    matches: int = 0
    error_directories: int = 0
    error_entries: int = 0
    skipped_links: int = 0
    skipped_depth: int = 0
    skipped_repeated: int = 0
    cancelled: bool = False
    complete: bool = False
    stopped_reason: str = ""
