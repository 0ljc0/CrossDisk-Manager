"""Fixed, root-owned registration and locks for preflight-only Linux targets."""
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
import stat
import uuid
from pathlib import PurePosixPath

from app.core.bundle import identifier, integer
from app.services.linux_safety import (
    SafetyError, allowed_test_root, check_basic_object, ensure, ext4_mount, identity,
    json_unique, normalize_uuid, open_absolute_directory, open_beneath, open_regular,
    overlaps, owned_fd, private_directory, read_limited, require_linux,
)

CONFIG_DIR = "/etc/crossdisk-manager"
REGISTRY_DIR = "/var/lib/crossdisk-manager/registry"
LOCK_DIR = "/run/lock/crossdisk-manager"
REGISTRATION_VERSION = 1


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def document_hash(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def atomic_json(directory_fd, name, value):
    identifier(name.replace(".", "_"))
    temporary = "." + uuid.uuid4().hex + ".tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=directory_fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    except BaseException:
        # Retain evidence on failure; never remove files by a prefix pattern.
        raise


def read_private_json(directory_fd, name):
    with owned_fd(open_regular(directory_fd, name)) as fd:
        info = os.fstat(fd)
        ensure(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1,
               "Untrusted private record")
        return json_unique(read_limited(fd, 8 * 1024 * 1024))


@contextmanager
def lock(name):
    import fcntl
    identifier(name)
    with owned_fd(private_directory(LOCK_DIR, create=True)) as directory:
        fd = os.open(name + ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=directory)
        with owned_fd(fd):
            info = os.fstat(fd)
            ensure(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                   and stat.S_IMODE(info.st_mode) == 0o600, "Untrusted lock file")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SafetyError("Another CrossDisk process holds the lock") from exc
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)


class Registry:
    def __init__(self, config_fd, registry_fd):
        self.config_fd, self.registry_fd = config_fd, registry_fd
        self.config = read_private_json(config_fd, "targets.json")
        self.records = read_private_json(registry_fd, "registry.json")
        ensure(type(self.config) is dict and type(self.records) is dict, "Invalid registry documents")
        ensure(self.config.get("version") == REGISTRATION_VERSION
               and self.records.get("version") == REGISTRATION_VERSION, "Unknown registry version")
        ensure(type(self.config.get("targets")) is dict and type(self.records.get("runs")) is dict,
               "Invalid registry structure")
        ensure(self.records.get("config_sha256") == document_hash(self.config),
               "Registration records disagree; explicit administrative recovery required")

    def save_records(self):
        atomic_json(self.registry_fd, "registry.json", self.records)

    def save_registration(self):
        # Not a cross-file transaction. A crash between writes fails closed on reopen.
        atomic_json(self.config_fd, "targets.json", self.config)
        self.records["config_sha256"] = document_hash(self.config)
        self.save_records()


@contextmanager
def registry(*, initialize=False):
    require_linux()
    # Global lock deliberately serializes the first-version registry and all preflights.
    # Filesystem/target locks below are retained for future narrower concurrency.
    with lock("registry"), owned_fd(private_directory(CONFIG_DIR, create=initialize)) as config_fd, \
            owned_fd(private_directory(REGISTRY_DIR, create=initialize)) as registry_fd:
        present = []
        for directory, name in ((config_fd, "targets.json"), (registry_fd, "registry.json")):
            try:
                os.stat(name, dir_fd=directory, follow_symlinks=False)
                present.append(True)
            except FileNotFoundError:
                present.append(False)
        if not any(present):
            ensure(initialize, "Target registry has not been initialized")
            config = dict(version=REGISTRATION_VERSION, targets={})
            atomic_json(config_fd, "targets.json", config)
            atomic_json(registry_fd, "registry.json",
                        dict(version=REGISTRATION_VERSION, config_sha256=document_hash(config), runs={}))
        else:
            ensure(all(present), "Partial/missing registry; initialization cannot reset it")
        yield Registry(config_fd, registry_fd)


def policy(uids, gids, file_modes, directory_modes):
    for values in (uids, gids, file_modes, directory_modes):
        ensure(type(values) is list and values and len(values) == len(set(values)), "Empty/duplicate policy")
    for value in uids + gids:
        integer(value, 1, 2**32-2)
    for value in file_modes + directory_modes:
        integer(value, 0, 0o777)
    return dict(uids=sorted(uids), gids=sorted(gids), file_modes=sorted(file_modes),
                directory_modes=sorted(directory_modes))


def authorize_metadata(info, allowed, *, directory=False):
    ensure(info["uid"] in allowed["uids"] and info["gid"] in allowed["gids"], "Owner is not authorized")
    mode = stat.S_IMODE(info["mode"])
    ensure(mode in allowed["directory_modes" if directory else "file_modes"], "Mode is not authorized")


def target_key(fs_uuid, relative):
    return hashlib.sha256((fs_uuid+"\0"+relative).encode("utf-8")).hexdigest()


def no_registration_overlap(existing, proposed):
    for item in existing.values():
        if item["mount"]["uuid"] == proposed["mount"]["uuid"]:
            ensure(not overlaps(item["relative_root"], proposed["relative_root"]),
                   "Target root overlaps an existing registration (including mount aliases)")
        for left in item["storage"].values():
            for right in proposed["storage"].values():
                ensure(not overlaps(left["path"], right["path"]), "Private storage already registered")
                if left["mount"]["uuid"] == right["mount"]["uuid"]:
                    ensure(not overlaps(left["fs_relative"], right["fs_relative"]),
                           "Private storage aliases an existing registration")


def register(name, mount_point, relative, state_root, backup_root, allowed, confirm_root, confirm_uuid,
             *, initialize=False, enable_bundle_apply=False):
    require_linux()
    identifier(name)
    absolute = allowed_test_root(mount_point, relative)
    ensure(confirm_root == absolute, "Confirm the exact dedicated test root")
    expected_uuid = normalize_uuid(confirm_uuid)
    ensure(not overlaps(state_root, backup_root), "State and backup directories must be separate")
    with registry(initialize=initialize) as store, ExitStack() as stack:
        ensure(name not in store.config["targets"], "Registration exists; no implicit replacement")
        mount_fd = stack.enter_context(owned_fd(open_absolute_directory(mount_point)))
        mount = ext4_mount(mount_fd, exact_path=mount_point)
        ensure(mount["uuid"] == expected_uuid, "Confirmation UUID differs from mounted filesystem")
        stack.enter_context(lock("fs-"+mount["uuid"]))
        root_fd = stack.enter_context(owned_fd(open_beneath(mount_fd, relative, os.O_RDONLY | os.O_DIRECTORY)))
        check_basic_object(root_fd, directory=True)
        storage = {}
        for kind, location in (("state", state_root), ("backup", backup_root)):
            fd = stack.enter_context(owned_fd(private_directory(location)))
            item_mount = ext4_mount(fd)
            ensure(os.fstat(fd).st_dev != os.fstat(root_fd).st_dev and item_mount["uuid"] != mount["uuid"],
                   "Private storage must be outside the target filesystem")
            ensure(not os.listdir(fd), "Initial private storage must be empty")
            fs_relative = str(PurePosixPath("/") / PurePosixPath(location).relative_to(item_mount["mount_point"]))
            storage[kind] = dict(path=location, identity=identity(fd), mount=item_mount, fs_relative=fs_relative)
        if storage["state"]["mount"]["uuid"] == storage["backup"]["mount"]["uuid"]:
            ensure(not overlaps(storage["state"]["fs_relative"], storage["backup"]["fs_relative"]),
                   "State and backup are overlapping filesystem aliases")
        entry = dict(name=name, relative_root=relative, mount_point=mount_point, mount=mount,
                     root_identity=identity(root_fd), policy=allowed, storage=storage,
                     target_key=target_key(mount["uuid"], relative), purpose="preflight-only")
        if enable_bundle_apply:
            from app.services.linux_file_ops import loop_image_identity
            entry["loop_image"] = loop_image_identity(root_fd)
            entry["purpose"] = "bundle-test"
        no_registration_overlap(store.config["targets"], entry)
        store.config["targets"][name] = entry
        store.save_registration()
        return entry


def verify_mount(current, expected):
    fields = ("uuid", "device", "mount_point", "fsroot", "mount_id", "namespace", "boot_id", "options", "super_options")
    ensure(all(current.get(k) == expected.get(k) for k in fields),
           "Mount mapping changed; this preflight registration requires administrative review")


@contextmanager
def registered_target(store, name):
    identifier(name)
    ensure(name in store.config["targets"], "Unknown target registration")
    entry = store.config["targets"][name]
    ensure(entry.get("purpose") in ("preflight-only", "bundle-test"), "Unsupported target purpose")
    allowed_test_root(entry["mount_point"], entry["relative_root"])
    ensure(entry["target_key"] == target_key(entry["mount"]["uuid"], entry["relative_root"]), "Corrupt target key")
    with ExitStack() as stack:
        stack.enter_context(lock("fs-"+entry["mount"]["uuid"]))
        stack.enter_context(lock("t-"+entry["target_key"][:60]))
        mount_fd = stack.enter_context(owned_fd(open_absolute_directory(entry["mount_point"])))
        verify_mount(ext4_mount(mount_fd, exact_path=entry["mount_point"]), entry["mount"])
        root = stack.enter_context(owned_fd(open_beneath(mount_fd, entry["relative_root"], os.O_RDONLY | os.O_DIRECTORY)))
        ensure(identity(root) == entry["root_identity"], "Registered root was replaced")
        check_basic_object(root, directory=True)
        storage = {}
        for kind, record in entry["storage"].items():
            fd = stack.enter_context(owned_fd(private_directory(record["path"])))
            ensure(identity(fd) == record["identity"], "Private storage directory was replaced")
            verify_mount(ext4_mount(fd), record["mount"])
            ensure(os.fstat(fd).st_dev != os.fstat(root).st_dev, "Private storage aliases target filesystem")
            storage[kind] = fd
        yield entry, root, storage
