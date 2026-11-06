"""Qt Model/View 适配，不包含真实文件系统操作。"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyle

from app.core.browser import FileEntry, Partition
from app.core.inventory import DiskInventory


DISK_ROLE = Qt.ItemDataRole.UserRole + 1


class InventoryTreeModel(QStandardItemModel):
    def __init__(self, inventory: DiskInventory, parent=None) -> None:
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["物理磁盘 / 分区", "状态"])
        for disk in inventory.disks:
            root = QStandardItem(f"磁盘 {disk.number} · {disk.model} · {disk.size / 2**30:.2f} GiB")
            state = QStandardItem("离线" if disk.offline else disk.status or "已发现")
            for item in (root, state):
                item.setEditable(False)
                item.setData(disk.id, DISK_ROLE)
                item.setToolTip(root.text())
            for partition in (p for p in inventory.partitions if p.disk_id == disk.id):
                letter = partition.drive_letter + ": · " if partition.drive_letter else ""
                name = QStandardItem(f"分区 {partition.number} · {letter}{partition.category} · {partition.size / 2**30:.2f} GiB")
                status = QStandardItem(partition.status)
                for item in (name, status):
                    item.setEditable(False)
                    item.setData(partition.id, Qt.ItemDataRole.UserRole)
                    item.setToolTip(f"{name.text()}\n{partition.filesystem}\n{partition.reason}")
                root.appendRow([name, status])
            self.appendRow([root, state])

    def add_network(self, partition: Partition) -> None:
        if self.match(self.index(0, 0), Qt.ItemDataRole.UserRole, partition.id, 1,
                      Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive):
            return
        name, status = QStandardItem(partition.name), QStandardItem("只读网络共享")
        for item in (name, status):
            item.setEditable(False)
            item.setData(partition.id, Qt.ItemDataRole.UserRole)
            item.setToolTip(partition.reason)
        self.appendRow([name, status])


class PartitionModel(QStandardItemModel):
    def __init__(self, partitions: tuple[Partition, ...], parent=None) -> None:
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["模拟分区", "能力状态"])
        root = QStandardItem("演示磁盘 · 纯模拟")
        root.setEditable(False)
        for partition in partitions:
            name, status = QStandardItem(partition.name), QStandardItem(partition.status)
            for item in (name, status):
                item.setEditable(False)
                item.setData(partition.id, Qt.ItemDataRole.UserRole)
                item.setToolTip(partition.reason)
            root.appendRow([name, status])
        self.appendRow(root)


class FileTableModel(QAbstractTableModel):
    headers = ("名称", "类型", "大小", "修改时间", "权限提示", "访问状态", "后端来源")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.entries: tuple[FileEntry, ...] = ()
        self.pending_statuses = {}

    def set_pending_statuses(self, values):
        self.pending_statuses = dict(values)
        if self.entries:
            self.dataChanged.emit(self.index(0, 5), self.index(len(self.entries)-1, 5))

    def set_entries(self, entries: tuple[FileEntry, ...]) -> None:
        self.beginResetModel()
        self.pending_statuses = {}
        self.entries = entries
        self.endResetModel()

    def append_entries(self, entries: tuple[FileEntry, ...]) -> None:
        if entries:
            first = len(self.entries)
            self.beginInsertRows(QModelIndex(), first, first + len(entries) - 1)
            self.entries += entries
            self.endInsertRows()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.entries):
            return None
        entry = self.entries[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return entry
        if role == Qt.ItemDataRole.ToolTipRole:
            return entry.name + ("\n" + entry.error if entry.error else "") + f"\n链接状态：{self.permission(entry.is_link)}\n权限仅是属性提示，不代表实际授权"
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            icon = (QStyle.StandardPixmap.SP_FileLinkIcon if entry.is_link else
                    QStyle.StandardPixmap.SP_DirIcon if entry.is_directory else QStyle.StandardPixmap.SP_FileIcon)
            return QApplication.style().standardIcon(icon)
        if role == Qt.ItemDataRole.DisplayRole:
            kind = "链接（受限）" if entry.is_link else "未知" if entry.is_directory is None else "文件夹" if entry.is_directory else "文件"
            return (entry.name, kind,
                    "未知" if entry.size is None else "—" if entry.is_directory else f"{entry.size:,} B", entry.modified or "未知",
                    f"读：{self.permission(entry.readable)} / 写：{self.permission(entry.writable)}",
                    self.pending_statuses.get(entry.name, entry.access_status), entry.backend_source)[index.column()]
        return None

    @staticmethod
    def permission(value: bool | None) -> str:
        return "未知" if value is None else "是" if value else "否"
