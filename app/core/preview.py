"""有上限的只读预览结果。"""

from dataclasses import dataclass

TEXT_LIMIT = 2 * 1024 * 1024
MAX_TEXT_LIMIT = 8 * 1024 * 1024
IMAGE_LIMIT = 16 * 1024 * 1024
MAX_PIXELS = 16_000_000
ENCODINGS = ("auto", "utf-8", "utf-16-le", "utf-16-be", "gb18030", "cp1252")
TEXT_TYPES = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".log", ".csv"}


@dataclass(frozen=True)
class PreviewResult:
    kind: str
    partition_id: str
    relative_path: str
    size: int | None
    modified: str
    backend_source: str
    text: str = ""
    image_png: str = ""
    encoding: str = ""
    truncated: bool = False
    bytes_read: int = 0
    message: str = ""
    read_only: bool = True
