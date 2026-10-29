"""将扫描身份映射到 Windows 只读根及待验证的 Linux 候选。"""

from app.core.browser import Location, Partition
from app.core.inventory import DiskInventory
from app.backends.windows_native import NativeWindowsBackend, VOLUME_ROOT, validate_relative
from app.backends.ext4_readonly import validate_path
from app.services.disk_inventory import LINUX_DATA
from dataclasses import asdict
from app.core.capability_policy import CapabilityPolicy
from app.core.browser import ReadOnlyCapabilities
import hashlib
import ntpath


class InventoryBrowserSource:
    def __init__(self, inventory: DiskInventory) -> None:
        self.inventory = inventory
        self.roots: dict[str, str] = {}
        self.network: dict[str, Partition] = {}
        self.ext4: dict[str, dict] = {}
        for p in inventory.partitions:
            disk = next(d for d in inventory.disks if d.id == p.disk_id)
            if (p.category == "普通数据" and p.status == "只读" and not p.hidden and not disk.offline
                    and p.identity_stable and p.filesystem.upper() in ("NTFS", "FAT", "FAT32", "EXFAT")
                    and VOLUME_ROOT.fullmatch(p.volume_path)):
                self.roots[p.id] = p.volume_path
            elif (p.gpt_type == LINUX_DATA and p.guid and p.identity_stable and not disk.offline and not p.is_system
                  and p.filesystem == "未识别"):
                self.ext4[p.id] = dict(disk=asdict(disk), partition=asdict(p), fingerprint="")

    def partitions(self) -> tuple[Partition, ...]:
        return tuple(Partition(p.id, f"分区 {p.number} · {p.drive_letter + ':' if p.drive_letter else p.category}",
                               "ext4" if self.ext4.get(p.id, {}).get("fingerprint") else
                               "待验证" if p.id in self.ext4 else
                               p.filesystem,
                               ("只读" if self.ext4[p.id]["fingerprint"] else "待验证") if p.id in self.ext4 else p.status,
                               p.id in self.roots or p.id in self.ext4, False,
                               ("ext4 只读，禁止写入和跟随符号链接" if self.ext4[p.id]["fingerprint"] else
                                "Linux 类型候选：单击时复核身份并探测 ext4，仅只读；LUKS/LVM 等不支持")
                               if p.id in self.ext4 else "Windows 原生只读浏览，写入禁用" if p.id in self.roots else p.reason,
                               p.category, "ext4" if p.id in self.ext4 else "Windows" if p.id in self.roots else "")
                     for p in self.inventory.partitions) + tuple(self.network.values())

    def list_directory(self, location: Location) -> tuple:
        # 保留旧接口；GUI 使用后台分页，不能在 UI 主线程调用这里。
        from app.services.backend_access import query_page
        return query_page(dict(partition_id=location.partition_id, root=self.roots.get(location.partition_id, ""),
                               relative_path=location.relative_path, offset=0, show_hidden=False, fingerprint="",
                               backend_spec=self.request_spec(location.partition_id))).entries

    def resolve_address(self, address: str) -> Location:
        """仅路由已验证卷或用户明确输入的普通 UNC；此方法不执行 I/O。"""
        if address.startswith("\\\\") and not address.startswith(("\\\\?\\", "\\\\.\\")):
            drive, tail = ntpath.splitdrive(address)
            root = drive + "\\"
            backend = NativeWindowsBackend("unc", root)
            identifier = "unc-" + hashlib.sha256(backend.root.casefold().encode()).hexdigest()
            relative = tail.lstrip("\\").rstrip("\\").replace("\\", "/")
            validate_relative(relative)
            self.roots[identifier] = backend.root
            self.network[identifier] = Partition(identifier, drive, "网络共享", "只读", True, False,
                                                 "显式打开的 UNC 共享；受 Windows 权限约束，仅只读", "网络共享", "Windows")
            return Location(identifier, relative)
        normalized = address.replace("\\", "/")
        for p in self.inventory.partitions:
            prefix = p.drive_letter + ":/" if p.drive_letter else ""
            native_prefix = p.volume_path.replace("\\", "/")
            for candidate in (prefix, native_prefix):
                if candidate and normalized.casefold().startswith(candidate.casefold()):
                    if p.id not in self.roots:
                        raise ValueError("该分区受保护或未识别，不允许文件浏览")
                    relative = normalized[len(candidate):].rstrip("/")
                    validate_relative(relative)
                    return Location(p.id, relative)
        partition_id, separator, relative = address.partition(":/")
        if separator and (partition_id in self.roots or partition_id in self.ext4):
            relative = relative.rstrip("/")
            (validate_path if partition_id in self.ext4 else validate_relative)(relative)
            return Location(partition_id, relative)
        raise ValueError("地址未对应到已验证的 Windows 卷，请扫描或输入普通 UNC 共享路径")

    def metadata(self, partition_id: str):
        return next((p for p in self.inventory.partitions if p.id == partition_id), self.network.get(partition_id))

    def decision(self, partition_id: str):
        partition = self.metadata(partition_id)
        backend = "ext4" if partition_id in self.ext4 else "Windows" if partition_id in self.roots else ""
        return CapabilityPolicy().evaluate(partition, ReadOnlyCapabilities if backend else None, backend)

    def request_spec(self, partition_id: str) -> dict:
        decision = self.decision(partition_id)
        if not decision.browse:
            raise ValueError(decision.reason)
        if partition_id in self.ext4:
            return dict(self.ext4[partition_id], kind="ext4")
        return dict(kind="Windows", partition=asdict(self.metadata(partition_id)))

    def display_address(self, location: Location) -> str:
        for p in self.inventory.partitions:
            if p.id == location.partition_id and p.drive_letter:
                return p.drive_letter + ":\\" + location.relative_path.replace("/", "\\")
        if location.partition_id in self.network:
            return self.network[location.partition_id].name + "\\" + location.relative_path.replace("/", "\\")
        return location.address
