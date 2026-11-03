"""源码与冻结运行时共享的后台启动参数。"""
from pathlib import Path
import sys


def worker_command(kind: str) -> list[str]:
    modules = {'native': 'app.jobs.native_query', 'search': 'app.jobs.search_query'}
    if kind not in modules:
        raise ValueError('未知后台入口')
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--worker', kind]
    return [sys.executable, '-B', '-m', modules[kind]]


def runtime_directory() -> Path:
    return Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
