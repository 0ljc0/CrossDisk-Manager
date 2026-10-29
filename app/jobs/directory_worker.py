"""有取消与超时的目录分页；网络路径阻塞不会卡住 GUI 或退出。"""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import QThread, Signal

from app.core.browser import DirectoryPage, FileEntry, Location


class DirectoryWorker(QThread):
    succeeded = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, request_id: int, location: Location, root: str, show_hidden: bool,
                 offset: int = 0, fingerprint: str = "", parent=None, timeout: float = 15) -> None:
        super().__init__(parent)
        self.request_id = request_id
        self.request = dict(partition_id=location.partition_id, root=root, relative_path=location.relative_path,
                            show_hidden=show_hidden, offset=offset, fingerprint=fingerprint)
        self.timeout = timeout

    def run(self) -> None:
        process = None
        try:
            process = subprocess.Popen([sys.executable, "-m", "app.jobs.native_query"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", cwd=Path(__file__).resolve().parents[2],
                env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            deadline = time.monotonic() + self.timeout
            payload = json.dumps(self.request, ensure_ascii=True)
            while True:
                if self.isInterruptionRequested():
                    return
                if time.monotonic() >= deadline:
                    self.failed.emit(self.request_id, "目录读取超时，设备或网络可能不可用，请重试。")
                    return
                try:
                    output, _ = process.communicate(payload, timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    payload = None
            if process.returncode:
                raise ValueError("查询进程失败")
            data = json.loads(output)
            if "error" in data:
                self.failed.emit(self.request_id, data["error"])
            else:
                page = data["page"]
                self.succeeded.emit(self.request_id, DirectoryPage(tuple(FileEntry(**e) for e in page["entries"]),
                                     page["next_offset"], page["fingerprint"]))
        except Exception:
            if not self.isInterruptionRequested():
                self.failed.emit(self.request_id, "无法启动或解析只读目录查询，请重试。")
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate()
