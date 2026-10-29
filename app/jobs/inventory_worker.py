"""在独立线程执行有超时的磁盘元数据查询。"""

from PySide6.QtCore import QThread, Signal

from app.core.inventory import InventoryError
from app.services.disk_inventory import DiskInventoryService


class InventoryWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service: DiskInventoryService, parent=None) -> None:
        super().__init__(parent)
        self.service = service

    def run(self) -> None:
        try:
            self.succeeded.emit(self.service.scan())
        except InventoryError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("磁盘扫描发生内部错误，请检查日志并重试。")
