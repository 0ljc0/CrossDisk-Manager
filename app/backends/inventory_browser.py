"""仅将已扫描的元数据适配到现有界面，不提供真实文件浏览。"""

from app.core.browser import Location, Partition
from app.core.inventory import DiskInventory


class InventoryBrowserSource:
    def __init__(self, inventory: DiskInventory) -> None:
        self.inventory = inventory

    def partitions(self) -> tuple[Partition, ...]:
        return tuple(Partition(p.id, f"分区 {p.number} · {p.drive_letter + ':' if p.drive_letter else p.category}",
                               p.filesystem, p.status, False, False, p.reason) for p in self.inventory.partitions)

    def list_directory(self, location: Location) -> tuple:
        raise PermissionError("任务 03 仅展示分区元数据，文件浏览尚未接入。")
