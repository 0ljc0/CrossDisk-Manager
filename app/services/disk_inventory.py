"""固定 Windows Storage 查询，仅收集元数据，绝不修改磁盘。"""

import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

from app.core.inventory import DiskInfo, DiskInventory, InventoryError, PartitionInfo, VolumeInfo


# 不拼接用户输入；仅使用 Get-* 查询与结构化投影。
INVENTORY_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    $disks = @(Get-Disk | Select-Object Number,FriendlyName,Size,Guid,UniqueId,PartitionStyle,
        @{n='Status';e={($_.OperationalStatus -join ',')}},IsOffline,IsReadOnly)
    $partitions = @(Get-Partition | Select-Object DiskNumber,PartitionNumber,Guid,GptType,Offset,Size,
        IsHidden,IsSystem,IsBoot,DriveLetter,AccessPaths,Type,
        @{n='Status';e={($_.OperationalStatus -join ',')}})
    $volumes = @(Get-Volume | Select-Object UniqueId,Path,DriveLetter,FileSystemLabel,FileSystem,
        @{n='Status';e={($_.OperationalStatus -join ',')}},HealthStatus)
    [pscustomobject]@{Disks=$disks;Partitions=$partitions;Volumes=$volumes} | ConvertTo-Json -Depth 6 -Compress
} catch {
    $code = if ($_.CategoryInfo.Category -eq 'PermissionDenied' -or
        $_.Exception -is [System.UnauthorizedAccessException]) {'permission'} else {'query'}
    [pscustomobject]@{Error=$code} | ConvertTo-Json -Compress
    exit 1
}
'''


def _items(value) -> list[dict]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    if any(not isinstance(item, dict) for item in values):
        raise ValueError("清单对象无效")
    return values


def _text(value) -> str:
    return "" if value is None else str(value).replace("\x00", "").strip()


def _guid(value) -> str:
    text = _text(value).strip("{}")
    return str(UUID(text)) if text and UUID(text).int else ""


def _number(record: dict, name: str) -> int:
    value = record[name]
    if type(value) is not int or value < 0:
        raise ValueError("清单数值无效")
    return value


def _flag(record: dict, name: str) -> bool:
    value = record.get(name, False)
    # Storage may return null on removable/MBR devices. All flags read here
    # (offline, read-only, hidden, system, boot) restrict access when true.
    if value is None:
        return True
    if type(value) is not bool:
        raise ValueError("清单标志无效")
    return value


def _identity(prefix: str, *parts: str) -> str:
    value = json.dumps(parts, ensure_ascii=True).encode("utf-8")
    return prefix + hashlib.sha256(value).hexdigest()


EFI = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
MSR = "e3c9e316-0b5c-4db8-817d-f92df00215ae"
RECOVERY = "de94bba4-06d1-4d40-a16a-bfd50179d6ac"
BASIC = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"
LINUX_DATA = "0fc63daf-8483-4772-8e79-3d69d8477de4"


def parse_inventory(payload: str) -> DiskInventory:
    """接受 PowerShell 单对象、数组和 null；无法确认一致性时整次失败。"""
    try:
        data = json.loads(payload.lstrip("\ufeff"))
        if not isinstance(data, dict):
            raise ValueError("清单根对象无效")
        if "Error" in data:
            raise InventoryError("磁盘扫描权限不足，请使用普通账户检查 Storage 查询权限；程序不会自动提权。"
                                 if data["Error"] == "permission" else "Windows Storage 查询失败，请刷新重试。")
        disks, partitions = [], []
        raw_volumes = _items(data["Volumes"])
        volumes = tuple(VolumeInfo(_text(v.get("UniqueId")), _text(v.get("DriveLetter")),
                                  _text(v.get("FileSystemLabel")), _text(v.get("FileSystem")),
                                  _text(v.get("Status")) or _text(v.get("HealthStatus"))) for v in raw_volumes)
        by_number = {}
        for raw in _items(data["Disks"]):
            guid, unique_id = _guid(raw.get("Guid")), _text(raw.get("UniqueId"))
            stable = bool(guid or unique_id)
            identifier = _identity("disk-", guid or unique_id or str(uuid4()))
            disk = DiskInfo(identifier, _number(raw, "Number"), _text(raw.get("FriendlyName")),
                            _number(raw, "Size"), guid, unique_id, _text(raw.get("PartitionStyle")),
                            _text(raw.get("Status")), _flag(raw, "IsOffline"), _flag(raw, "IsReadOnly"), stable)
            if disk.number in by_number or any(d.id == disk.id for d in disks):
                raise ValueError("磁盘标识冲突")
            by_number[disk.number] = disk
            disks.append(disk)
        for raw in _items(data["Partitions"]):
            disk = by_number[_number(raw, "DiskNumber")]
            guid, gpt_type = _guid(raw.get("Guid")), _guid(raw.get("GptType"))
            offset, size = _number(raw, "Offset"), _number(raw, "Size")
            if offset + size > disk.size:
                raise ValueError("分区超出磁盘边界")
            letter = _text(raw.get("DriveLetter"))
            paths = raw.get("AccessPaths") or []
            paths = [paths] if isinstance(paths, str) else paths
            if not isinstance(paths, list):
                raise ValueError("卷路径无效")
            paths = {_text(p).casefold() for p in paths}
            matches = [v for v in raw_volumes if
                       (_text(v.get("UniqueId")).casefold() in paths and _text(v.get("UniqueId"))) or
                       (_text(v.get("Path")).casefold() in paths and _text(v.get("Path"))) or
                       (letter and letter.casefold() == _text(v.get("DriveLetter")).casefold())]
            if len(matches) > 1:
                raise ValueError("卷关联存在歧义")
            volume = matches[0] if matches else {}
            filesystem = _text(volume.get("FileSystem")) or "未识别"
            category = {EFI: "EFI", MSR: "MSR", RECOVERY: "Recovery", BASIC: "普通数据",
                        LINUX_DATA: "Linux 数据（文件系统待验证）"}.get(gpt_type, "未知类型")
            hidden = _flag(raw, "IsHidden")
            if category in ("EFI", "Recovery"):
                status, reason = "受保护", "系统或隐藏分区，仅展示元数据，禁止普通文件操作。"
            elif category == "MSR":
                status, reason = "不可浏览", "MSR 保留分区没有普通文件树。"
            elif hidden or _flag(raw, "IsSystem"):
                status, reason = "受保护", "系统或隐藏分区，仅展示元数据，禁止普通文件操作。"
            elif disk.offline:
                status, reason = "不可访问", "磁盘处于离线状态；程序不会修改其状态。"
            elif filesystem.upper() in ("NTFS", "FAT", "FAT32", "EXFAT"):
                status, reason = "只读", "已识别文件系统；任务 03 仅展示元数据，文件浏览尚未接入。"
            else:
                status, reason = "不可识别", "未验证文件系统或卷未解锁；不推断为 ext4，仅展示元数据。"
            identifier = _identity("part-", disk.id, guid, str(offset), str(size), gpt_type, filesystem)
            partition = PartitionInfo(identifier, disk.id, disk.number, _number(raw, "PartitionNumber"),
                guid, gpt_type, offset, size, hidden, letter, _text(volume.get("FileSystemLabel")),
                filesystem, status, category, reason, _text(volume.get("Status")) or _text(raw.get("Status")), disk.identity_stable,
                _text(volume.get("Path")) if _text(volume.get("Path")).startswith("\\\\?\\Volume{") else _text(volume.get("UniqueId")),
                _flag(raw, "IsSystem"), _flag(raw, "IsBoot"))
            if any(p.id == identifier or (p.disk_id == disk.id and p.number == partition.number) for p in partitions):
                raise ValueError("分区标识冲突")
            partitions.append(partition)
        return DiskInventory(tuple(disks), tuple(partitions), volumes)
    except InventoryError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise InventoryError("磁盘清单格式无效或扫描期间设备发生变化，请刷新重试。") from exc


class DiskInventoryService:
    def __init__(self, timeout: float = 30, runner=None) -> None:
        self.timeout = timeout
        self.runner = runner if runner is not None else subprocess.run

    def scan(self) -> DiskInventory:
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        encoded = base64.b64encode(INVENTORY_SCRIPT.encode("utf-16-le")).decode("ascii")
        try:
            result = self.runner([str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                capture_output=True, encoding="utf-8", errors="replace", timeout=self.timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        except FileNotFoundError as exc:
            raise InventoryError("找不到 Windows PowerShell，无法扫描磁盘。") from exc
        except PermissionError as exc:
            raise InventoryError("启动磁盘查询被拒绝，请检查当前账户权限。") from exc
        except subprocess.TimeoutExpired as exc:
            raise InventoryError("磁盘扫描超时，请稍后刷新重试。") from exc
        except OSError as exc:
            raise InventoryError("无法启动磁盘查询进程。") from exc
        if result.returncode and not result.stdout.strip():
            raise InventoryError("PowerShell 查询失败，可能权限不足或 Storage 模块不可用。")
        inventory = parse_inventory(result.stdout)
        if result.returncode:
            raise InventoryError("PowerShell 查询未成功完成，请刷新重试。")
        return inventory
