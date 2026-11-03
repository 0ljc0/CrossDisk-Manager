"""冻结入口先分派后台模式，避免为子进程重复创建 GUI。"""
import os
import sys


def restore_worker_stdio():
    # windowed bootloader 将 Python 标准流设为 None；只在显式后台模式
    # 恢复父进程提供的匿名管道，不为普通 GUI 分配控制台。
    if os.name != 'nt':
        return
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    for name, number, mode, flags in (('stdin', -10, 'r', os.O_RDONLY),
                                     ('stdout', -11, 'w', os.O_WRONLY), ('stderr', -12, 'w', os.O_WRONLY)):
        if getattr(sys, name) is None:
            handle = kernel.GetStdHandle(number & 0xffffffff)
            if handle and handle != ctypes.c_void_p(-1).value:
                fd = msvcrt.open_osfhandle(handle, flags | os.O_BINARY)
                setattr(sys, name, os.fdopen(fd, mode, encoding='utf-8', buffering=1))


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == '--worker':
        if len(sys.argv) != 3 or sys.argv[2] not in ('native', 'search'):
            return 2
        restore_worker_stdio()
        if sys.stdin is None or sys.stdout is None:
            return 2
        if sys.argv[2] == 'native':
            from app.jobs.native_query import main as worker
        else:
            from app.jobs.search_query import main as worker
        return worker()
    from app.main import main as gui
    return gui()
