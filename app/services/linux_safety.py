"""Linux-only file-descriptor path boundary for the read-only preflight.

No target write API is exposed. Unknown platforms and missing syscalls fail closed.
"""
from contextlib import contextmanager
import ctypes
import errno
import hashlib
import json
import os
import platform
import re
import stat
import struct
import subprocess
from pathlib import PurePosixPath

from app.core.bundle import BundleError, path as relative_path


class SafetyError(BundleError):
    pass


def ensure(condition, message):
    if not condition:
        raise SafetyError(message)


def require_linux():
    ensure(platform.system() == "Linux", "Linux is required; no fallback is available")
    ensure("microsoft" not in platform.release().lower(), "Use native Ubuntu, not WSL")
    ensure(platform.machine() in ("x86_64", "aarch64") and ctypes.sizeof(ctypes.c_void_p) == 8,
           "Only tested-ABI 64-bit x86_64/aarch64 syscall layouts are supported")
    ensure(os.geteuid() == 0, "Run this preflight tool with sudo")


class OpenHow(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_uint64), ("mode", ctypes.c_uint64),
                ("resolve", ctypes.c_uint64)]


def open_beneath(parent_fd, relative, flags, *, no_xdev=True):
    """Return FD using openat2; never retry with an unsafe open()."""
    require_linux()
    relative_path(relative)
    resolve = 0x08 | 0x04 | 0x02 | (0x01 if no_xdev else 0)
    how = OpenHow(flags | os.O_CLOEXEC | os.O_NOFOLLOW, 0, resolve)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    result = libc.syscall(ctypes.c_long(437), ctypes.c_int(parent_fd),
                          ctypes.c_char_p(relative.encode("utf-8")), ctypes.byref(how),
                          ctypes.c_size_t(ctypes.sizeof(how)))
    if result < 0:
        code = ctypes.get_errno()
        raise OSError(code, "openat2 rejected path or is unavailable: " + os.strerror(code))
    return int(result)


@contextmanager
def owned_fd(fd):
    try:
        yield fd
    finally:
        os.close(fd)


def absolute_path(value):
    ensure(type(value) is str and value.startswith("/"), "Expected absolute Linux path")
    if value != "/":
        relative_path(value[1:])
    return value


def open_absolute_directory(value):
    require_linux()
    absolute_path(value)
    root = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    if value == "/":
        return root
    with owned_fd(root):
        # Crossing mounts only allowed while locating an explicitly selected anchor.
        return open_beneath(root, value[1:], os.O_RDONLY | os.O_DIRECTORY, no_xdev=False)


def identity(fd):
    info = os.fstat(fd)
    return {"dev": info.st_dev, "inode": info.st_ino}


def private_directory(value, *, create=False):
    """Verify every ancestor; optionally create only beneath a trusted ancestor."""
    absolute_path(value)
    require_linux()
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        components = value.strip("/").split("/") if value != "/" else []
        current = ""
        for component in components:
            current += "/" + component
            try:
                child = open_beneath(fd, component, os.O_RDONLY | os.O_DIRECTORY, no_xdev=False)
            except FileNotFoundError:
                ensure(create, "Private directory is missing")
                os.mkdir(component, 0o700, dir_fd=fd)
                os.fsync(fd)
                child = open_beneath(fd, component, os.O_RDONLY | os.O_DIRECTORY, no_xdev=False)
            try:
                info = os.fstat(child)
                # Ubuntu may expose /run/lock as root-owned sticky 1777. Its private
                # child must already be root-owned or be exclusively created here.
                sticky_lock = current == "/run/lock" and bool(info.st_mode & stat.S_ISVTX)
                ensure(info.st_uid == 0 and (not info.st_mode & 0o022 or sticky_lock),
                       "Private directory has an untrusted ancestor: " + current)
                ensure(not os.listxattr(child), "Private directory ACL/xattr is unsupported")
            except BaseException:
                os.close(child)
                raise
            os.close(fd)
            fd = child
        ensure(stat.S_IMODE(os.fstat(fd).st_mode) == 0o700,
               "Private directory must be root-owned mode 0700: " + value)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_limited(fd, limit):
    chunks, count = [], 0
    while True:
        chunk = os.read(fd, min(1024 * 1024, limit + 1 - count))
        if not chunk:
            break
        chunks.append(chunk)
        count += len(chunk)
        ensure(count <= limit, "Input exceeds byte limit")
    return b"".join(chunks)


def open_regular(parent_fd, relative):
    # Inspect with O_PATH before any device/FIFO could be opened for I/O. Reopen
    # our pinned regular inode via procfs, never the original untrusted pathname.
    require_linux()
    with owned_fd(open_beneath(parent_fd, relative, os.O_PATH)) as anchor:
        ensure(stat.S_ISREG(os.fstat(anchor).st_mode), "Expected a regular file")
        fd = os.open("/proc/self/fd/"+str(anchor), os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            ensure(identity(fd) == identity(anchor) and stat.S_ISREG(os.fstat(fd).st_mode),
                   "Pinned file identity changed")
            return fd
        except BaseException:
            os.close(fd)
            raise


def json_unique(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            ensure(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise SafetyError("Invalid JSON number")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_float=invalid, parse_constant=invalid)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise SafetyError("Invalid JSON document") from exc


def normalize_uuid(value):
    ensure(type(value) is str and re.fullmatch(
        r"(?:[a-fA-F0-9]{32}|[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})", value),
        "Invalid filesystem UUID")
    return value.replace("-", "").lower()


def unescape_mount(value):
    return re.sub(r"\\(040|011|012|134)", lambda m: chr(int(m[1], 8)), value)


def parse_mountinfo(text):
    records = []
    for line in text.splitlines():
        before, after = line.split(" - ", 1)
        fields, tail = before.split(), after.split()
        ensure(len(fields) >= 6 and len(tail) >= 3, "Invalid mountinfo")
        records.append(dict(mount_id=int(fields[0]), device=fields[2],
                            fsroot=unescape_mount(fields[3]), mount_point=unescape_mount(fields[4]),
                            options=fields[5].split(","), filesystem=tail[0],
                            source=unescape_mount(tail[1]), super_options=tail[2].split(",")))
    return records


def trusted_command(name, *arguments, allowed=(0,)):
    require_linux()
    executable = next((p for p in ("/usr/sbin/"+name, "/usr/bin/"+name,
                                   "/sbin/"+name, "/bin/"+name) if os.path.isfile(p)), None)
    ensure(executable is not None, "Missing system tool: " + name)
    info = os.stat(executable)
    ensure(info.st_uid == 0 and not info.st_mode & 0o022, "Untrusted system tool")
    result = subprocess.run([executable, *arguments], capture_output=True, text=True,
                            timeout=30, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    ensure(result.returncode in allowed, name + " failed: " + result.stderr.strip()[:500])
    return result.stdout


def mount_for_fd(fd):
    with open("/proc/self/fdinfo/"+str(fd), encoding="ascii") as stream:
        values = dict(line.rstrip().split(":", 1) for line in stream if ":" in line)
    mount_id = int(values["mnt_id"].strip())
    with open("/proc/self/mountinfo", encoding="utf-8") as stream:
        records = parse_mountinfo(stream.read())
    matches = [r for r in records if r["mount_id"] == mount_id]
    ensure(len(matches) == 1, "Mount identity is ambiguous")
    result = matches[0]
    device = os.fstat(fd).st_dev
    ensure(result["device"] == f"{os.major(device)}:{os.minor(device)}", "FD device differs from mount")
    return result


def ext4_mount(fd, *, exact_path=None):
    result = mount_for_fd(fd)
    ensure(result["filesystem"] == "ext4" and result["fsroot"] == "/",
           "Only full-root local ext4 mounts are supported")
    if exact_path is not None:
        ensure(result["mount_point"] == exact_path, "Path is not the exact mount point")
    ensure("rw" in result["options"], "Target/storage mount is read-only")
    ensure(not {"prjquota", "usrquota", "grpquota"}.intersection(result["super_options"]),
           "Quota mounts are outside the first-version policy")
    query = json.loads(trusted_command("findmnt", "--json", "--mountpoint", result["mount_point"],
                                     "--output", "TARGET,FSTYPE,UUID,SOURCE,FSROOT,MAJ:MIN"))
    entries = query.get("filesystems", [])
    ensure(len(entries) == 1, "findmnt returned ambiguous mount records")
    entry = entries[0]
    ensure(entry.get("target") == result["mount_point"] and entry.get("fstype") == "ext4"
           and entry.get("fsroot") == "/" and entry.get("maj:min") == result["device"],
           "findmnt and open directory identity disagree")
    result["uuid"] = normalize_uuid(entry.get("uuid"))
    # Check currently discoverable devices, not only the mount's textual UUID.
    from uuid import UUID
    devices = trusted_command("blkid", "-c", "/dev/null", "-t",
                              "UUID="+str(UUID(result["uuid"])), "-o", "device").splitlines()
    identities = set()
    for device in devices:
        info = os.stat(device)
        ensure(stat.S_ISBLK(info.st_mode), "UUID resolved to a non-block device")
        identities.add(info.st_rdev)
    ensure(identities == {os.fstat(fd).st_dev}, "Duplicate or unverified filesystem UUID")
    result["namespace"] = os.stat("/proc/self/ns/mnt").st_ino
    with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as stream:
        result["boot_id"] = stream.read().strip()
    return result


def allowed_test_root(mount_point, relative):
    absolute_path(mount_point)
    relative_path(relative)
    absolute = str(PurePosixPath(mount_point) / relative)
    parts = PurePosixPath(absolute).parts[1:]
    ensure(len(parts) >= 3 and parts[0] in ("home", "mnt", "media"),
           "Only dedicated test roots below /home, /mnt or /media are permitted")
    ensure(relative.split("/")[0] not in
           ("etc", "usr", "var", "boot", "bin", "sbin", "lib", "lib64", "dev", "proc", "sys", "root", "run", "tmp"),
           "System filesystem subtree is forbidden, even through a mount alias")
    return absolute


def overlaps(left, right):
    return (left == right or left.startswith(right.rstrip("/")+"/")
            or right.startswith(left.rstrip("/")+"/"))


def check_basic_object(fd, *, directory=False):
    import fcntl
    info = os.fstat(fd)
    ensure(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), "Wrong object type")
    ensure(not info.st_mode & 0o7000, "Special permission bits are unsupported")
    ensure(directory or info.st_nlink == 1, "Hard-linked files are unsupported")
    ensure(not os.listxattr(fd), "ACL/xattr is unsupported")
    # Linux 64-bit _IOR('f', 1, long). Only extent/index representation flags
    # are accepted; immutable, project inheritance, encryption etc. are rejected.
    flags = struct.unpack("=I", fcntl.ioctl(fd, 0x80086601, bytes(8))[:4])[0]
    ensure(flags & ~(0x80000 | (0x1000 if directory else 0)) == 0,
           "Unsupported ext4 inode flags")
    # fsxattr also exposes a project ID without an inheritance flag.
    fsx = fcntl.ioctl(fd, 0x801c581f, bytes(28))
    ensure(struct.unpack_from("=I", fsx, 12)[0] == 0, "Project ID is unsupported")
    return info


def snapshot_fd(fd):
    before = check_basic_object(fd)
    digest, size = hashlib.sha256(), 0
    while chunk := os.read(fd, 1024 * 1024):
        size += len(chunk)
        ensure(size <= before.st_size, "File grew during snapshot")
        digest.update(chunk)
    after = check_basic_object(fd)
    fields = ("st_dev", "st_ino", "st_size", "st_mode", "st_uid", "st_gid",
              "st_mtime_ns", "st_ctime_ns", "st_nlink")
    ensure(size == before.st_size and all(getattr(before, f) == getattr(after, f) for f in fields),
           "File changed during snapshot")
    return dict(kind="regular_file", size=size, sha256=digest.hexdigest(), mode=before.st_mode,
                uid=before.st_uid, gid=before.st_gid, mtime_ns=before.st_mtime_ns,
                nlink=before.st_nlink, inode=before.st_ino)
