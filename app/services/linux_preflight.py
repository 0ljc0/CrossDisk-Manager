"""Read-only target preflight with private, verified payload staging.

This module intentionally has no apply function. Reports are observations, not
permissions or a promise that a later write would be safe.
"""
from contextlib import ExitStack
import hashlib
import os
import stat
import uuid

from app.core.bundle import loads, manifest_hash
from app.services.linux_registry import (
    atomic_json, authorize_metadata, document_hash, read_private_json, registered_target, registry,
)
from app.services.linux_safety import (
    SafetyError, check_basic_object, ensure, identity, mount_for_fd, open_absolute_directory,
    open_beneath, open_regular, owned_fd, read_limited, require_linux, snapshot_fd,
)

MAX_STAGE_BYTES = 512 * 1024 * 1024
SPACE_MARGIN = 16 * 1024 * 1024
TRANSPORT_FILESYSTEMS = {"ext4", "ntfs", "ntfs3", "vfat", "exfat"}


def read_manifest(bundle_fd):
    with owned_fd(open_regular(bundle_fd, "manifest.json")) as fd:
        return loads(read_limited(fd, 4 * 1024 * 1024))


def validate_binding(manifest, entry):
    ensure(manifest["target"]["fs_uuid"] == entry["mount"]["uuid"], "Bundle UUID differs from registered target")
    ensure(manifest["target"]["mount_relative_root"] == entry["relative_root"],
           "Bundle root differs from registered test root")


def snapshot_differences(expected, actual):
    return [key for key in expected if expected[key] != actual.get(key)]


def require_absent(parent_fd, name):
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise SafetyError("Destination already exists (including a dangling link)")


def inspect_operation(root_fd, operation, allowed):
    relative = operation["path"]
    parent, _, name = relative.rpartition("/")
    parent_fd = (open_beneath(root_fd, parent, os.O_RDONLY | os.O_DIRECTORY)
                 if parent else os.dup(root_fd))
    with owned_fd(parent_fd):
        check_basic_object(parent_fd, directory=True)
        parent_identity = identity(parent_fd)
        kind = operation["type"]
        if kind in ("create_file", "mkdir"):
            authorize_metadata(operation["metadata"], allowed, directory=kind == "mkdir")
            require_absent(parent_fd, name)
        else:
            expected = (operation["source_precondition"] if kind == "rename_file"
                        else operation["precondition"]["object"])
            authorize_metadata(expected, allowed)
            with owned_fd(open_regular(parent_fd, name)) as fd:
                actual = snapshot_fd(fd)
                changed = snapshot_differences(expected, actual)
                ensure(not changed, "Original file differs: " + ", ".join(changed))
                # Recheck name binding as well as the open file; no CAS guarantee.
                named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                ensure((named.st_dev, named.st_ino) == (os.fstat(fd).st_dev, actual["inode"]),
                       "Source name changed during inspection")
            if kind == "rename_file":
                require_absent(parent_fd, operation["new_path"].rpartition("/")[2])
        ensure(identity(parent_fd) == parent_identity, "Parent directory identity changed")
        return dict(id=operation["id"], type=kind, path=relative, status="MATCH",
                    parent_identity=parent_identity)


def recheck_anchors(entry, root_fd, storage):
    """Reject name/mount rebinding during a long snapshot or payload read."""
    with owned_fd(open_absolute_directory(entry["mount_point"])) as mount_fd:
        current = mount_for_fd(mount_fd)
        ensure(all(current[k] == entry["mount"][k] for k in
                   ("mount_id", "device", "mount_point", "fsroot", "options", "super_options")),
               "Mount changed during preflight")
        with owned_fd(open_beneath(mount_fd, entry["relative_root"], os.O_RDONLY | os.O_DIRECTORY)) as current_root:
            ensure(identity(current_root) == identity(root_fd) == entry["root_identity"],
                   "Root name changed during preflight")
    for kind, fd in storage.items():
        record = entry["storage"][kind]
        with owned_fd(open_absolute_directory(record["path"])) as current:
            ensure(identity(current) == identity(fd) == record["identity"], "Storage changed during preflight")
            ensure(mount_for_fd(current)["mount_id"] == record["mount"]["mount_id"],
                   "Storage mount changed during preflight")


def stage_payload(bundle_fd, run_fd, operation):
    expected = operation["payload"]
    name = operation["id"] + ".payload"
    with owned_fd(open_regular(bundle_fd, expected["path"])) as source_fd:
        before = os.fstat(source_fd)
        ensure(before.st_size == expected["size"], "Payload size mismatch")
        destination = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                              0o600, dir_fd=run_fd)
        digest, size = hashlib.sha256(), 0
        with os.fdopen(destination, "wb") as stream:
            while chunk := os.read(source_fd, 1024 * 1024):
                size += len(chunk)
                ensure(size <= expected["size"], "Payload grew during staging")
                stream.write(chunk)
                digest.update(chunk)
            after = os.fstat(source_fd)
            ensure(size == expected["size"] and digest.hexdigest() == expected["sha256"],
                   "Payload size/hash mismatch")
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            ensure(all(getattr(before, k) == getattr(after, k) for k in fields), "Payload changed during staging")
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
        os.fsync(run_fd)
    return dict(operation_id=operation["id"], file=name, size=size, sha256=digest.hexdigest())


def check_previous(record, digest, state_fd):
    ensure(record["manifest_sha256"] == digest, "Bundle ID is already bound to another manifest")
    ensure(record["status"] in ("PREFLIGHT_OK", "PREFLIGHT_REJECTED"),
           "Unfinished preflight record requires administrative review")
    with owned_fd(open_beneath(state_fd, record["run_directory"], os.O_RDONLY | os.O_DIRECTORY)) as previous:
        info = os.fstat(previous)
        ensure(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700, "Untrusted prior report directory")
        report = read_private_json(previous, "report.json")
        ensure(document_hash(report) == record["report_sha256"], "Prior report is missing or corrupt")


def preflight(bundle, target):
    require_linux()
    with registry() as store, registered_target(store, target) as (entry, root_fd, storage), ExitStack() as stack:
        ensure(all(item["status"] in ("COMPLETED", "ROLLED_BACK")
                   for item in store.records.get("executions", {}).get(entry["target_key"], {}).values()),
               "Unfinished execution exists; use explicit recovery")
        bundle_fd = stack.enter_context(owned_fd(open_absolute_directory(os.path.abspath(bundle))))
        ensure(mount_for_fd(bundle_fd)["filesystem"] in TRANSPORT_FILESYSTEMS,
               "Unsupported bundle transport filesystem; copy it to local ext4 first")
        manifest = read_manifest(bundle_fd)
        validate_binding(manifest, entry)
        digest = manifest_hash(manifest)
        total = sum(op.get("payload", {}).get("size", 0) for op in manifest["operations"])
        ensure(total <= MAX_STAGE_BYTES, "Preflight staging budget exceeds 512 MiB")
        space = os.fstatvfs(storage["state"])
        ensure(space.f_bavail * space.f_frsize >= total + SPACE_MARGIN, "Insufficient private staging space")
        backups = sum((op.get("precondition", {}).get("object", {}).get("size", 0)
                       if op["type"] in ("replace_file", "delete_file") else 0)
                      for op in manifest["operations"])
        space = os.fstatvfs(storage["backup"])
        needed = backups + SPACE_MARGIN
        if os.fstat(storage["state"]).st_dev == os.fstat(storage["backup"]).st_dev:
            needed += total
        ensure(space.f_bavail * space.f_frsize >= needed, "Insufficient prospective backup space")
        target_runs = store.records["runs"].setdefault(entry["target_key"], {})
        for item in target_runs.values():
            check_previous(item, item["manifest_sha256"], storage["state"])
        previous = target_runs.get(manifest["bundle_id"])
        if previous:
            ensure(previous["manifest_sha256"] == digest, "Bundle ID is already bound to another manifest")
        run_name = "preflight-" + uuid.uuid4().hex
        record = dict(status="PREFLIGHT_STARTED", manifest_sha256=digest, run_directory=run_name)
        target_runs[manifest["bundle_id"]] = record
        store.save_records()  # Persist intention before creating the external run.
        os.mkdir(run_name, 0o700, dir_fd=storage["state"])
        os.fsync(storage["state"])
        run_fd = stack.enter_context(owned_fd(open_beneath(storage["state"], run_name, os.O_RDONLY | os.O_DIRECTORY)))
        report = dict(format="crossdisk-preflight", version=1, target=target, bundle_id=manifest["bundle_id"],
                      manifest_sha256=digest, mount=entry["mount"], root_identity=identity(root_fd),
                      apply_allowed=False, target_modified=False, operations=[], staged_payloads=[],
                      limitations=["Read-only preflight; no apply/backup/rollback implementation",
                                   "Reads may update atime; maintenance window is still required",
                                   "Observations are not atomic conditional-write guarantees"])
        try:
            atomic_json(run_fd, "manifest.json", manifest)
            for operation in manifest["operations"]:
                if "payload" in operation:
                    report["staged_payloads"].append(stage_payload(bundle_fd, run_fd, operation))
            for operation in manifest["operations"]:
                try:
                    result = inspect_operation(root_fd, operation, entry["policy"])
                except (OSError, ValueError) as exc:
                    result = dict(id=operation["id"], type=operation["type"], path=operation["path"],
                                  status="CONFLICT", error=str(exc))
                report["operations"].append(result)
            recheck_anchors(entry, root_fd, storage)
            report["status"] = ("PREFLIGHT_OK" if all(op["status"] == "MATCH" for op in report["operations"])
                                else "PREFLIGHT_REJECTED")
        except (OSError, ValueError) as exc:
            report["status"] = "PREFLIGHT_REJECTED"
            report["error"] = str(exc)
        atomic_json(run_fd, "report.json", report)
        record.update(status=report["status"], report_sha256=document_hash(report))
        store.save_records()
        return dict(report, report_path=entry["storage"]["state"]["path"]+"/"+run_name+"/report.json")
