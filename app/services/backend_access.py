"""后台后端路由与二次策略检查，避免 UI 标志成为授权依据。"""

from contextlib import contextmanager
from dataclasses import replace
from typing import Iterator

from app.core.backend import FileSystemBackend
from app.core.browser import DirectoryPage, Partition, ReadOnlyCapabilities
from app.core.inventory import PartitionInfo
from app.core.capability_policy import CapabilityPolicy
from app.backends.windows_native import NativeWindowsBackend, normalize_root
from app.backends.ext4_readonly import Ext4ReadOnlyBackend
from app.core.virtual_path import VirtualPath


@contextmanager
def open_backend(request: dict, operation: str = "list_dir") -> Iterator[FileSystemBackend]:
    spec = request.get("backend_spec") or {}
    metadata = spec.get("partition")
    if not metadata:
        raise ValueError("缺少已验证的分区上下文，拒绝启动后端")
    partition = PartitionInfo(**metadata) if "gpt_type" in metadata else Partition(**metadata)
    if partition.id != request["partition_id"]:
        raise ValueError("请求与分区身份不一致，拒绝启动后端")
    kind = spec.get("kind", "ext4")
    policy = CapabilityPolicy()
    decision = policy.evaluate(partition, ReadOnlyCapabilities, kind)
    allowed = {"list_dir": decision.browse, "stat": decision.stat, "open_read": decision.open_read}
    if not allowed.get(operation, False):
        raise ValueError(decision.reason)
    if kind == "ext4":
        backend = (Ext4ReadOnlyBackend.from_image(spec["image"], expected_fs=spec.get("fingerprint", ""))
                   if "image" in spec else Ext4ReadOnlyBackend.from_partition(spec, expected_fs=spec.get("fingerprint", "")))
    elif kind == "Windows":
        expected_root = partition.volume_path
        if not expected_root or normalize_root(request["root"]).casefold() != normalize_root(expected_root).casefold():
            raise ValueError("访问根与分区身份不一致或缺少绑定根，拒绝启动后端")
        backend = NativeWindowsBackend(request["partition_id"], request["root"])
    else:
        raise ValueError("未知后端，仅允许查看分区信息")
    try:
        if not isinstance(backend, FileSystemBackend):
            raise ValueError("后端不符合统一只读接口")
        actual = policy.evaluate(partition, backend.get_capabilities, kind)
        if not {"list_dir": actual.browse, "stat": actual.stat, "open_read": actual.open_read}.get(operation, False):
            raise ValueError("后端没有本次只读操作所需的能力")
        yield backend
    finally:
        if isinstance(backend, Ext4ReadOnlyBackend):
            backend.close()


def query_page(request: dict) -> DirectoryPage:
    path = VirtualPath(request["partition_id"], request["relative_path"])
    with open_backend(request) as backend:
        page = backend.list_dir(path.path, offset=request["offset"],
            show_hidden=request["show_hidden"], fingerprint=request["fingerprint"])
        return replace(page, source_info=backend.probe) if isinstance(backend, Ext4ReadOnlyBackend) else page
