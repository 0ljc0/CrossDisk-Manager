"""用户配置：本阶段安全模式始终只读。"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / "AppData" / "Local") / "CrossDiskManager"


@dataclass(frozen=True)
class AppConfig:
    theme: str = "system"
    language: str = "zh_CN"
    window_width: int = 1000
    window_height: int = 680
    show_hidden_files: bool = False
    read_only: bool = True

    def __post_init__(self) -> None:
        if self.theme not in ("system", "light", "dark") or self.language != "zh_CN":
            raise ValueError("不支持的主题或语言")
        if (type(self.window_width) is not int or type(self.window_height) is not int
                or not 640 <= self.window_width <= 7680
                or not 480 <= self.window_height <= 4320):
            raise ValueError("窗口大小无效")
        if type(self.show_hidden_files) is not bool or self.read_only is not True:
            raise ValueError("配置无效：本阶段必须保持只读模式")


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else user_data_dir() / "config.json"

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        # 损坏配置明确报错，保留原文件供排查。
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("配置内容必须是 JSON 对象")
        return AppConfig(**data)

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
