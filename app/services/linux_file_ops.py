"""FD-relative primitives for registered disposable-image bundle execution."""
from contextlib import contextmanager
import ctypes
import hashlib
import os
import stat
import uuid

from app.services.linux_safety import (ensure, owned_fd, open_beneath, open_regular,
    snapshot_fd, check_basic_object, identity, require_linux)


def rename_noreplace(parent, old, new):
    require_linux()
    libc = ctypes.CDLL(None, use_errno=True)
    ensure(hasattr(libc, "renameat2"), "renameat2 is required")
    fn = libc.renameat2
    fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    if fn(parent, old.encode(), parent, new.encode(), 1):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


@contextmanager
def parent_of(root, relative):
    prefix, _, name = relative.rpartition("/")
    fd = open_beneath(root, prefix, os.O_RDONLY | os.O_DIRECTORY) if prefix else os.dup(root)
    with owned_fd(fd):
        check_basic_object(fd, directory=True)
        yield fd, name


def file_snapshot(parent, name):
    try:
        with owned_fd(open_regular(parent, name)) as fd:
            return snapshot_fd(fd)
    except FileNotFoundError:
        return None


def dir_snapshot(parent, name):
    try:
        with owned_fd(open_beneath(parent, name, os.O_RDONLY | os.O_DIRECTORY)) as fd:
            value = check_basic_object(fd, directory=True)
            return dict(kind="directory", mode=value.st_mode, uid=value.st_uid, gid=value.st_gid,
                        inode=value.st_ino, dev=value.st_dev, mtime_ns=value.st_mtime_ns,
                        empty=not os.listdir(fd))
    except FileNotFoundError:
        return None


def copy_checked(source, destination, size, digest):
    value, count = hashlib.sha256(), 0
    while chunk := os.read(source, 1024 * 1024):
        count += len(chunk)
        ensure(count <= size, "Source grew while copying")
        destination.write(chunk)
        value.update(chunk)
    ensure(count == size and value.hexdigest() == digest, "Source size/hash mismatch")


def verify_blob(directory, name, expected):
    with owned_fd(open_regular(directory, name)) as fd:
        digest, size = hashlib.sha256(), 0
        while chunk := os.read(fd, 1024 * 1024):
            size += len(chunk)
            ensure(size <= expected["size"], "Private blob grew")
            digest.update(chunk)
        ensure(size == expected["size"] and digest.hexdigest() == expected["sha256"], "Private blob corrupted")


def backup_file(parent, name, directory, backup_name, expected):
    ensure(file_snapshot(parent, name) == expected, "Original changed before backup")
    with owned_fd(open_regular(parent, name)) as source:
        info = os.fstat(source)
        fd = os.open(backup_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as stream:
            copy_checked(source, stream, expected["size"], expected["sha256"])
            stream.flush(); os.fsync(stream.fileno())
        ensure(file_snapshot(parent, name) == expected, "Original changed during backup")
    os.fsync(directory)
    verify_blob(directory, backup_name, expected)
    return dict(file=backup_name, snapshot=expected, atime_ns=info.st_atime_ns)


def make_temporary(parent, source_dir, source_name, expected, metadata, temp_name, *, atime_ns=None):
    with owned_fd(open_regular(source_dir, source_name)) as source:
        fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as target:
            copy_checked(source, target, expected["size"], expected["sha256"])
            target.flush()
            os.fchown(target.fileno(), metadata["uid"], metadata["gid"])
            os.fchmod(target.fileno(), stat.S_IMODE(metadata["mode"]))
            if atime_ns is not None:
                os.utime(target.fileno(), ns=(atime_ns, metadata["mtime_ns"]))
            os.fsync(target.fileno())
    os.fsync(parent)
    after = file_snapshot(parent, temp_name)
    ensure(after["sha256"] == expected["sha256"] and after["size"] == expected["size"], "Temporary content mismatch")
    ensure(after["uid"] == metadata["uid"] and after["gid"] == metadata["gid"]
           and stat.S_IMODE(after["mode"]) == stat.S_IMODE(metadata["mode"]), "Temporary metadata mismatch")
    return after


def loop_image_identity(root_fd):
    """Physical partitions cannot obtain apply capability in this release."""
    require_linux()
    device = os.fstat(root_fd).st_dev
    filename = f"/sys/dev/block/{os.major(device)}:{os.minor(device)}/loop/backing_file"
    with open(filename, encoding="utf-8") as stream:
        backing = stream.read().strip()
    ensure(backing.startswith("/") and not backing.endswith(" (deleted)"), "Unknown loop backing file")
    # Only pin regular backing files; never write the loop block device directly.
    with owned_fd(os.open("/", os.O_RDONLY | os.O_DIRECTORY)) as os_root:
        with owned_fd(open_beneath(os_root, backing[1:], os.O_PATH, no_xdev=False)) as fd:
            info = os.fstat(fd)
            ensure(stat.S_ISREG(info.st_mode), "Loop backing is not a regular file")
            return dict(path=backing, identity=identity(fd), size=info.st_size)
