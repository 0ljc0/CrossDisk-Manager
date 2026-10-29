"""Qt Model/View 适配，不包含真实文件系统操作。"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

from app.core.browser import FileEntry, Partition


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
    headers = ("名称", "类型", "大小", "修改时间（模拟）")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.entries: tuple[FileEntry, ...] = ()

    def set_entries(self, entries: tuple[FileEntry, ...]) -> None:
        self.beginResetModel()
        self.entries = entries
        self.endResetModel()

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
            return entry.name
        if role == Qt.ItemDataRole.DisplayRole:
            return (entry.name, "文件夹" if entry.is_directory else "文件",
                    "—" if entry.is_directory else f"{entry.size:,} B", entry.modified)[index.column()]
        return None
