"""Windows 原生只读后端：不跟随链接，不提供任何写入接口。"""

import ctypes
import ntpath
import os
import re
import stat as stat_module
from contextlib import contextmanager, ExitStack
from datetime import datetime
from typing import BinaryIO

from app.core.browser import DirectoryPage, FileEntry, ReadOnlyCapabilities


VOLUME_ROOT = re.compile(r"^\\\\\?\\Volume\{[0-9a-fA-F-]{36}\}\\$", re.IGNORECASE)
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", re.IGNORECASE)


def normalize_root(root: str) -> str:
    """仅允许绝对盘符路径、普通 UNC 共享或卷 GUID 根。"""
    if VOLUME_ROOT.fullmatch(root):
        return root
    if root.startswith("\\\\?\\UNC\\"):
        root = "\\\\" + root[8:]
    if root.startswith(("\\\\?\\", "\\\\.\\")) or "\x00" in root:
        raise ValueError("禁止设备路径或原始卷路径")
    drive, tail = ntpath.splitdrive(root)
    if drive.startswith("\\\\") and not tail:
        tail = "\\"
        root += "\\"
    if not drive or not tail.startswith("\\"):
        raise ValueError("需要绝对盘符路径或 UNC 共享路径")
    if drive.startswith("\\\\"):
        parts = drive[2:].split("\\")
        if len(parts) != 2 or any(not p or any(c in p for c in '<>:"/|?*') for p in parts):
            raise ValueError("UNC 共享格式无效")
        if parts[1].upper() in ("IPC$", "ADMIN$") or re.fullmatch(r"[A-Za-z]\$", parts[1]):
            raise ValueError("不允许管理共享，请使用普通授权共享")
    elif not re.fullmatch("[A-Za-z]:", drive):
        raise ValueError("盘符格式无效")
    components = tail.strip("\\").split("\\") if tail.strip("\\") else []
    validate_relative("/".join(components))
    result = ntpath.normpath(root)
    return ("\\\\?\\UNC\\" + result[2:] if result.startswith("\\\\") else "\\\\?\\" + result).rstrip("\\") + "\\"


def validate_relative(path: str) -> tuple[str, ...]:
    if not path:
        return ()
    parts = path.split("/")
    if any(not p or p in (".", "..") or p.endswith((".", " ")) or _RESERVED.match(p)
           or any(ord(c) < 32 or c in '<>:"\\|?*' for c in p) for p in parts):
        raise ValueError("路径无效：禁止越界、设备名和备用数据流")
    return tuple(parts)


def readable_error(exc: BaseException) -> str:
    if getattr(exc, "winerror", None) in (32, 33):
        return "文件被占用或锁定，请稍后重试。"
    if isinstance(exc, PermissionError):
        return "访问被拒绝，请检查 Windows 权限；程序不会绕过权限。"
    if isinstance(exc, FileNotFoundError):
        return "路径不存在或设备已断开，请刷新后重试。"
    if isinstance(exc, NotADirectoryError):
        return "目标不是目录。"
    if isinstance(exc, IsADirectoryError):
        return "目标是目录，不能作为文件读取。"
    if isinstance(exc, ValueError):
        return str(exc)
    return "无法读取目标，设备不可用或文件状态已发生变化。"


class NativeWindowsBackend:
    def __init__(self, partition_id: str, root: str) -> None:
        self.partition_id = partition_id
        self.root = normalize_root(root)

    def get_capabilities(self) -> ReadOnlyCapabilities:
        return ReadOnlyCapabilities()

    @contextmanager
    def _handle(self, path: str, read: bool = False):
        """OPEN_EXISTING；不授予写权限，不共享删除，固定组件防止重命名换位。"""
        if os.name != "nt":
            raise OSError("此后端仅支持 Windows")
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL
        handle = create(path, 0x80000000 if read else 0x80, 0x1 | 0x2, None, 3,
                        0x02000000 | 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            class AttributeTag(ctypes.Structure):
                _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]
            info = AttributeTag()
            query = kernel.GetFileInformationByHandleEx
            query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            query.restype = wintypes.BOOL
            if not query(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.attributes & 0x400:
                raise ValueError("链接或重解析点仅展示属性，禁止进入或读取，以防止越界和循环")
            yield handle
        finally:
            close(handle)

    @contextmanager
    def _guard(self, relative_path: str):
        parts = validate_relative(relative_path)
        # 固定根路径的每级目录，包括自定义 UNC/测试子目录的父级。
        drive, tail = ntpath.splitdrive(self.root)
        current = drive + "\\"
        components = [p for p in tail.split("\\") if p] + list(parts)
        with ExitStack() as stack:
            stack.enter_context(self._handle(current))
            for part in components:
                current = ntpath.join(current, part)
                stack.enter_context(self._handle(current))
            yield current

    @staticmethod
    def _entry(name: str, info: os.stat_result) -> FileEntry:
        attributes = getattr(info, "st_file_attributes", 0)
        link = bool(attributes & 0x400) or stat_module.S_ISLNK(info.st_mode)
        return FileEntry(name, stat_module.S_ISDIR(info.st_mode), info.st_size,
                         datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                         bool(attributes & 0x2), link, bool(info.st_mode & stat_module.S_IREAD),
                         bool(info.st_mode & stat_module.S_IWRITE), "", "Windows", "属性已读取")

    def list_dir(self, relative_path: str = "", *, offset: int = 0, page_size: int = 200,
                 show_hidden: bool = False, fingerprint: str = "") -> DirectoryPage:
        if type(offset) is not int or offset < 0 or not 1 <= page_size <= 1000:
            raise ValueError("分页参数无效")
        with self._guard(relative_path) as path:
            info = os.stat(path, follow_symlinks=False)
            if not stat_module.S_ISDIR(info.st_mode):
                raise NotADirectoryError()
            current = f"{info.st_dev}:{info.st_ino}:{info.st_mtime_ns}"
            if fingerprint and fingerprint != current:
                raise ValueError("目录在分页期间发生变化，请刷新后重新加载")
            entries = []
            examined = 0
            with os.scandir(path) as iterator:
                for index, entry in enumerate(iterator):
                    if index < offset:
                        continue
                    examined += 1
                    try:
                        record = self._entry(entry.name, entry.stat(follow_symlinks=False))
                    except FileNotFoundError:
                        continue
                    except OSError:
                        record = FileEntry(entry.name, None, size=None, modified="", error="属性不可读取",
                                           backend_source="Windows", access_status="属性不可读取")
                    if show_hidden or not record.hidden:
                        entries.append(record)
                    if len(entries) >= page_size or examined >= 2000:
                        return DirectoryPage(tuple(entries), offset + examined, current)
            return DirectoryPage(tuple(entries), None, current)

    def stat(self, relative_path: str = "") -> FileEntry:
        parts = validate_relative(relative_path)
        # 只固定父目录，最后一个链接只读取 lstat 元数据。
        parent = "/".join(parts[:-1]) if parts else ""
        with self._guard(parent) as directory:
            path = ntpath.join(directory, parts[-1]) if parts else directory
            return self._entry(parts[-1] if parts else self.root, os.stat(path, follow_symlinks=False))

    @contextmanager
    def open_read(self, relative_path: str) -> BinaryIO:
        """只用 rb 暴露文件；固定组件期间读，不跟随链接、不修改文件。"""
        import msvcrt
        with self._guard(relative_path) as path:
            if not stat_module.S_ISREG(os.stat(path, follow_symlinks=False).st_mode):
                raise IsADirectoryError()
            with self._handle(path, read=True) as handle:
                # 复制句柄归属，避免 fd 关闭时与 _handle 重复释放。
                fd = msvcrt.open_osfhandle(self._duplicate_handle(handle), os.O_RDONLY | os.O_BINARY)
                with os.fdopen(fd, "rb") as stream:
                    yield stream

    @staticmethod
    def _duplicate_handle(handle) -> int:
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process = kernel.GetCurrentProcess()
        duplicate = wintypes.HANDLE()
        function = kernel.DuplicateHandle
        function.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                             ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        function.restype = wintypes.BOOL
        if not function(process, handle, process, ctypes.byref(duplicate), 0, False, 2):
            raise ctypes.WinError(ctypes.get_last_error())
        return duplicate.value
