"""分区身份与 POSIX 内部路径，绝不把 Ubuntu 路径解释为 Windows 盘符。"""

from dataclasses import dataclass


@dataclass(frozen=True, init=False)
class VirtualPath:
    partition_id: str
    path: str

    def __init__(self, partition_id: str, path: str = "", *, relative_path: str | None = None) -> None:
        if not isinstance(partition_id, str) or not partition_id or any(c.isspace() or c in ":/\\\x00" for c in partition_id):
            raise ValueError("分区标识无效")
        if relative_path is not None:
            if path and path != relative_path:
                raise ValueError("路径参数冲突")
            path = relative_path
        if not isinstance(path, str):
            raise ValueError("内部路径必须是字符串")
        if "\\" in path or any(ord(c) < 32 for c in path):
            raise ValueError("内部路径必须使用 POSIX 分隔符且不能包含控制字符")
        parts = []
        for part in path.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if not parts:
                    raise ValueError("路径越过分区根目录，已拒绝")
                parts.pop()
            else:
                parts.append(part)
        object.__setattr__(self, "partition_id", partition_id)
        object.__setattr__(self, "path", "/".join(parts))

    @property
    def relative_path(self) -> str:
        return self.path

    @property
    def address(self) -> str:
        return f"{self.partition_id}:/{self.path}"

    @property
    def parent(self) -> "VirtualPath":
        return VirtualPath(self.partition_id, self.path.rpartition("/")[0])

    def child(self, name: str) -> "VirtualPath":
        if not name or name in (".", "..") or "/" in name or "\\" in name:
            raise ValueError("目录项名称无效，禁止越界")
        return VirtualPath(self.partition_id, "/".join(filter(None, (self.path, name))))

    def breadcrumbs(self) -> tuple["VirtualPath", ...]:
        parts = self.path.split("/") if self.path else []
        return tuple(VirtualPath(self.partition_id, "/".join(parts[:i])) for i in range(len(parts) + 1))
