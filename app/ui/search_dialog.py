"""用户显式启动的元数据扫描，没有监控、内容索引或网络上传。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
                               QTableView, QVBoxLayout, QWidget)

from app.core.search import SearchLimits, SearchQuery
from app.jobs.search_worker import SearchWorker
from app.ui.search_models import SearchResultsModel


class SearchDialog(QDialog):
    locate_requested = Signal(object)
    idle = Signal()

    def __init__(self, source_builder, parent=None):
        super().__init__(parent)
        self.source_builder = source_builder
        self.worker = None
        self.generation = 0
        self.close_pending = False
        self.stats = {}
        self.setWindowTitle("文件名与属性搜索 · 只读")
        self.resize(1200, 740)
        layout = QVBoxLayout(self)
        self.form = QWidget()
        grid = QGridLayout(self.form)
        self.scope = QComboBox()
        self.scope.addItems(["当前目录（递归）", "当前分区（递归）", "全部已验证分区（递归）"])
        self.pattern = QLineEdit("*.py")
        self.pattern.setMaxLength(256)
        self.extensions = QLineEdit()
        self.extensions.setPlaceholderText(".py,.md")
        self.path_filter = QLineEdit()
        self.path_filter.setMaxLength(512)
        self.entry_type = QComboBox()
        for title, value in (("全部类型", "all"), ("文件", "file"), ("目录", "directory"), ("链接（不跟随）", "link")):
            self.entry_type.addItem(title, value)
        self.case = QComboBox()
        for title in ("大小写按后端", "不区分大小写", "区分大小写"):
            self.case.addItem(title)
        self.min_size, self.max_size, self.date_from, self.date_to = [QLineEdit() for _ in range(4)]
        self.depth, self.result_limit = QSpinBox(), QSpinBox()
        self.depth.setRange(1, 64)
        self.depth.setValue(32)
        self.result_limit.setRange(1, 10000)
        self.result_limit.setValue(5000)
        fields = [("范围", self.scope), ("名称/通配符", self.pattern), ("扩展名", self.extensions),
                  ("路径包含/通配符", self.path_filter), ("类型", self.entry_type), ("大小写", self.case),
                  ("最小字节数", self.min_size), ("最大字节数", self.max_size),
                  ("修改起日 YYYY-MM-DD", self.date_from), ("修改止日 YYYY-MM-DD", self.date_to),
                  ("深度上限", self.depth), ("结果上限", self.result_limit)]
        for index, (title, widget) in enumerate(fields):
            row, column = divmod(index, 3)
            grid.addWidget(QLabel(title), row * 2, column)
            grid.addWidget(widget, row * 2 + 1, column)
        layout.addWidget(self.form)
        buttons = QHBoxLayout()
        self.start_button, self.cancel_button, self.clear_button = [QPushButton(t) for t in ("开始只读扫描", "取消", "清空结果")]
        self.start_button.clicked.connect(self.start_search)
        self.cancel_button.clicked.connect(self.cancel)
        self.clear_button.clicked.connect(self.clear)
        self.cancel_button.setEnabled(False)
        for button in (self.start_button, self.cancel_button, self.clear_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("等待开始")
        layout.addWidget(self.progress)
        self.status = QLabel("仅搜索名称和属性；不跟随链接，不建立索引；需点击开始")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.model = SearchResultsModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.locate)
        for column, width in enumerate((200, 180, 350, 90, 100, 160, 90)):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.errors.setMaximumBlockCount(150)
        self.errors.setMaximumHeight(100)
        self.errors.setPlaceholderText("不可读/跳过原因（最多保留 100 条明细，统计仍累计）")
        layout.addWidget(self.errors)

    def start_search(self) -> None:
        if self.worker:
            return
        try:
            try:
                minimum = int(self.min_size.text()) if self.min_size.text().strip() else None
                maximum = int(self.max_size.text()) if self.max_size.text().strip() else None
            except ValueError as exc:
                raise ValueError("大小筛选必须填写非负整数（字节）") from exc
            query = SearchQuery(self.pattern.text(), self.extensions.text(), self.path_filter.text(), self.entry_type.currentData(),
                minimum, maximum,
                self.date_from.text(), self.date_to.text(), (None, False, True)[self.case.currentIndex()])
            sources, skipped = self.source_builder(self.scope.currentIndex())
            if not sources:
                raise ValueError("没有已验证可读的搜索来源，请先选择并浏览分区")
            limits = SearchLimits(max_depth=self.depth.value(), max_results=self.result_limit.value())
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.clear()
        if skipped:
            self.errors.setPlainText("\n".join(skipped[:100]))
        self.generation += 1
        self.worker = SearchWorker(self.generation, sources, query, limits, self)
        self.worker.event_received.connect(self.handle_event)
        self.worker.finished.connect(self.worker_finished)
        self.form.setEnabled(False)
        self.start_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat("扫描中")
        self.status.setText("正在只读扫描…结果将按来源分区展示")
        self.worker.start()

    def handle_event(self, generation, event) -> None:
        if generation != self.generation:
            return
        kind = event["event"]
        if kind == "results":
            self.model.append(event["results"])
        elif kind == "error":
            self.errors.appendPlainText(f"{event['partition_name']}:/{event['path']} — {event['message']}")
        elif kind in ("progress", "finished"):
            self.stats = event["stats"]
            s = self.stats
            summary = (f"结果 {self.model.rowCount()} · 已检查 {s['entries']} 项 / {s['directories']} 目录 · "
                       f"来源 {s['sources_done']}/{s['sources_total']} · 错误目录 {s['error_directories']} / 条目 {s['error_entries']} · "
                       f"跳过链接 {s['skipped_links']} / 深度 {s['skipped_depth']} / 重复 {s['skipped_repeated']}")
            if kind == "finished":
                self.cancel_button.setEnabled(False)
                summary = ("完成（不跟随链接）" if s["complete"] else "部分完成，未扫描全部范围") + " · " + summary
                if s["stopped_reason"]:
                    summary += "\n" + s["stopped_reason"]
                self.progress.setRange(0, 1)
                self.progress.setValue(1 if s["complete"] else 0)
                self.progress.setFormat("完成限定范围" if s["complete"] else "已停止，部分结果")
            self.status.setText(summary)

    def cancel(self) -> None:
        if self.worker:
            self.worker.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在取消，只保留已返回结果…")

    def worker_finished(self) -> None:
        self.worker.deleteLater()
        self.worker = None
        self.form.setEnabled(True)
        self.start_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress.setRange(0, 1)
        self.idle.emit()
        if self.close_pending:
            self.close()

    def clear(self) -> None:
        if self.worker:
            return
        self.generation += 1
        self.model.clear()
        self.errors.clear()
        self.stats = {}
        self.status.setText("结果已清空，点击开始执行元数据搜索")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("等待开始")

    def invalidate(self) -> None:
        self.generation += 1
        self.cancel()
        self.model.clear()
        self.stats = {}
        self.status.setText("分区清单已刷新，旧结果失效，请重新搜索")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("设备清单已变化")

    def locate(self, index) -> None:
        result = index.data(Qt.ItemDataRole.UserRole)
        if result:
            self.locate_requested.emit(result)

    def closeEvent(self, event) -> None:
        if self.worker:
            self.close_pending = True
            self.cancel()
            event.ignore()
        else:
            event.accept()
