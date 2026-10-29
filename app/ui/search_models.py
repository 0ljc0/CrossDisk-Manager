"""当前目录筛选与按来源分区展示的搜索结果。"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from app.core.browser import FileEntry
from app.core.search import SearchQuery, SearchResult


class FileFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query, self.parent_path, self.backend = SearchQuery(), "", "Windows"

    def set_query(self, query: SearchQuery, parent_path: str, backend: str) -> None:
        self.beginFilterChange()
        self.query, self.parent_path, self.backend = query, parent_path, backend
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, row, parent):
        entry = self.sourceModel().index(row, 0, parent).data(Qt.ItemDataRole.UserRole)
        return bool(entry and self.query.matches(entry, "/".join(filter(None, (self.parent_path, entry.name))), self.backend))


class SearchResultsModel(QAbstractTableModel):
    headers = ("来源分区", "名称", "相对路径", "类型", "大小", "修改时间", "后端")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.results: list[SearchResult] = []

    def clear(self) -> None:
        self.beginResetModel()
        self.results.clear()
        self.endResetModel()

    def append(self, records: list[dict]) -> None:
        if not records:
            return
        rows = [SearchResult(r["partition_id"], r["partition_name"], r["relative_path"], FileEntry(**r["entry"])) for r in records]
        first = len(self.results)
        self.beginInsertRows(QModelIndex(), first, first + len(rows) - 1)
        self.results.extend(rows)
        self.endInsertRows()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.results)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        return self.headers[section] if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal else None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.results):
            return None
        result = self.results[index.row()]
        entry = result.entry
        if role == Qt.ItemDataRole.UserRole:
            return result
        if role == Qt.ItemDataRole.ToolTipRole:
            return result.partition_id + ":/" + result.relative_path
        if role == Qt.ItemDataRole.DisplayRole:
            return (result.partition_name, entry.name, result.relative_path,
                    "链接（不跟随）" if entry.is_link else "目录" if entry.is_directory else "未知" if entry.is_directory is None else "文件",
                    "未知" if entry.size is None else f"{entry.size:,} B", entry.modified or "未知", entry.backend_source)[index.column()]
