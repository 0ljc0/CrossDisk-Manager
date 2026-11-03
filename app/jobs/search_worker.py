"""逐行接收搜索元数据，进程隔离、队列背压、超时及取消。"""

from dataclasses import asdict
import json
import os
from pathlib import Path
from queue import Empty, Full, Queue
import subprocess
import sys
import threading
import time

from PySide6.QtCore import QThread, Signal

from app.core.search import SearchLimits, SearchQuery, SearchStats
from app.core.runtime import worker_command, runtime_directory


class SearchWorker(QThread):
    event_received = Signal(int, object)

    def __init__(self, generation: int, sources: list[dict], query: SearchQuery, limits: SearchLimits, parent=None) -> None:
        super().__init__(parent)
        self.generation = generation
        self.request = dict(sources=sources, query=asdict(query), limits=asdict(limits))
        self.limits = limits

    def run(self) -> None:
        process, reader = None, None
        done = threading.Event()
        events = Queue(maxsize=16)
        latest = asdict(SearchStats(sources_total=len(self.request["sources"])))
        shown = 0
        def put(value):
            while not done.is_set():
                try:
                    events.put(value, timeout=0.1)
                    return
                except Full:
                    continue
        def receive():
            try:
                while not done.is_set():
                    line = process.stdout.readline(16 * 1024 * 1024 + 1)
                    if not line:
                        break
                    if len(line) > 16 * 1024 * 1024:
                        raise ValueError("搜索响应过大")
                    put(json.loads(line))
            except Exception:
                put(dict(event="fatal", message="搜索响应无法解析"))
            finally:
                put(None)
        def emit(event):
            self.event_received.emit(self.generation, event)
        def partial(reason, cancelled=False):
            latest.update(complete=False, cancelled=cancelled, stopped_reason=reason, matches=shown)
            latest["entries"] = max(latest["entries"], shown)
            latest["directories"] = max(latest["directories"], 1 if shown else 0)
            emit(dict(event="finished", stats=latest.copy()))
        try:
            process = subprocess.Popen(worker_command('search'),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", cwd=runtime_directory(),
                env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1"),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            reader = threading.Thread(target=receive, daemon=True)
            reader.start()
            process.stdin.write(json.dumps(self.request, ensure_ascii=True))
            process.stdin.close()
            started = last_event = time.monotonic()
            final = False
            while True:
                if self.isInterruptionRequested():
                    partial("用户取消，保留已返回的部分结果", True)
                    break
                if time.monotonic() - last_event > 60 or time.monotonic() - started > self.limits.max_seconds + 5:
                    partial("搜索超时，保留部分结果；未完成全部扫描")
                    break
                try:
                    event = events.get(timeout=0.1)
                except Empty:
                    continue
                if event is None:
                    if not final:
                        partial("读取进程提前结束，结果不完整")
                    break
                last_event = time.monotonic()
                if event["event"] in ("progress", "finished"):
                    latest = event["stats"]
                if event["event"] == "results":
                    shown += len(event["results"])
                if event["event"] == "fatal":
                    partial(event["message"])
                    break
                if event["event"] == "finished":
                    final = True
                emit(event)
        except Exception:
            partial("无法运行搜索进程，结果不完整")
        finally:
            done.set()
            if process is not None:
                if process.poll() is None:
                    if os.name == "nt":
                        try:
                            executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/taskkill.exe"
                            subprocess.run([str(executable), "/PID", str(process.pid), "/T", "/F"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
                        except (OSError, subprocess.TimeoutExpired):
                            pass
                    if process.poll() is None:
                        process.kill()
                process.wait()
                if reader:
                    reader.join(timeout=1)
                process.stdout.close()
