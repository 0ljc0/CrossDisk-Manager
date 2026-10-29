"""分类保护优先，功能能力其次；本阶段所有写操作始终关闭。"""

from dataclasses import dataclass
from typing import Callable

from app.core.browser import FileEntry, ReadOnlyCapabilities


@dataclass(frozen=True)
class AccessDecision:
    browse: bool
    stat: bool
    open_read: bool
    write: bool
    reason: str


class CapabilityPolicy:
    def require_windows_write(self, partition, disk) -> None:
        decision = self.evaluate(partition, ReadOnlyCapabilities, "Windows")
        if (not decision.browse or getattr(partition, "category", "") != "普通数据"
                or not getattr(partition, "identity_stable", False)
                or not getattr(partition, "volume_path", "")
                or getattr(partition, "is_boot", False)
                or getattr(partition, "status", "") != "只读"
                or getattr(partition, "volume_status", "").lower() not in ("ok", "healthy")
                or disk.offline or disk.read_only or not disk.identity_stable
                or partition.filesystem not in ("NTFS", "FAT", "FAT32", "exFAT", "EXFAT")):
            raise ValueError("仅允许在线、未锁定、身份可靠的普通 Windows 数据卷写入")

    def evaluate(self, partition, capabilities: ReadOnlyCapabilities | Callable | None,
                 backend: str = "") -> AccessDecision:
        gpt = getattr(partition, "gpt_type", "").strip("{}").lower()
        category = {"c12a7328-f81f-11d2-ba4b-00a0c93ec93b": "EFI",
                    "e3c9e316-0b5c-4db8-817d-f92df00215ae": "MSR",
                    "de94bba4-06d1-4d40-a16a-bfd50179d6ac": "Recovery",
                    "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7": "普通数据",
                    "0fc63daf-8483-4772-8e79-3d69d8477de4": "Linux 数据"}.get(gpt, "未知类型" if gpt else getattr(partition, "category", "未知类型"))
        reasons = {"EFI": "EFI 引导分区受保护，只能查看分区信息",
                   "MSR": "MSR 保留分区没有普通文件树，只能查看分区信息",
                   "Recovery": "Recovery 恢复分区受保护，只能查看分区信息"}
        reason = reasons.get(category)
        linux = gpt == "0fc63daf-8483-4772-8e79-3d69d8477de4"
        if not reason and getattr(partition, "is_system", False):
            reason = "系统保护分区只展示元数据"
        if not reason and getattr(partition, "hidden", False) and not (linux and backend == "ext4"):
            reason = "隐藏分区只展示元数据"
        if not reason and category in ("未知类型", "未知", "不可识别"):
            reason = "未知分区不能启用文件后端，只能查看分区信息"
        if not reason and linux and backend and backend != "ext4":
            reason = "Linux 数据只能经过验证的 ext4 只读后端访问"
        if not reason and backend == "ext4" and not linux:
            reason = "该分区不是 Linux 数据，不能交给 ext4 后端"
        if not reason and backend == "Windows" and getattr(partition, "filesystem", "") not in ("NTFS", "FAT", "FAT32", "exFAT", "EXFAT", "网络共享"):
            reason = "未识别的 Windows 文件系统仅展示分区信息"
        if reason:
            return AccessDecision(False, False, False, False, reason)
        # 在分类保护之后才能调用能力提供者，保护分区不会触发后端构造/询问。
        if capabilities is None or backend not in ("Windows", "ext4", "模拟"):
            return AccessDecision(False, False, False, False, "没有可用的只读后端，只能查看分区信息")
        caps = capabilities() if callable(capabilities) else capabilities
        reason = ("只读模式：新建、重命名、删除、保存均禁用" if caps.read and caps.list_dir else
                  "后端不具备只读目录浏览能力，仅展示分区信息")
        return AccessDecision(bool(caps.read and caps.list_dir), bool(caps.read and caps.stat),
                              bool(caps.read and caps.open_read), False, reason)

    def entry_reason(self, entry: FileEntry, backend: str) -> str:
        if entry.error:
            return entry.error
        if entry.is_link is True:
            return "链接和重解析点禁止跟随，防止越界或循环"
        if entry.is_link is None and backend != "模拟":
            return "链接状态未知，不能安全进入或读取"
        return ""
