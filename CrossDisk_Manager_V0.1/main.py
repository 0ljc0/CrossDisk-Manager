"""CrossDisk Manager V0.3：分区关联、统一只读适配器与权限信息。"""
from __future__ import annotations

import ctypes
import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSignalBlocker
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QStackedWidget, QStyle, QInputDialog,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QMainWindow,
)

from storage_scan import partition_kind, is_protected_partition, scan_storage
from preview_utils import decode_preview
from fs_adapters import ReadOnlyMountedAdapter
from volume_links import DriveInfo, drive_mode_text, probe_drives, resolve_verified_links

TEXT_SUFFIXES = {
    '.txt', '.py', '.md', '.json', '.yaml', '.yml', '.xml',
    '.csv', '.ini', '.cfg', '.log', '.sh', '.c', '.h',
    '.cpp', '.hpp', '.java', '.js', '.ts', '.html', '.css',
    '.sql', '.toml', '.conf',
}
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}
MAX_ENTRIES = 5000
PREVIEW_BYTES = 128 * 1024


def mounted_drives() -> list[str]:
    """仅列出已挂载且可被 Windows 正常访问的盘符。"""
    if os.name != 'nt':
        return ['/']
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    found = []
    for i in range(26):
        if mask & (1 << i):
            root = f'{chr(65 + i)}:\\'
            if os.path.isdir(root):
                found.append(root)
    return found


def human_size(n: int | float | None) -> str:
    if n is None:
        return '未知'
    number = max(0, int(n))
    if number < 1024:
        return f'{number} B'
    size = float(number)
    for unit in ('KiB', 'MiB', 'GiB', 'TiB', 'PiB'):
        size /= 1024
        if size < 1024:
            return f'{size:.2f} {unit}'
    return f'{size:.2f} EiB'


class StorageWorker(QThread):
    """将耗时的 PowerShell 磁盘扫描从 Qt 主线程移出去。"""
    result_ready = Signal(object, str)

    def run(self) -> None:
        try:
            data = scan_storage()
            data['drive_probes'] = probe_drives(mounted_drives())
            self.result_ready.emit(data, '')
        except Exception as exc:  # 扫描失败不能导致 GUI 退出
            self.result_ready.emit(None, str(exc))


class CrossDiskWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.current_path: Path | None = None
        self.current_adapter: ReadOnlyMountedAdapter | None = None
        self.drive_probes: list[DriveInfo] = []
        self.verified_links: dict[tuple[int, int], tuple[str, str]] = {}
        self.manual_links: dict[tuple[int, int], tuple[str, str]] = {}
        self.storage_data: dict | None = None
        self.scan_error = ''
        self.scanner: StorageWorker | None = None
        self.close_after_scan = False
        self.setWindowTitle('CrossDisk Manager · V0.3 分区关联 / 全局只读')
        self.resize(1350, 780)
        self.setMinimumSize(940, 570)
        self.setup_ui()
        self.refresh()

    def setup_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        heading = QLabel('CrossDisk Manager    /    跨分区文件管理器')
        heading.setObjectName('heading')
        layout.addWidget(heading)

        bar = QHBoxLayout()
        self.up_button = QPushButton('↑ 上一级')
        self.refresh_button = QPushButton('⟳ 刷新分区与目录')
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText('当前文件路径，例如 E:\\home\\ljc')
        self.go_button = QPushButton('前往')
        for widget in (self.up_button, self.refresh_button, self.path_edit, self.go_button):
            bar.addWidget(widget)
        bar.setStretch(2, 1)
        layout.addLayout(bar)

        panes = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(panes, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.addWidget(QLabel('磁盘 / 分区与已挂载盘符'))
        self.navigation = QTreeWidget()
        self.navigation.setHeaderHidden(True)
        self.navigation.setMinimumWidth(255)
        left_layout.addWidget(self.navigation)
        self.scan_label = QLabel('后台正在扫描分区…')
        self.scan_label.setWordWrap(True)
        left_layout.addWidget(self.scan_label)
        self.partition_details_button = QPushButton('查看所选分区属性')
        self.partition_details_button.clicked.connect(self.show_selected_partition_details)
        left_layout.addWidget(self.partition_details_button)
        self.associate_button = QPushButton('手动关联选中分区（仅本次会话）')
        self.associate_button.clicked.connect(self.associate_selected_partition)
        left_layout.addWidget(self.associate_button)
        left_note = QLabel('点击已验证关联的分区可直接浏览。\n未验证的分区只展示信息；人工关联只读且不代表物理确认。')
        left_note.setWordWrap(True)
        left_layout.addWidget(left_note)
        panes.addWidget(left)

        middle = QWidget()
        mid_layout = QVBoxLayout(middle)
        mid_layout.setContentsMargins(4, 4, 4, 4)
        mid_layout.addWidget(QLabel('文件列表（双击进入目录，单击只读预览）'))
        self.files = QTableWidget(0, 4)
        self.files.setHorizontalHeaderLabels(['名称', '类型', '大小', '修改时间'])
        self.files.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.files.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.files.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.files.verticalHeader().hide()
        self.files.setAlternatingRowColors(True)
        self.files.setColumnWidth(0, 285)
        self.files.setColumnWidth(1, 85)
        self.files.setColumnWidth(2, 100)
        self.files.horizontalHeader().setStretchLastSection(True)
        mid_layout.addWidget(self.files)
        panes.addWidget(middle)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.addWidget(QLabel('分区信息 / 文件预览（全局只读）'))
        self.preview_stack = QStackedWidget()
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlainText('选择一个磁盘、分区或文件查看信息。')
        self.preview_image = QLabel()
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setWordWrap(True)
        self.preview_stack.addWidget(self.preview_text)
        self.preview_stack.addWidget(self.preview_image)
        right_layout.addWidget(self.preview_stack)
        panes.addWidget(right)
        panes.setSizes([310, 625, 380])

        self.statusBar().showMessage('V0.3 全局只读：不写入文件或磁盘，不改变挂载状态')
        self.navigation.itemClicked.connect(self.navigation_clicked)
        self.files.itemDoubleClicked.connect(self.file_double_clicked)
        self.files.itemClicked.connect(self.preview_clicked)
        self.files.itemSelectionChanged.connect(self.preview_selected)
        self.up_button.clicked.connect(self.go_up)
        self.refresh_button.clicked.connect(self.refresh)
        self.go_button.clicked.connect(self.go_to_address)
        self.path_edit.returnPressed.connect(self.go_to_address)

    def add_node(self, parent: QTreeWidgetItem, label: str, kind: str, payload: object,
                 icon: object | None = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [label])
        item.setData(0, Qt.ItemDataRole.UserRole, (kind, payload))
        if icon is not None:
            item.setIcon(0, icon)
        return item

    def populate_navigation(self) -> None:
        self.navigation.clear()
        disk_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        folder_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        info_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView)
        disk_root = QTreeWidgetItem(self.navigation, ['物理磁盘 / 全部分区'])
        disk_root.setIcon(0, disk_icon)
        disk_root.setData(0, Qt.ItemDataRole.UserRole, ('group', 'physical'))
        disks = self.storage_data.get('disks', []) if self.storage_data else []
        parts = self.storage_data.get('partitions', []) if self.storage_data else []
        for disk in sorted(disks, key=lambda d: int(d.get('number', 0))):
            num = int(disk.get('number', 0))
            d_item = self.add_node(
                disk_root,
                f'磁盘 {num}  {disk.get("name") or "未知设备"}  ({human_size(disk.get("size"))})',
                'disk', disk, disk_icon,
            )
            belongs = sorted((p for p in parts if int(p.get('disk_number', -1)) == num),
                             key=lambda p: int(p.get('offset', 0)))
            for part in belongs:
                pnum = int(part.get('partition_number', 0))
                kind = partition_kind(part)
                drive = str(part.get('drive_letter') or '').upper()
                suffix = f'  [{drive}:]' if drive else ''
                hidden = ' · 隐藏' if part.get('is_hidden') else ''
                key = (num, pnum)
                linked = self.verified_links.get(key) or self.manual_links.get(key)
                badge = f' → {linked[0]}（{"验证" if key in self.verified_links else "人工"}）' if linked else ''
                self.add_node(
                    d_item, f'分区 {pnum}  {kind}  {human_size(part.get("size"))}{suffix}{hidden}{badge}',
                    'partition', part, info_icon,
                )
            d_item.setExpanded(True)
        disk_root.setExpanded(True)
        if not disks:
            label = '扫描中…' if self.scanner and self.scanner.isRunning() else '无法获得磁盘信息（不影响已挂载盘符）'
            self.add_node(disk_root, label, 'placeholder', None)

        drives = mounted_drives()
        drive_root = QTreeWidgetItem(self.navigation, [f'已挂载盘符（{len(drives)}）'])
        drive_root.setData(0, Qt.ItemDataRole.UserRole, ('group', 'drives'))
        drive_root.setIcon(0, folder_icon)
        for drive in drives:
            info = next((d for d in self.drive_probes if d.root.upper() == drive.upper()), None)
            label = f'{drive}  {info.filesystem or "文件系统未知"}' if info else f'{drive}  可浏览'
            self.add_node(drive_root, label, 'drive', drive, disk_icon)
        drive_root.setExpanded(True)

    def navigation_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        kind, data = item.data(0, Qt.ItemDataRole.UserRole) or ('placeholder', None)
        if kind == 'drive':
            self.open_dir(Path(data))
        elif kind == 'disk':
            self.show_disk_info(data)
        elif kind == 'partition':
            key = (int(data['disk_number']), int(data['partition_number']))
            linked = self.verified_links.get(key) or self.manual_links.get(key)
            if linked and not is_protected_partition(data):
                self.open_dir(Path(linked[0]))
                evidence = '自动验证' if key in self.verified_links else '本次会话人工关联，物理归属未经验证'
                self.statusBar().showMessage(f'{linked[0]} · {evidence} · 本程序禁止任何写入')
            else:
                self.show_partition_info(data)

    def show_selected_partition_details(self) -> None:
        item = self.navigation.currentItem()
        kind, part = item.data(0, Qt.ItemDataRole.UserRole) if item else (None, None)
        if kind == 'partition':
            self.show_partition_info(part)
        else:
            QMessageBox.information(self, '请先选择分区', '请先选中左侧的分区节点。')

    def associate_selected_partition(self) -> None:
        item = self.navigation.currentItem()
        kind, part = item.data(0, Qt.ItemDataRole.UserRole) if item else (None, None)
        if kind != 'partition':
            QMessageBox.information(self, '请先选择分区', '请先在左侧选择一个分区，再进行人工关联。')
            return
        if is_protected_partition(part):
            QMessageBox.warning(self, '受保护分区', 'EFI、MSR、Recovery 不允许在程序中建立文件浏览关联。')
            return
        key = (int(part['disk_number']), int(part['partition_number']))
        if key in self.verified_links:
            QMessageBox.information(self, '已自动验证', '此分区已有 Windows 报告的关联，无需人工选择。')
            return
        assigned = {root.upper() for key0, (root, _reason) in self.verified_links.items() if key0 != key}
        drives = [root for root in mounted_drives() if root.upper() not in assigned]
        if partition_kind(part) == 'Linux 文件系统分区':
            native_fs = {'NTFS', 'REFS', 'FAT', 'FAT32', 'EXFAT'}
            drives = [root for root in drives if not any(
                di.root.upper() == root.upper() and di.filesystem.upper() in native_fs
                for di in self.drive_probes)]
        if not drives:
            QMessageBox.information(self, '无可用盘符', '没有可以人工关联的盘符。请先确认 Paragon 已挂载对应卷。')
            return
        chosen, ok = QInputDialog.getItem(self, '只读人工关联',
            '选择你已经在驱动管理器中确认的盘符。\n'
            '注意：此关联不能证明盘符与物理分区匹配，只在本次会话有效。',
            drives, 0, False)
        if not ok:
            return
        answer = QMessageBox.question(self, '确认人工关联',
            f'将磁盘 {key[0]} 分区 {key[1]} 临时关联为 {chosen}？\n'
            '软件不会挂载磁盘或写入数据。关联错误会导致浏览错误的盘符。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.manual_links[key] = (chosen, '人工关联：仅本次会话，物理对应未经验证')
        self.populate_navigation()
        self.open_dir(Path(chosen))
        self.statusBar().showMessage(f'人工关联 {chosen} · 仅本次会话 · 只读')

    def show_info(self, message: str) -> None:
        self.preview_stack.setCurrentIndex(0)
        self.preview_text.setPlainText(message)
        self.files.setRowCount(0)
        self.current_path = None
        self.current_adapter = None
        self.path_edit.clear()

    def show_disk_info(self, disk: dict) -> None:
        number = disk.get('number')
        count = sum(int(p.get('disk_number', -1)) == int(number)
                    for p in (self.storage_data or {}).get('partitions', []))
        self.show_info('\n'.join([
            f'磁盘 {number}', '',
            f'名称：{disk.get("name") or "未知"}',
            f'容量：{human_size(disk.get("size"))}',
            f'分区样式：{disk.get("partition_style") or "未知"}',
            f'总线：{disk.get("bus_type") or "未知"}',
            f'健康状态：{disk.get("health") or "未知"}',
            f'运行状态：{disk.get("operational") or "未知"}',
            f'已识别分区数：{count}', '',
            '这是磁盘属性页面，不会打开物理磁盘进行原始扇区写入。',
        ]))
        self.statusBar().showMessage(f'磁盘 {number} · 信息查看模式')

    def show_partition_info(self, part: dict) -> None:
        letter = str(part.get('drive_letter') or '').upper()
        file_system = str(part.get('file_system') or '')
        label = str(part.get('volume_label') or '')
        kind = partition_kind(part)
        protected = is_protected_partition(part)
        # 重要：没有盘符、文件系统未知或 Paragon 的映射不明确时不猜测任何可浏览路径。
        note = ('此分区属于 EFI / MSR / Recovery 等系统分区，程序不提供分区操作入口。'
                if protected else
                '如有已挂载盘符，请在左侧「已挂载盘符」中访问；否则仅展示属性。')
        key = (int(part.get('disk_number', -1)), int(part.get('partition_number', -1)))
        linked = self.verified_links.get(key) or self.manual_links.get(key)
        evidence = linked[1] if linked else '无可确认的盘符关联（可能是驱动未提供物理 extent 信息）'
        details = [
            f'磁盘 {part.get("disk_number")} · 分区 {part.get("partition_number")}', '',
            f'分区类型：{kind}',
            f'Windows 原始类型：{part.get("type") or "未知"}',
            f'GPT 类型 GUID：{part.get("gpt_type") or "未提供"}',
            f'容量：{human_size(part.get("size"))}',
            f'起始偏移量：{part.get("offset", "未知")} 字节',
            f'Windows 识别文件系统：{file_system or "未识别 / 未提供"}',
            f'卷标：{label or "无 / 未提供"}',
            f'隐藏分区：{"是" if part.get("is_hidden") else "否"}',
            f'分区属性只读：{"是" if part.get("is_read_only") else "否"}',
            f'Windows 分区对象报告的盘符：{letter + ":" if letter else "无"}',
            f'剩余空间：{human_size(part.get("free_space")) if file_system else "无法确定"}',
            f'关联路径：{linked[0] if linked else "未验证"}',
            f'关联依据：{evidence}',
            '程序文件权限：仅允许只读操作',
            '', note, '',
            '注意：Windows 分区 IsReadOnly 属性，不代表 Paragon 当前挂载会话的只读/读写状态。',
            '本版本不会更改分区隐藏属性、分配盘符、挂载/卸载或格式化分区。',
        ]
        self.show_info('\n'.join(details))
        self.statusBar().showMessage(f'分区 {part.get("partition_number")} · 仅查看属性')

    def begin_scan(self) -> None:
        if self.scanner is not None and self.scanner.isRunning():
            self.scan_label.setText('后台正在扫描分区，请稍候…')
            return
        self.scan_label.setText('后台正在扫描所有物理磁盘和分区…')
        self.scanner = StorageWorker(self)
        self.scanner.result_ready.connect(self.on_scan_complete)
        self.scanner.finished.connect(self.on_scan_thread_finished)
        self.scanner.start()

    def on_scan_complete(self, data: object, error: str) -> None:
        if error:
            self.storage_data = None
            self.scan_error = error
            self.scan_label.setText('分区扫描失败（仍可浏览已挂载盘符）。')
            self.statusBar().showMessage('分区扫描失败：' + error[:160])
        else:
            self.storage_data = data
            self.drive_probes = data.get('drive_probes', [])
            self.verified_links = resolve_verified_links(data.get('partitions', []), self.drive_probes)
            self.manual_links.clear()  # 刷新后需要重新人工确认，不永久缓存映射
            self.scan_error = ''
            n_disks = len(data.get('disks', []))
            n_parts = len(data.get('partitions', []))
            self.scan_label.setText(f'已识别 {n_disks} 块磁盘、{n_parts} 个分区；自动关联 {len(self.verified_links)} 个')
            self.statusBar().showMessage(f'磁盘信息扫描完成：{n_disks} 块磁盘，{n_parts} 个分区 · 只读')
        self.populate_navigation()

    def on_scan_thread_finished(self) -> None:
        if self.close_after_scan:
            self.close()

    def closeEvent(self, event) -> None:
        # 防止扫描仍在运行时销毁 QThread 引发崩溃。
        if self.scanner is not None and self.scanner.isRunning():
            self.close_after_scan = True
            self.statusBar().showMessage('分区扫描正在结束，结束后窗口将自动关闭…')
            event.ignore()
            return
        super().closeEvent(event)

    def refresh(self) -> None:
        path = self.current_path
        self.populate_navigation()
        drives = mounted_drives()
        if path and os.path.isdir(path):
            self.open_dir(path)
        elif drives:
            self.open_dir(Path(drives[0]))
        else:
            self.show_info('未检测到可浏览的盘符；可以点击左侧物理磁盘查看分区信息。')
        self.begin_scan()

    def _adapter_for_path(self, path: Path) -> ReadOnlyMountedAdapter:
        # 本程序只通过已挂载的文件系统路径访问；未挂载分区不能自动打开。
        protected_roots = set()
        for part in (self.storage_data or {}).get('partitions', []):
            if is_protected_partition(part):
                key = (int(part['disk_number']), int(part['partition_number']))
                linked = self.verified_links.get(key)
                if linked:
                    protected_roots.add(linked[0].upper())
                letter = str(part.get('drive_letter') or '').strip().upper()
                if len(letter) == 1 and letter.isalpha():
                    protected_roots.add(letter + ':\\')
        for root in mounted_drives():
            if root.upper() in protected_roots:
                continue
            try:
                candidate = ReadOnlyMountedAdapter(root)
                candidate._within_root(path)
                return candidate
            except PermissionError:
                continue
        raise PermissionError('目标不在当前已挂载的盘符内，或是系统保护的路径')

    def open_dir(self, path: Path) -> None:
        try:
            adapter = self._adapter_for_path(path)
            if not path.is_dir():
                raise NotADirectoryError(f'路径不是文件夹：{path}')
            entries, truncated = adapter.list_dir(path, MAX_ENTRIES)
        except (OSError, ValueError, PermissionError) as exc:
            QMessageBox.warning(self, '无法访问目录', str(exc))
            return
        self.current_path = path
        self.current_adapter = adapter
        self.path_edit.setText(str(path))
        with QSignalBlocker(self.files):
            self.files.clearSelection()
            self.files.setRowCount(0)
            self.files.setRowCount(len(entries))
            dir_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
            file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            for row, record in enumerate(entries):
                first = QTableWidgetItem(dir_icon if record.is_dir else file_icon, record.name)
                first.setData(Qt.ItemDataRole.UserRole, (str(record.path), record.is_dir))
                values = [first, QTableWidgetItem('文件夹' if record.is_dir else '文件'),
                          QTableWidgetItem('' if record.is_dir else human_size(record.size)),
                          QTableWidgetItem(record.modified)]
                for col, value in enumerate(values):
                    self.files.setItem(row, col, value)
            self.files.setCurrentCell(-1, -1)
        self.preview_stack.setCurrentIndex(0)
        self.preview_text.setPlainText('选择一个文件查看内容；全局只读，不会修改磁盘。')
        suffix = '（仅展示前 5000 项）' if truncated else ''
        drive = next((d for d in self.drive_probes if str(path).upper().startswith(d.root.upper())), None)
        state = drive_mode_text(drive) if drive else '卷只读标志未探测'
        self.statusBar().showMessage(f'{path} | {len(entries)} 项{suffix} | 程序只读 | {state}')

    def selected_entry(self, row: int | None = None) -> tuple[str, bool] | None:
        # 不再依赖 selectedItems()：用户点击表格其他列也能预览对应文件。
        if row is None:
            row = self.files.currentRow()
        if row < 0 or row >= self.files.rowCount():
            return None
        first = self.files.item(row, 0)
        return first.data(Qt.ItemDataRole.UserRole) if first else None

    def file_double_clicked(self, item: QTableWidgetItem) -> None:
        entry = self.selected_entry(item.row())
        if not entry:
            return
        if entry[1]:
            self.open_dir(Path(entry[0]))
        else:
            self.preview_row(item.row())  # 双击文件也明确触发预览，不执行文件

    def preview_clicked(self, item: QTableWidgetItem) -> None:
        self.preview_row(item.row())

    def preview_selected(self) -> None:
        self.preview_row(self.files.currentRow())

    def preview_row(self, row: int) -> None:
        entry = self.selected_entry(row)
        if not entry:
            return
        full_path, is_dir = entry
        path = Path(full_path)
        self.preview_stack.setCurrentIndex(0)
        if is_dir:
            self.preview_text.setPlainText(f'文件夹：\n{path}\n\n双击进入。')
            return
        try:
            adapter = self.current_adapter or self._adapter_for_path(path)
            size = adapter.stat(path).st_size
            if path.suffix.lower() in TEXT_SUFFIXES:
                content = adapter.read_bytes(path, PREVIEW_BYTES)
                result, encoding = decode_preview(content)
                if size > PREVIEW_BYTES:
                    result += '\n\n[预览已截断，仅展示前 128 KiB]'
                self.preview_text.setPlainText(result)
                self.statusBar().showMessage(
                    f'已预览：{path.name} | {human_size(size)} | {encoding} | 只读'
                )
            elif path.suffix.lower() in IMAGE_SUFFIXES and size <= 10 * 1024 * 1024:
                picture = QPixmap()
                picture.loadFromData(adapter.read_bytes(path, 10 * 1024 * 1024))
                if picture.isNull():
                    self.preview_text.setPlainText('图片格式无法预览。')
                else:
                    self.preview_image.setPixmap(picture.scaled(
                        340, 460, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))
                    self.preview_stack.setCurrentIndex(1)
            else:
                self.preview_text.setPlainText(
                    f'文件：{path.name}\n大小：{human_size(size)}\n位置：{path}\n\n'
                    '当前版本不预览此类型（不会执行文件）。')
        except (OSError, ValueError, UnicodeError, PermissionError) as exc:
            self.preview_stack.setCurrentIndex(0)
            self.preview_text.setPlainText(f'读取失败：{path}\n\n{type(exc).__name__}: {exc}')
            self.statusBar().showMessage(f'预览失败：{path.name}')

    def go_up(self) -> None:
        if self.current_path and self.current_path.parent != self.current_path:
            try:
                self._adapter_for_path(self.current_path.parent)
            except PermissionError:
                return
            self.open_dir(self.current_path.parent)

    def go_to_address(self) -> None:
        raw = self.path_edit.text().strip().strip('"')
        if raw:
            self.open_dir(Path(raw))


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet('''
        QWidget { background: #141c2b; color: #e7ebf3; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
        QLabel#heading { font-size: 20px; font-weight: bold; padding: 5px 0 8px; }
        QPushButton { background: #25344c; border: 1px solid #344863; padding: 9px 14px; border-radius: 6px; }
        QPushButton:hover { background: #324963; }
        QLineEdit, QTreeWidget, QTableWidget, QPlainTextEdit { background: #1a2538; border: 1px solid #344863; border-radius: 5px; padding: 5px; }
        QTreeWidget::item:selected, QTableWidget::item:selected { background: #28517a; }
        QTreeWidget::item { padding: 3px; }
        QHeaderView::section { background: #25344c; padding: 8px; border: none; }
        QSplitter::handle { background: #344863; width: 3px; }
        QStatusBar { background: #182336; }
    ''')
    window = CrossDiskWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
