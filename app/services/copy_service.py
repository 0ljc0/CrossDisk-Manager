"""只读源到受限 Windows 目标；独占临时文件、校验、禁止覆盖发布。"""
from contextlib import ExitStack
import hashlib
import ntpath
import os
import shutil
import time
import uuid

from app.backends.windows_native import NativeWindowsBackend, validate_relative, readable_error
from app.core.virtual_path import VirtualPath
from app.services.backend_access import open_backend


class CopyCancelled(Exception):
    pass


def check_target(target):
    spec = target.get("backend_spec", {})
    if spec.get("kind") != "Windows":
        raise ValueError("目标必须是已识别的本地 Windows 普通数据卷")
    root = target.get("root", "")
    if not root.lower().startswith("\\\\?\\volume{"):
        raise ValueError("目标必须绑定本地 Volume GUID，禁止 UNC 和设备路径")
    path = target.get("relative_path", "")
    parts = validate_relative(path)
    if not parts:
        raise ValueError("请选择卷中的现有数据目录，不能选择卷根")
    forbidden = {"windows", "program files", "program files (x86)", "programdata",
                 "$recycle.bin", "system volume information", "recovery", "efi", "boot", "$extend"}
    if any(p.casefold() in forbidden for p in parts):
        raise ValueError("禁止写入系统关键目录")
    # 分类和实际只读能力复核；不借此授予通用 write 能力。
    return path


def copy_job(job, emit=lambda value: None, cancelled=lambda: False, paused=lambda: False):
    stats = dict(completed=0, failed=0, skipped=0, bytes=0, total_bytes=0, entries=0, state="运行中")
    started = time.monotonic()
    def checkpoint():
        while paused():
            if cancelled():
                raise CopyCancelled()
            time.sleep(.05)
        if cancelled():
            raise CopyCancelled()
        if time.monotonic() - started > 3600:
            raise ValueError("任务超过一小时预算，请缩小范围")
    def notify(message=""):
        emit(dict(stats, message=message))
    try:
        target_path = check_target(job.target)
        source_path = VirtualPath(job.source["partition_id"], job.source["relative_path"]).path
        if not source_path:
            raise ValueError("请选择具体文件或目录，不复制整个分区根")
        spec = job.source.get("backend_spec", {})
        if spec.get("kind") == "ext4" and not source_path.startswith("home/"):
            raise ValueError("ext4 导出仅开放 /home 下的用户数据")
        if spec.get("kind") == "Windows" and any(p.casefold() in
                {"windows", "program files", "program files (x86)", "programdata", "efi", "recovery", "boot", "system volume information"}
                for p in source_path.split("/")):
            raise ValueError("禁止复制系统关键目录")
        if spec.get("kind") == "ext4" and not spec.get("fingerprint"):
            raise ValueError("ext4 来源尚未完成只读验证")
        with open_backend(job.target) as target_backend, open_backend(job.source, "open_read") as source:
            # 持有目标全部祖先目录句柄，禁止重命名替换或重解析越界。
            with target_backend._guard(target_path) as destination:
                if spec.get("kind") == "Windows":
                    with source._guard(source_path) as native_source:
                        a, b = ntpath.normcase(native_source), ntpath.normcase(destination)
                        if b == a or b.startswith(a.rstrip("\\") + "\\"):
                            raise ValueError("目标不能位于来源自身或其子目录")
                stack = [(source_path, source_path.rsplit("/", 1)[-1], 0)]
                seen = set()
                while stack:
                    checkpoint()
                    path, relative, depth = stack.pop()
                    validate_relative(relative)
                    stats["entries"] += 1
                    if stats["entries"] > job.max_entries or depth > job.max_depth:
                        raise ValueError("达到目录深度或条目预算，未完成全部复制")
                    try:
                        entry = source.stat(path)
                        if entry.is_link is not False or entry.is_directory is None or entry.error:
                            stats["skipped"] += 1
                            notify("跳过链接或属性未知条目")
                            continue
                        output = ntpath.join(destination, *relative.split("/"))
                        if entry.is_directory:
                            # 不合并既有目录，避免碰到其内部链接和既有内容。
                            parent = relative.rsplit("/", 1)[0] if "/" in relative else ""
                            with target_backend._guard("/".join(filter(None, (target_path, parent)))) as guarded:
                                output = ntpath.join(guarded, relative.rsplit("/", 1)[-1])
                                exists = os.path.lexists(output)
                                identity = os.stat(output, follow_symlinks=False) if exists else None
                                owned = identity is not None and job.created_directories.get(output) == (identity.st_dev, identity.st_ino)
                                if exists and not owned:
                                    if job.conflict == "error":
                                        raise FileExistsError()
                                    stats["skipped"] += 1
                                    notify("跳过已存在的整个目录")
                                    continue
                                if not exists:
                                    os.mkdir(output)
                                    identity = os.stat(output, follow_symlinks=False)
                                    job.created_directories[output] = (identity.st_dev, identity.st_ino)
                                with target_backend._guard("/".join((target_path, relative))):
                                    pass
                            offset, fingerprint = 0, ""
                            while True:
                                checkpoint()
                                page = source.list_dir(path, offset=offset, page_size=200,
                                                       show_hidden=True, fingerprint=fingerprint)
                                fingerprint = page.fingerprint
                                token = (path, offset)
                                if token in seen:
                                    raise ValueError("重复分页，停止复制")
                                seen.add(token)
                                if len(stack) + stats["entries"] + len(page.entries) > job.max_entries:
                                    raise ValueError("达到待处理条目预算")
                                for child in page.entries:
                                    validate_relative(child.name)
                                    stack.append((VirtualPath(job.source["partition_id"], path).child(child.name).path,
                                                  relative + "/" + child.name, depth + 1))
                                if page.next_offset is None:
                                    break
                                if page.next_offset <= offset:
                                    raise ValueError("分页没有前进")
                                offset = page.next_offset
                            continue
                        if entry.size is None or entry.size < 0:
                            raise ValueError("未知文件大小，拒绝复制")
                        if os.path.lexists(output):
                            if job.conflict == "error":
                                raise FileExistsError()
                            stats["skipped"] += 1
                            notify("跳过已存在文件")
                            continue
                        stats["total_bytes"] += entry.size
                        parent = relative.rsplit("/", 1)[0] if "/" in relative else ""
                        with target_backend._guard("/".join(filter(None, (target_path, parent)))) as guarded:
                            if shutil.disk_usage(guarded).free < entry.size + 1024 * 1024:
                                raise OSError(28, "目标空间不足")
                            temporary = ntpath.join(guarded, ".crossdisk-" + uuid.uuid4().hex + ".partial")
                            created = False
                            try:
                                digest, copied = hashlib.sha256(), 0
                                with open(temporary, "xb") as writer:
                                    created = True
                                    with source.open_read(path) as reader:
                                        while True:
                                            checkpoint()
                                            block = reader.read(min(1024 * 1024, entry.size - copied + 1))
                                            if not block:
                                                break
                                            copied += len(block)
                                            if copied > entry.size:
                                                raise ValueError("源大小变化，停止发布")
                                            writer.write(block)
                                            digest.update(block)
                                            stats["bytes"] += len(block)
                                            notify()
                                    writer.flush()
                                    os.fsync(writer.fileno())
                                if copied != entry.size or source.stat(path) != entry:
                                    raise ValueError("源属性变化或短读，未发布目标")
                                verify = hashlib.sha256()
                                with open(temporary, "rb") as reader:
                                    while block := reader.read(1024 * 1024):
                                        checkpoint()
                                        verify.update(block)
                                if verify.digest() != digest.digest():
                                    raise ValueError("目标哈希校验失败")
                                checkpoint()
                                # Windows rename 在目标存在时失败；绝不使用 replace。
                                if os.name != "nt":
                                    raise ValueError("发布仅支持 Windows")
                                os.rename(temporary, output)
                                created = False
                                stats["completed"] += 1
                                notify("文件已核对字节数和 SHA-256")
                            finally:
                                if created:
                                    os.unlink(temporary)
                    except CopyCancelled:
                        raise
                    except (OSError, ValueError) as exc:
                        stats["failed"] += 1
                        message = ("目标空间不足" if getattr(exc, "errno", None) == 28 else
                                   "目标已存在，冲突策略为报错" if isinstance(exc, FileExistsError) else readable_error(exc))
                        notify(message)
                        # 任一失败停止本项任务，队列可继续，避免无限错误和磁盘耗尽。
                        raise ValueError(message) from None
        stats["state"] = "完成" if not stats["skipped"] else "完成（有跳过）"
        notify()
    except CopyCancelled:
        stats["state"] = "已取消"
        notify("已完成文件保留；仅清理本任务未完成临时文件")
    except Exception as exc:
        stats["failed"] = max(1, stats["failed"])
        stats["state"] = "失败"
        notify(readable_error(exc))
    return stats
