"""复制到 Windows 的显式任务；不赋予源后端写能力。"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CopyJob:
    source: dict
    target: dict
    conflict: str = "skip"
    max_entries: int = 100000
    max_depth: int = 32
    created_directories: dict = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self):
        if self.conflict not in ("skip", "error"):
            raise ValueError("仅支持跳过或报错，不支持覆盖")
        if not 1 <= self.max_entries <= 100000 or not 0 <= self.max_depth <= 64:
            raise ValueError("复制预算无效")


ExportJob = CopyJob
