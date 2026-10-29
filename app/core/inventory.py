"""磁盘清单值对象，不持有设备句柄。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DiskInfo:
    id: str
    number: int
    model: str
    size: int
    guid: str
    unique_id: str
    partition_style: str
    status: str
    offline: bool
    read_only: bool
    identity_stable: bool


@dataclass(frozen=True)
class PartitionInfo:
    id: str
    disk_id: str
    disk_number: int
    number: int
    guid: str
    gpt_type: str
    offset: int
    size: int
    hidden: bool
    drive_letter: str
    label: str
    filesystem: str
    status: str
    category: str
    reason: str
    volume_status: str
    identity_stable: bool


@dataclass(frozen=True)
class VolumeInfo:
    id: str
    drive_letter: str
    label: str
    filesystem: str
    status: str


@dataclass(frozen=True)
class DiskInventory:
    disks: tuple[DiskInfo, ...]
    partitions: tuple[PartitionInfo, ...]
    volumes: tuple[VolumeInfo, ...]


class InventoryError(RuntimeError):
    """可直接展示的去敏扫描错误。"""
