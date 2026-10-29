"""Windows 数据目录受控写入；源后端默认仍无写入授权。"""
from contextlib import ExitStack
import ctypes
from dataclasses import dataclass
import hashlib
import ntpath
import os
import uuid

from app.core.capability_policy import CapabilityPolicy
from app.backends.windows_native import validate_relative, VOLUME_ROOT
from app.services.disk_inventory import DiskInventoryService

MAX_TEXT = 2 * 1024 * 1024
BLOCKED = {'windows', 'program files', 'program files (x86)', 'programdata', 'boot', 'efi', 'recovery',
           'system volume information', '$recycle.bin', '$extend'}


@dataclass(frozen=True)
class WriteContext:
    partition: object
    disk: object
    scope: str
    scanner: object = None

    def validate(self, backend, path):
        CapabilityPolicy().require_windows_write(self.partition, self.disk)
        if backend.partition_id != self.partition.id or backend.root.casefold() != self.partition.volume_path.casefold():
            raise ValueError("写入根与稳定分区身份不一致")
        if not VOLUME_ROOT.fullmatch(backend.root):
            raise ValueError("写入仅支持本地 Volume GUID 根")
        parts = validate_relative(path)
        scope = validate_relative(self.scope)
        if not scope or len(parts) <= len(scope) or tuple(p.casefold() for p in parts[:len(scope)]) != tuple(p.casefold() for p in scope):
            raise ValueError("只能操作已配置数据目录内的子项，不能操作目录本身")
        if any(p.casefold() in BLOCKED for p in parts):
            raise ValueError("系统关键目录禁止写入")
        # 每个后台操作重新扫描，不信任磁盘编号或 UI 旧清单。
        inventory = (self.scanner or DiskInventoryService().scan)()
        current = next((p for p in inventory.partitions if p.id == self.partition.id), None)
        disk = next((d for d in inventory.disks if d.id == self.disk.id), None)
        if current != self.partition or disk != self.disk:
            raise ValueError("磁盘或分区状态变化，请重新配置写入目录")
        CapabilityPolicy().require_windows_write(current, disk)


def read_text(backend, path):
    with backend.open_read(path) as reader:
        raw = reader.read(MAX_TEXT + 1)
    if len(raw) > MAX_TEXT or b'\x00' in raw:
        raise ValueError("编辑仅支持不超过 2 MiB 的 UTF-8 普通文本")
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError("编辑仅支持 UTF-8 文本，请使用只读预览查看其他编码") from None
    return dict(text=text, version=hashlib.sha256(raw).hexdigest())


def _replace_with_backup(original, temporary, backup):
    from ctypes import wintypes
    function = ctypes.WinDLL('kernel32', use_last_error=True).ReplaceFileW
    function.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    function.restype = wintypes.BOOL
    if not function(original, temporary, backup, 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def recycle(path):
    from ctypes import wintypes
    class Operation(ctypes.Structure):
        _fields_ = [('hwnd', wintypes.HWND), ('function', wintypes.UINT), ('source', wintypes.LPCWSTR),
                    ('target', wintypes.LPCWSTR), ('flags', ctypes.c_ushort), ('aborted', wintypes.BOOL),
                    ('mappings', ctypes.c_void_p), ('title', wintypes.LPCWSTR)]
    # Shell 回收站不接受扩展前缀；长路径明确拒绝，不回退永久删除。
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetVolumePathNamesForVolumeNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    root, tail = ntpath.splitdrive(path)
    names, needed = ctypes.create_unicode_buffer(32768), wintypes.DWORD()
    if not kernel.GetVolumePathNamesForVolumeNameW(root + '\\', names, len(names), ctypes.byref(needed)) or not names.value:
        raise ValueError("该卷没有回收站可用的挂载路径")
    shell_path = ntpath.join(names.value, tail.lstrip('\\'))
    if len(shell_path) >= 250:
        raise ValueError("回收站暂不支持此长路径；没有执行永久删除")
    # 保留 Shell 自己的确认；无法回收时必须显示永久删除警告，不能静默退化。
    operation = Operation(None, 3, shell_path + '\x00', None, 0x40 | 0x4000, False, None, None)
    function = ctypes.WinDLL('shell32').SHFileOperationW
    function.argtypes = [ctypes.POINTER(Operation)]
    function.restype = ctypes.c_int
    if function(ctypes.byref(operation)) or operation.aborted:
        raise ValueError("回收站操作失败或取消；不会回退永久删除")


def execute(backend, operation, path, **kwargs):
    backend.write_context.validate(backend, path)
    if operation == 'read_text':
        return read_text(backend, path)
    parent, name = path.rsplit('/', 1) if '/' in path else ('', path)
    with ExitStack() as stack:
        directory = stack.enter_context(backend._guard(parent))
        full = ntpath.join(directory, name)
        if operation == 'create_dir':
            os.mkdir(full)
        elif operation == 'create_file':
            with open(full, 'xb'):
                pass
        else:
            entry = backend.stat(path)
            if entry.is_link is not False or entry.error:
                raise ValueError("链接或未知属性条目禁止修改")
            if operation in ('rename', 'move'):
                target = kwargs['target']
                backend.write_context.validate(backend, target)
                if operation == 'rename' and ntpath.dirname(target) != ntpath.dirname(path):
                    raise ValueError("重命名必须在同一目录")
                if entry.is_directory and target.casefold().startswith(path.casefold() + '/'):
                    raise ValueError("不能移动目录到自身内部")
                target_parent, target_name = target.rsplit('/', 1)
                folder = stack.enter_context(backend._guard(target_parent))
                os.rename(full, ntpath.join(folder, target_name))
            elif operation == 'delete':
                if entry.is_directory and os.listdir(full):
                    raise ValueError("仅允许删除文件或空目录，不递归删除")
                if kwargs.get('permanent'):
                    if not kwargs.get('confirmed'):
                        raise ValueError("永久删除必须二次确认不可恢复风险")
                    os.rmdir(full) if entry.is_directory else os.unlink(full)
                else:
                    recycle(full)
            elif operation == 'write_file':
                data = kwargs['data']
                if entry.is_directory or not isinstance(data, bytes) or len(data) > MAX_TEXT:
                    raise ValueError("仅允许保存不超过 2 MiB 的 UTF-8 文本")
                data.decode('utf-8')
                temporary = ntpath.join(directory, '.crossdisk-' + uuid.uuid4().hex + '.partial')
                backup = full + '.crossdisk-' + uuid.uuid4().hex + '.bak'
                created = False
                try:
                    with open(temporary, 'xb') as writer:
                        created = True
                        writer.write(data)
                        writer.flush()
                        os.fsync(writer.fileno())
                    # 最后时刻再次检查原内容，避免覆盖读取以来的外部改动。
                    # 阻止普通外部写句柄在最终检查和替换期间改写内容；
                    # 允许 DELETE 共享以供 ReplaceFile 原子替换，备份由系统创建。
                    with backend._handle(full, read=True, share=0x1 | 0x4):
                        if read_text(backend, path)['version'] != kwargs['version']:
                            raise ValueError("保存冲突：原文件已变化，请重新打开；编辑内容保留")
                        _replace_with_backup(full, temporary, backup)
                    created = False
                    return dict(message='保存成功；原文件备份：' + ntpath.basename(backup), version=hashlib.sha256(data).hexdigest())
                finally:
                    if created and os.path.exists(temporary):
                        os.unlink(temporary)
            else:
                raise ValueError("未知写入操作")
    return dict(message='操作完成；不提供自动撤销')
