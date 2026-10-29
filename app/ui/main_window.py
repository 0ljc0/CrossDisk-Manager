"""统一虚拟路径、策略与后台导航的只读窗口。"""

import logging
from dataclasses import replace

from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QTextOption
from PySide6.QtWidgets import (QApplication, QHeaderView, QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
                               QMessageBox, QPushButton, QSplitter, QStackedWidget, QTableView,
                               QToolBar, QToolButton, QTreeView, QVBoxLayout, QHBoxLayout, QScrollArea, QComboBox, QWidget)
from PySide6.QtCore import QSortFilterProxyModel, QTimer, Qt

from app.core.config import AppConfig, ConfigStore
from app.core.browser import BrowserSource, Location
from app.backends.mock_browser import MockBrowserSource
from app.ui.browser_models import FileTableModel, PartitionModel
from app.ui.browser_models import DISK_ROLE, InventoryTreeModel
from app.core.inventory import DiskInventory
from app.services.disk_inventory import DiskInventoryService
from app.backends.inventory_browser import InventoryBrowserSource
from app.jobs.inventory_worker import InventoryWorker
from app.jobs.directory_worker import DirectoryWorker
from app.jobs.directory_worker import PreviewWorker
from app.core.browser import DirectoryPage
from app.backends.ext4_readonly import Ext4Error, validate_path
from app.core.capability_policy import CapabilityPolicy
from app.core.browser import ReadOnlyCapabilities
from app.services.messages import user_message
from app.core.preview import ENCODINGS, MAX_TEXT_LIMIT, TEXT_LIMIT, TEXT_TYPES, PreviewResult
from app.ui.preview_panel import PreviewPanel
from app.core.search import SearchQuery
from app.ui.search_models import FileFilterProxy
from app.ui.search_dialog import SearchDialog


class PropertyView(QPlainTextEdit):
    """长标识符自动换行，保留原属性视图的文本访问接口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)

    def setText(self, text: str) -> None:
        self.setPlainText(text)

    def text(self) -> str:
        return self.toPlainText()


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, store: ConfigStore, logger: logging.Logger,
                 source: BrowserSource | None = None,
                 inventory_service: DiskInventoryService | None = None) -> None:
        super().__init__()
        self.config = config
        self.store = store
        self.logger = logger
        self.policy = CapabilityPolicy()
        self.search_dialog: SearchDialog | None = None
        self.inventory_service = inventory_service
        self.inventory: DiskInventory | None = None
        self.worker: InventoryWorker | None = None
        self.close_pending = False
        self.directory_worker: DirectoryWorker | None = None
        self.preview_worker: PreviewWorker | None = None
        self.pending_preview: dict | None = None
        self.preview_request_id = 0
        self.preview_location: Location | None = None
        self.preview_limit = TEXT_LIMIT
        self.preview_result: PreviewResult | None = None
        self.pending_directory: dict | None = None
        self.next_offset: int | None = None
        self.fingerprint = ""
        self.source = source if source is not None else MockBrowserSource()
        self.partitions = {p.id: p for p in self.source.partitions()}
        self.location: Location | None = None
        self.history: list[Location] = []
        self.history_index = -1
        self.request_id = 0
        self.loading = False
        self.load_failed = False
        self.setWindowTitle("CrossDisk Manager · 跨分区文件管理器 · 模拟演示")
        self.setMinimumSize(640, 480)
        self.resize(config.window_width, config.window_height)
        self._build_actions()
        self._build_views()
        self.set_theme(config.theme)
        if self.inventory_service is not None:
            self.setWindowTitle("CrossDisk Manager · 跨分区文件管理器 · 只读浏览")
            self.safety_label.setText("Windows / ext4 · 全局只读")
            self.address.setToolTip("例如 C:\\Users、D:\\ 或普通 UNC 共享路径，回车打开")
            self.search.setPlaceholderText("筛选已加载的文件…")
            self.hidden_action.setText("显示隐藏文件")
            self.partitions = {}
            self.partition_model.clear()
            for action in self.write_actions + [self.back_action, self.forward_action, self.up_action]:
                action.setEnabled(False)
                action.setToolTip("任务 03 仅展示磁盘元数据")
            QTimer.singleShot(0, self.scan_inventory)
        elif self.partitions:
            self.navigate(Location(next(iter(self.partitions))))

    def _action(self, text, callback, toolbar, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        toolbar.addAction(action)
        return action

    def _build_actions(self) -> None:
        navigation = QToolBar("导航", self)
        navigation.setMovable(False)
        self.addToolBar(navigation)
        self.back_action = self._action("后退", lambda: self.move_history(-1), navigation, "Alt+Left")
        self.forward_action = self._action("前进", lambda: self.move_history(1), navigation, "Alt+Right")
        self.up_action = self._action("向上", self.go_up, navigation, "Alt+Up")
        self.refresh_action = self._action("刷新", self.refresh, navigation, "F5")
        self.scan_action = self._action("重扫磁盘", self.scan_inventory, navigation)
        self.scan_action.setVisible(self.inventory_service is not None)
        self.global_search_action = self._action("跨分区搜索", self.open_search, navigation, "Ctrl+Shift+F")
        self.global_search_action.setEnabled(False)
        self.addToolBarBreak()
        address_bar = QToolBar("地址与搜索", self)
        address_bar.setMovable(False)
        self.addToolBar(address_bar)
        address_bar.addWidget(QLabel(" 地址 "))
        self.address = QLineEdit()
        self.address.setMinimumWidth(140)
        self.address.setToolTip("模拟地址，例如 mock-c:/用户文档；回车跳转")
        self.address.returnPressed.connect(self.open_address)
        address_bar.addWidget(self.address)
        self.search = QLineEdit()
        self.search.setMaximumWidth(260)
        self.search.setPlaceholderText("筛选当前模拟目录…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaxLength(256)
        address_bar.addWidget(self.search)
        self.local_field = QComboBox()
        self.local_field.addItems(["名称", "路径"])
        self.local_extensions = QLineEdit()
        self.local_extensions.setPlaceholderText("扩展名 .py,.md")
        self.local_extensions.setMaximumWidth(140)
        self.local_extensions.setMaxLength(256)
        self.local_type = QComboBox()
        for name, value in (("全部类型", "all"), ("文件", "file"), ("目录", "directory"), ("链接", "link")):
            self.local_type.addItem(name, value)
        address_bar.addWidget(self.local_field)
        address_bar.addWidget(self.local_extensions)
        address_bar.addWidget(self.local_type)
        self.addToolBarBreak()
        operations = QToolBar("文件操作", self)
        operations.setMovable(False)
        self.addToolBar(operations)
        self.write_actions = [self._action(name, self.explain_write_block, operations)
                              for name in ("新建", "重命名", "删除", "保存")]
        file_menu = self.menuBar().addMenu("文件")
        file_menu.addActions(self.write_actions)
        file_menu.addSeparator()
        self._action("退出", self.close, file_menu, "Ctrl+Q")
        view_menu = self.menuBar().addMenu("视图")
        theme_menu = view_menu.addMenu("主题")
        group = QActionGroup(self)
        self.theme_actions = {}
        for key, name in (("system", "跟随系统"), ("light", "浅色"), ("dark", "深色")):
            action = QAction(name, self, checkable=True)
            action.triggered.connect(lambda checked=False, value=key: self.set_theme(value))
            group.addAction(action)
            theme_menu.addAction(action)
            self.theme_actions[key] = action
        self.hidden_action = QAction("显示隐藏文件（模拟）", self, checkable=True)
        self.hidden_action.setChecked(self.config.show_hidden_files)
        self.hidden_action.toggled.connect(self.toggle_hidden)
        view_menu.addAction(self.hidden_action)
        help_menu = self.menuBar().addMenu("帮助")
        self._action("关于演示", lambda: QMessageBox.information(
            self, "关于", "CrossDisk Manager\n任务 08：只读浏览、预览与名称/属性搜索。\n搜索显式启动，有预算与取消，不读取文件内容或自动监控。\n所有文件写入功能禁用。"), help_menu)

    def _build_views(self) -> None:
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeView()
        self.partition_model = PartitionModel(tuple(self.partitions.values()), self)
        self.tree.setModel(self.partition_model)
        self.tree.expandAll()
        self.tree.setMinimumWidth(160)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.selectionModel().currentChanged.connect(self.select_partition)
        self.splitter.addWidget(self.tree)
        self.table = QTableView()
        self.file_model = FileTableModel(self)
        self.proxy = FileFilterProxy(self)
        self.proxy.setSourceModel(self.file_model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(0)
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(2, 85)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 145)
        self.table.setColumnWidth(5, 120)
        self.table.setColumnWidth(6, 90)
        self.table.doubleClicked.connect(self.open_entry)
        self.table.selectionModel().currentChanged.connect(self.show_entry)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.table)
        self.pages.addWidget(self.message)
        middle = QWidget()
        layout = QVBoxLayout(middle)
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)
        self.breadcrumb_buttons: list[QToolButton] = []
        self.breadcrumb_widget = QWidget()
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_widget)
        self.breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        breadcrumb_scroll = QScrollArea()
        breadcrumb_scroll.setWidgetResizable(True)
        breadcrumb_scroll.setWidget(self.breadcrumb_widget)
        breadcrumb_scroll.setFixedHeight(42)
        breadcrumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(breadcrumb_scroll)
        layout.addWidget(self.pages)
        self.more_button = QPushButton("加载下一批（最多 200 项）")
        self.more_button.setVisible(False)
        self.more_button.clicked.connect(self.load_more)
        layout.addWidget(self.more_button)
        self.splitter.addWidget(middle)
        self.properties = PropertyView()
        self.properties.setText("选择文件或分区以查看属性")
        right = QWidget()
        right.setMinimumWidth(140)
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("属性与预览"))
        self.preview_panel = PreviewPanel()
        self.preview_panel.encoding_changed.connect(self.reload_preview)
        self.preview_panel.more_requested.connect(self.more_preview)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(self.properties)
        self.right_splitter.addWidget(self.preview_panel)
        self.right_splitter.setSizes([220, 400])
        right_layout.addWidget(self.right_splitter)
        self.splitter.addWidget(right)
        self.splitter.setSizes([300, 440, 260])
        self.splitter.setStretchFactor(1, 1)
        self.setCentralWidget(self.splitter)
        self.search.textChanged.connect(self.filter_entries)
        self.local_extensions.textChanged.connect(lambda: self.filter_entries(self.search.text()))
        self.local_type.currentIndexChanged.connect(lambda: self.filter_entries(self.search.text()))
        self.local_field.currentIndexChanged.connect(lambda: self.filter_entries(self.search.text()))
        self.safety_label = QLabel("模拟数据 · 全局只读")
        self.statusBar().addPermanentWidget(self.safety_label)

    def set_theme(self, theme: str) -> None:
        self.config = replace(self.config, theme=theme)
        QApplication.styleHints().setColorScheme({"system": Qt.ColorScheme.Unknown,
            "light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}[theme])
        self.theme_actions[theme].setChecked(True)

    def toggle_hidden(self, checked: bool) -> None:
        self.config = replace(self.config, show_hidden_files=checked)
        self.refresh()

    def select_partition(self, index, previous=None) -> None:
        partition_id = index.data(Qt.ItemDataRole.UserRole)
        if partition_id:
            self.navigate(Location(partition_id))
        elif self.inventory and index.data(DISK_ROLE):
            disk = next(d for d in self.inventory.disks if d.id == index.data(DISK_ROLE))
            self.request_id += 1
            self.cancel_directory()
            self.location = None
            self.loading, self.load_failed = False, True
            self.update_breadcrumbs()
            self.up_action.setEnabled(False)
            self.address.clear()
            self.file_model.set_entries(())
            self.show_message("请选择普通 Windows 分区进行只读浏览；受保护分区仅展示元数据。")
            self.properties.setText(f"磁盘 {disk.number}\n型号：{disk.model}\n容量：{disk.size:,} B ({disk.size / 2**30:.2f} GiB)\n分区表：{disk.partition_style}\n状态：{disk.status}\n离线：{disk.offline}\n只读：{disk.read_only}\nGPT GUID：{disk.guid or '不可用'}\n稳定标识：{disk.id}\n身份可靠：{disk.identity_stable}")

    def navigate(self, location: Location, record: bool = True) -> None:
        try:
            location = Location(location.partition_id, location.relative_path)
        except ValueError as exc:
            self.report_error(user_message(exc))
            return
        if location.partition_id not in self.partitions:
            self.report_error("未知分区或设备已失效，请重新扫描")
            return
        # 在地址/搜索/选择变化触发其他信号之前，先令旧结果失效并清空旧列表。
        self.request_id += 1
        self.cancel_directory()
        self.loading, self.load_failed = True, False
        self.file_model.set_entries(())
        self.location = location
        if record and (self.history_index < 0 or self.history[self.history_index] != location):
            self.history = self.history[:self.history_index + 1] + [location]
            self.history_index = len(self.history) - 1
        address = self.source.display_address(location) if isinstance(self.source, InventoryBrowserSource) else location.address
        self.address.setText(address)
        self.search.clear()
        self.path_label.setText(address)
        self.path_label.setTextFormat(Qt.TextFormat.PlainText)
        self.update_breadcrumbs()
        indexes = self.partition_model.match(self.partition_model.index(0, 0), Qt.ItemDataRole.UserRole,
            location.partition_id, 1, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
        if indexes:
            self.tree.selectionModel().blockSignals(True)
            self.tree.setCurrentIndex(indexes[0])
            self.tree.selectionModel().blockSignals(False)
        self.back_action.setEnabled(self.history_index > 0)
        self.forward_action.setEnabled(self.history_index < len(self.history) - 1)
        self.up_action.setEnabled(bool(location.relative_path))
        partition = self.partitions[location.partition_id]
        decision = (self.source.decision(location.partition_id) if isinstance(self.source, InventoryBrowserSource) else
                    self.policy.evaluate(partition, ReadOnlyCapabilities if partition.browsable else None, "模拟"))
        self.block_reason = decision.reason
        for action in self.write_actions:
            action.setEnabled(decision.write)
            action.setToolTip(self.block_reason)
            action.setStatusTip(self.block_reason)
        self.show_partition()
        if not decision.browse:
            self.loading, self.load_failed = False, True
            self.show_message(f"{partition.status}\n{decision.reason}")
            self.statusBar().showMessage(decision.reason)
            return
        if self.inventory_service is not None:
            self.start_directory()
            return
        request_id = self.request_id
        self.loading = True
        self.load_failed = False
        self.file_model.set_entries(())
        self.show_message("正在加载模拟目录…")
        self.statusBar().showMessage("正在加载模拟数据…")
        # 仅延迟展示内存数据，便于观察加载状态；未来真实 I/O 必须移入异步任务。
        QTimer.singleShot(80, lambda: self.finish_load(request_id, location))

    def update_breadcrumbs(self) -> None:
        while self.breadcrumb_layout.count():
            item = self.breadcrumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.breadcrumb_buttons = []
        if self.location:
            for path in self.location.breadcrumbs():
                button = QToolButton()
                button.setText(self.partitions[path.partition_id].name if not path.path else path.path.rsplit("/", 1)[-1])
                button.setToolTip(path.address)
                button.setMaximumWidth(260)
                button.clicked.connect(lambda checked=False, target=path: self.navigate(target))
                self.breadcrumb_layout.addWidget(button)
                self.breadcrumb_buttons.append(button)
        self.breadcrumb_layout.addStretch()

    def finish_load(self, request_id: int, location: Location) -> None:
        if request_id != self.request_id:
            return
        self.loading = False
        partition = self.partitions[location.partition_id]
        if not partition.browsable:
            self.load_failed = True
            self.show_message(f"{partition.status}\n{partition.reason}")
            self.statusBar().showMessage("模拟分区不可访问：" + partition.reason)
            return
        try:
            entries = self.source.list_directory(location)
        except (OSError, ValueError) as exc:
            self.report_error(user_message(exc))
            return
        self.file_model.set_entries(tuple(e for e in entries if self.config.show_hidden_files or not e.hidden))
        self.filter_entries(self.search.text())

    def filter_entries(self, text: str) -> None:
        try:
            query = SearchQuery(name_pattern=text if self.local_field.currentIndex() == 0 else "*",
                path_contains=text if self.local_field.currentIndex() == 1 else "",
                extensions=self.local_extensions.text(), entry_type=self.local_type.currentData())
            path = self.location.path if self.location else ""
            backend = "ext4" if isinstance(self.source, InventoryBrowserSource) and self.location and self.location.partition_id in self.source.ext4 else "Windows"
            self.proxy.set_query(query, path, backend)
        except ValueError as exc:
            self.statusBar().showMessage(str(exc))
            return
        if self.loading or self.load_failed:
            return
        count = self.proxy.rowCount()
        if count:
            self.pages.setCurrentWidget(self.table)
        else:
            self.show_message(("已加载批次没有匹配文件，可继续加载下一批" if self.next_offset is not None else "没有匹配的文件")
                              if text else "当前批次没有可显示的文件，可继续加载下一批" if self.next_offset is not None else
                              "此目录为空或当前可见文件为空")
        prefix = "已加载" if self.inventory_service else "模拟目录"
        self.statusBar().showMessage(f"{prefix} · {count} 项 · 写入禁用：{self.block_reason}")

    def build_search_sources(self, scope: int) -> tuple[list[dict], list[str]]:
        if not isinstance(self.source, InventoryBrowserSource):
            raise ValueError("模拟模式没有真实递归搜索后端")
        if scope not in (0, 1, 2):
            raise ValueError("搜索范围无效")
        if scope != 2 and not self.location:
            raise ValueError("请先选择要搜索的分区或目录")
        sources, skipped = [], []
        for partition in self.source.partitions():
            if scope != 2 and partition.id != self.location.partition_id:
                continue
            decision = self.source.decision(partition.id)
            reason = ""
            if not decision.browse:
                reason = decision.reason
            elif partition.id in self.source.ext4 and not self.source.ext4[partition.id].get("fingerprint"):
                reason = "ext4 尚未验证可读，请先人工打开并验证"
            if reason:
                skipped.append(partition.name + "：" + reason)
                continue
            sources.append(dict(partition_id=partition.id, partition_name=partition.name,
                relative_path=self.location.path if scope == 0 else "", root=self.source.roots.get(partition.id, ""),
                backend_spec=self.source.request_spec(partition.id)))
        return sources, skipped

    def open_search(self) -> None:
        if self.search_dialog is None:
            self.search_dialog = SearchDialog(self.build_search_sources, self)
            self.search_dialog.locate_requested.connect(self.locate_search_result)
            self.search_dialog.idle.connect(self.search_idle)
        self.search_dialog.close_pending = False
        self.search_dialog.showNormal()
        self.search_dialog.raise_()

    def locate_search_result(self, result) -> None:
        if (not isinstance(self.source, InventoryBrowserSource) or result.partition_id not in self.partitions
                or not self.source.decision(result.partition_id).browse):
            self.report_error("搜索结果所属分区已失效或受保护，请重新搜索")
            return
        try:
            location = Location(result.partition_id, result.relative_path)
            target = location if result.entry.is_directory is True and result.entry.is_link is False else location.parent
            self.navigate(target)
            self.statusBar().showMessage("已定位目录，目标：" + result.entry.name)
            if self.search_dialog and not self.search_dialog.worker:
                self.search_dialog.hide()
        except ValueError as exc:
            self.report_error(user_message(exc))

    def search_idle(self) -> None:
        if self.close_pending:
            self.close()

    def show_message(self, text: str) -> None:
        self.message.setText(text)
        self.pages.setCurrentWidget(self.message)

    def show_partition(self) -> None:
        partition = self.partitions[self.location.partition_id]
        if self.inventory and partition.id not in getattr(self.source, "network", {}):
            p = next(p for p in self.inventory.partitions if p.id == partition.id)
            spec = getattr(self.source, "ext4", {}).get(partition.id, {})
            probe = spec.get("probe", {})
            filesystem = probe.get("filesystem", p.filesystem)
            label = probe.get("label", p.label)
            status = partition.status if spec else p.status
            self.properties.setText(f"磁盘 {p.disk_number} / 分区 {p.number}\n类别：{p.category}\n盘符：{p.drive_letter or '无'}\n卷标：{label or '无'}\n文件系统：{filesystem}\n状态：{status}\n卷状态：{p.volume_status or '不可用'}\n大小：{p.size:,} B ({p.size / 2**30:.2f} GiB)\n起始偏移：{p.offset:,} B\n隐藏：{p.hidden}\nGPT Type GUID：{p.gpt_type or '不可用'}\nPartition GUID：{p.guid or '不可用'}\n稳定标识：{p.id}\n身份可靠：{p.identity_stable}\n\n{partition.reason}")
            return
        self.properties.setText(f"{partition.name}\n\n文件系统：{partition.filesystem}\n能力：{partition.status}\n\n{partition.reason}\n\n写入禁用：{self.block_reason}\n\n仅模拟属性，未读取真实磁盘。")

    def show_entry(self, index, previous=None) -> None:
        entry = index.data(Qt.ItemDataRole.UserRole)
        if entry:
            readable, writable, link = (FileTableModel.permission(v) for v in (entry.readable, entry.writable, entry.is_link))
            note = (f"权限属性提示：读 {readable} / 写 {writable}\n实际访问仍由 Windows 权限决定，应用写入禁用。\n链接/重解析点：{link}\n{entry.error}\n支持的普通文件在下方只读预览。"
                    if self.inventory_service else "模拟属性，尚未接入文件内容预览。")
            if isinstance(self.source, InventoryBrowserSource) and self.location.partition_id in self.source.ext4:
                note = f"Unix 权限位提示：读 {readable} / 写 {writable}\n仅供参考，不能视为实际授权。\n后端只读，写入始终禁用。\n符号链接：{link}\n{entry.error}\n支持的普通文件在下方只读预览。"
            size = "未知" if entry.size is None else f"{entry.size:,} B"
            self.properties.setText(f"{entry.name}\n\n类型：{'链接（受限）' if entry.is_link else '未知' if entry.is_directory is None else '文件夹' if entry.is_directory else '文件'}\n大小：{size}\n修改时间：{entry.modified or '未知'}\n访问状态：{entry.access_status}\n后端来源：{entry.backend_source}\n\n{note}\n\n写入禁用：{self.block_reason}")
            self.select_preview(entry)

    def open_entry(self, index) -> None:
        entry = index.data(Qt.ItemDataRole.UserRole)
        backend = entry.backend_source if entry else ""
        reason = self.policy.entry_reason(entry, backend) if entry else ""
        if reason:
            self.report_error(reason)
        elif entry and entry.is_directory:
            try:
                self.navigate(self.location.child(entry.name))
            except ValueError as exc:
                self.report_error(user_message(exc))
        elif entry:
            self.show_entry(index)
            self.statusBar().showMessage("正在只读预览，不执行或外部打开文件")

    def open_address(self) -> None:
        if isinstance(self.source, InventoryBrowserSource):
            try:
                address = self.address.text().strip()
                if address.startswith("/") and self.location and self.location.partition_id in self.source.ext4:
                    relative = address[1:].rstrip("/")
                    validate_path(relative)
                    location = Location(self.location.partition_id, relative)
                else:
                    location = self.source.resolve_address(address)
                self.partitions = {p.id: p for p in self.source.partitions()}
                if location.partition_id in self.source.network:
                    self.partition_model.add_network(self.partitions[location.partition_id])
                self.navigate(location)
            except (ValueError, Ext4Error) as exc:
                self.report_error(user_message(exc))
            return
        partition_id, separator, path = self.address.text().strip().partition(":/")
        if not separator or "\\" in path or any(p in (".", "..", "") for p in path.split("/") if path):
            self.report_error("地址格式无效，请使用 mock-c:/用户文档 形式")
            return
        try:
            self.navigate(Location(partition_id, path))
        except ValueError as exc:
            self.report_error(user_message(exc))

    def move_history(self, delta: int) -> None:
        target = self.history_index + delta
        if 0 <= target < len(self.history):
            self.history_index = target
            self.navigate(self.history[target], record=False)

    def go_up(self) -> None:
        if self.location and self.location.relative_path:
            self.navigate(self.location.parent)

    def refresh(self) -> None:
        if self.location:
            self.navigate(self.location, record=False)
        elif self.inventory_service is not None:
            self.scan_inventory()

    def cancel_directory(self) -> None:
        self.cancel_preview()
        self.pending_directory = None
        self.next_offset = None
        self.fingerprint = ""
        self.more_button.setVisible(False)
        if self.directory_worker:
            self.directory_worker.requestInterruption()

    def cancel_preview(self) -> None:
        self.preview_request_id += 1
        self.pending_preview = None
        self.preview_location = None
        self.preview_result = None
        self.preview_limit = TEXT_LIMIT
        if self.preview_worker:
            self.preview_worker.requestInterruption()
        self.preview_panel.clear()

    def select_preview(self, entry) -> None:
        self.cancel_preview()
        if entry.is_directory is not False:
            return
        reason = self.policy.entry_reason(entry, entry.backend_source)
        if reason:
            self.preview_panel.clear(reason)
            return
        if not isinstance(self.source, InventoryBrowserSource) or not self.location:
            self.preview_panel.clear("模拟数据没有实际文件内容")
            return
        try:
            self.preview_location = self.location.child(entry.name)
        except ValueError as exc:
            self.preview_panel.clear(user_message(exc))
            return
        self.preview_panel.encoding.blockSignals(True)
        self.preview_panel.encoding.setCurrentIndex(0)
        self.preview_panel.encoding.blockSignals(False)
        self.queue_preview()

    def queue_preview(self) -> None:
        if not self.preview_location or not isinstance(self.source, InventoryBrowserSource):
            return
        self.preview_request_id += 1
        if self.preview_worker:
            self.preview_worker.requestInterruption()
        try:
            target = self.preview_location
            self.pending_preview = dict(request_id=self.preview_request_id, location=target,
                root=self.source.roots.get(target.partition_id, ""), backend_spec=self.source.request_spec(target.partition_id),
                byte_limit=self.preview_limit, encoding=ENCODINGS[self.preview_panel.encoding.currentIndex()],
                parent=self, timeout=45 if target.partition_id in self.source.ext4 else 15)
        except ValueError as exc:
            self.preview_failed(self.preview_request_id, user_message(exc))
            return
        self.preview_panel.clear("正在后台只读加载预览…")
        if not self.preview_worker:
            self.launch_preview()

    def launch_preview(self) -> None:
        if not self.pending_preview:
            return
        arguments, self.pending_preview = self.pending_preview, None
        self.preview_worker = PreviewWorker(**arguments)
        self.preview_worker.succeeded.connect(self.preview_ready)
        self.preview_worker.failed.connect(self.preview_failed)
        self.preview_worker.finished.connect(self.preview_finished)
        self.preview_worker.start()

    def preview_ready(self, request_id: int, result: PreviewResult) -> None:
        if request_id != self.preview_request_id or self.close_pending:
            return
        if not self.preview_location or (result.partition_id, result.relative_path) != (self.preview_location.partition_id, self.preview_location.path):
            return
        self.preview_result = result
        self.preview_panel.show_result(result, self.preview_limit, self.partitions[result.partition_id].name)

    def preview_failed(self, request_id: int, message: str) -> None:
        if request_id != self.preview_request_id or self.close_pending:
            return
        self.preview_result = None
        self.preview_panel.clear(message)
        if self.preview_location:
            from pathlib import PurePosixPath
            self.preview_panel.encoding.setEnabled(PurePosixPath(self.preview_location.path).suffix.lower() in TEXT_TYPES)
        self.statusBar().showMessage("预览失败：" + message)
        self.logger.error("只读预览未完成")

    def reload_preview(self) -> None:
        self.queue_preview()

    def more_preview(self) -> None:
        if self.preview_limit < MAX_TEXT_LIMIT:
            self.preview_limit = min(MAX_TEXT_LIMIT, self.preview_limit + TEXT_LIMIT)
            self.queue_preview()

    def preview_finished(self) -> None:
        if self.preview_worker:
            self.preview_worker.deleteLater()
            self.preview_worker = None
        if self.close_pending:
            self.close()
        else:
            self.launch_preview()

    def start_directory(self, offset: int = 0) -> None:
        if not isinstance(self.source, InventoryBrowserSource) or not self.location:
            return
        self.loading = True
        self.load_failed = False
        self.more_button.setEnabled(False)
        if not offset:
            self.show_message("正在后台验证身份并只读加载目录…")
        self.pending_directory = dict(request_id=self.request_id, location=self.location,
            root=self.source.roots.get(self.location.partition_id, ""), show_hidden=self.config.show_hidden_files,
            offset=offset, fingerprint=self.fingerprint, parent=self)
        try:
            self.pending_directory["backend_spec"] = self.source.request_spec(self.location.partition_id)
        except ValueError as exc:
            self.report_error(user_message(exc))
            return
        if self.location.partition_id in self.source.ext4:
            self.pending_directory["timeout"] = 45
        if not self.directory_worker:
            self.launch_directory()

    def launch_directory(self) -> None:
        if not self.pending_directory:
            return
        arguments, self.pending_directory = self.pending_directory, None
        self.directory_worker = DirectoryWorker(**arguments)
        self.directory_worker.succeeded.connect(self.directory_ready)
        self.directory_worker.failed.connect(self.directory_failed)
        self.directory_worker.finished.connect(self.directory_finished)
        self.directory_worker.start()

    def load_more(self) -> None:
        if self.next_offset is not None and not self.loading:
            self.start_directory(self.next_offset)

    def directory_ready(self, request_id: int, page: DirectoryPage) -> None:
        if request_id != self.request_id or self.close_pending:
            return
        self.loading = False
        if page.source_info and isinstance(self.source, InventoryBrowserSource):
            spec = self.source.ext4[self.location.partition_id]
            spec["fingerprint"] = page.source_info["fingerprint"]
            spec["probe"] = page.source_info
            self.partitions = {p.id: p for p in self.source.partitions()}
            self.show_partition()
            self.properties.setText(self.properties.text() + f"\n\next4 UUID：{page.source_info['uuid']}\n卷标：{page.source_info['label']}\n只读探测通过；不提供任何写入接口。")
            self.mark_partition_status(self.location.partition_id, "只读 ext4")
        self.fingerprint = page.fingerprint
        self.next_offset = page.next_offset
        self.file_model.append_entries(page.entries)
        self.more_button.setVisible(page.next_offset is not None)
        self.more_button.setEnabled(True)
        self.filter_entries(self.search.text())

    def directory_failed(self, request_id: int, message: str) -> None:
        if request_id != self.request_id or self.close_pending:
            return
        self.report_error(message)

    def report_error(self, message: str) -> None:
        self.request_id += 1
        self.cancel_directory()
        self.loading, self.load_failed = False, True
        self.show_message(message)
        self.statusBar().showMessage(message)
        self.logger.error("只读导航操作未完成")

    def directory_finished(self) -> None:
        if self.directory_worker:
            self.directory_worker.deleteLater()
            self.directory_worker = None
        if self.close_pending:
            self.close()
        else:
            self.launch_directory()

    def scan_inventory(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if self.search_dialog:
            self.search_dialog.invalidate()
        self.global_search_action.setEnabled(False)
        self.request_id += 1
        self.cancel_directory()
        self.location = None
        self.update_breadcrumbs()
        self.inventory = None
        self.partitions = {}
        self.source = InventoryBrowserSource(DiskInventory((), (), ()))
        self.history.clear()
        self.history_index = -1
        self.file_model.set_entries(())
        self.partition_model.clear()
        self.address.clear()
        self.address.setEnabled(False)
        for action in (self.back_action, self.forward_action, self.up_action):
            action.setEnabled(False)
        self.path_label.setText("Windows Storage · 只读磁盘清单")
        self.show_message("正在后台扫描磁盘与分区，请稍候…")
        self.properties.setText("仅查询磁盘元数据，不读取文件或修改分区。")
        self.refresh_action.setEnabled(False)
        self.scan_action.setEnabled(False)
        self.statusBar().showMessage("扫描中，可继续移动窗口或切换主题")
        self.worker = InventoryWorker(self.inventory_service, self)
        self.worker.succeeded.connect(self.inventory_ready)
        self.worker.failed.connect(self.inventory_failed)
        self.worker.finished.connect(self.scan_finished)
        self.worker.start()

    def inventory_ready(self, inventory: DiskInventory) -> None:
        self.inventory = inventory
        self.address.setEnabled(True)
        self.global_search_action.setEnabled(True)
        self.source = InventoryBrowserSource(inventory)
        self.partitions = {p.id: p for p in self.source.partitions()}
        old_model = self.partition_model
        self.partition_model = InventoryTreeModel(inventory, self)
        self.tree.setModel(self.partition_model)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.selectionModel().currentChanged.connect(self.select_partition)
        old_model.deleteLater()
        self.tree.expandAll()
        for partition_id in self.source.ext4:
            self.mark_partition_status(partition_id, "待验证")
        self.statusBar().showMessage(f"发现 {len(inventory.disks)} 个磁盘、{len(inventory.partitions)} 个分区、{len(inventory.volumes)} 个卷")
        self.show_message("选择普通 Windows 分区只读浏览；受保护或未知分区仅展示元数据。" if inventory.disks else "未发现物理磁盘，设备可能已断开。可点击刷新重试。")
        self.logger.info("磁盘元数据扫描完成：%d 个磁盘，%d 个分区", len(inventory.disks), len(inventory.partitions))

    def mark_partition_status(self, partition_id: str, status: str) -> None:
        indexes = self.partition_model.match(self.partition_model.index(0, 0), Qt.ItemDataRole.UserRole,
            partition_id, 1, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
        if indexes:
            index = indexes[0]
            self.partition_model.setData(index.siblingAtColumn(1), status)
            self.partition_model.setData(index.siblingAtColumn(1), self.partitions[partition_id].reason,
                                         Qt.ItemDataRole.ToolTipRole)

    def inventory_failed(self, message: str) -> None:
        self.report_error(message + "\n点击刷新可重试。")

    def scan_finished(self) -> None:
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        self.refresh_action.setEnabled(True)
        self.scan_action.setEnabled(True)
        if self.close_pending:
            self.close()

    def explain_write_block(self) -> None:
        self.statusBar().showMessage(self.block_reason)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.search_dialog and self.search_dialog.worker:
            self.close_pending = True
            self.search_dialog.cancel()
            event.ignore()
            return
        if self.preview_worker:
            self.close_pending = True
            self.cancel_preview()
            event.ignore()
            return
        if self.directory_worker:
            self.close_pending = True
            self.request_id += 1
            self.cancel_directory()
            event.ignore()
            return
        if self.worker and self.worker.isRunning():
            self.close_pending = True
            self.statusBar().showMessage("正在等待只读扫描结束后退出（查询有超时限制）…")
            event.ignore()
            return
        self.request_id += 1
        try:
            size = self.normalGeometry().size() if self.isMaximized() else self.size()
            self.store.save(replace(self.config, window_width=min(7680, size.width()),
                                    window_height=min(4320, size.height())))
        except OSError as exc:
            self.logger.error("配置保存失败：%s", type(exc).__name__)
            QMessageBox.warning(self, "配置保存失败", "无法保存窗口配置，本次设置不会保留。")
        self.logger.info("应用正常退出")
        event.accept()
