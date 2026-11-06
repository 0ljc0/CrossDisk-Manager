"""Experimental G0 snapshot reader. Does not authorize write or bundle export."""
from dataclasses import dataclass
import hashlib
import stat

@dataclass(frozen=True)
class FileSnapshot:
    kind: str
    size: int
    sha256: str
    mode: int
    uid: int
    gid: int
    mtime_ns: int
    nlink: int
    inode: int

def _metadata(backend, path):
    meta = backend._open(path).info.meta
    if meta.type != backend.tsk.TSK_FS_META_TYPE_REG:
        raise ValueError("Snapshot requires a regular file")
    names = ("size", "mode", "uid", "gid", "mtime", "mtime_nano", "nlink", "addr")
    values = tuple(getattr(meta, name, None) for name in names)
    if any(type(value) is not int for value in values):
        raise ValueError("Required snapshot metadata unavailable")
    size, mode, uid, gid, seconds, nanos, nlink, inode = values
    if not 0 <= nanos < 1000000000 or min(size, uid, gid) < 0 or nlink < 1 or inode < 1 or not 0 <= mode <= 0o7777:
        raise ValueError("Invalid snapshot metadata")
    return (size, stat.S_IFREG | mode, uid, gid, seconds * 1000000000 + nanos, nlink, inode)

def read_snapshot(backend, path):
    before = _metadata(backend, path)
    digest, count = hashlib.sha256(), 0
    with backend.open_read(path) as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            count += len(chunk)
    if before != _metadata(backend, path) or count != before[0]:
        raise ValueError("File changed during snapshot")
    size, mode, uid, gid, mtime_ns, nlink, inode = before
    return FileSnapshot("regular_file", size, digest.hexdigest(), mode, uid, gid, mtime_ns, nlink, inode)
