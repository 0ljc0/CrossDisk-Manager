"""Registered loop-image bundle execution and conservative explicit recovery."""
from contextlib import ExitStack
from copy import deepcopy
import os
import stat
import uuid

from app.core.bundle import identifier, loads, manifest_hash, canonical
from app.services.linux_registry import (registry, registered_target, atomic_json, document_hash,
    read_private_json, authorize_metadata)
from app.services.linux_safety import (ensure, require_linux, normalize_uuid, owned_fd,
    open_absolute_directory, open_beneath, identity, mount_for_fd)
from app.services.linux_preflight import (read_manifest, validate_binding, inspect_operation,
    stage_payload, recheck_anchors, check_previous, require_absent, TRANSPORT_FILESYSTEMS)
from app.services.linux_file_ops import (parent_of, file_snapshot, dir_snapshot, backup_file,
    make_temporary, verify_blob, rename_noreplace, loop_image_identity)


def execution_authorized(entry, root, confirmed):
    ensure(entry["purpose"] == "bundle-test", "Registration does not authorize bundle application")
    ensure(normalize_uuid(confirmed) == entry["mount"]["uuid"], "Confirmation UUID mismatch")
    ensure(loop_image_identity(root) == entry["loop_image"], "Loop test image changed")


class Run:
    def __init__(self, store, entry, record, directory, backup, value):
        self.store, self.entry, self.record = store, entry, record
        self.directory, self.backup, self.value = directory, backup, value

    def save(self, event):
        events = self.value["events"]
        previous = events[-1]["digest"] if events else "0"*64
        item = dict(sequence=len(events)+1, previous=previous, event=event)
        item["digest"] = document_hash(item)
        events.append(item)
        atomic_json(self.directory, "run.json", self.value)
        self.record.update(status=self.value["status"], run_sha256=document_hash(self.value))
        self.store.save_records()


def validate_events(value):
    previous = "0"*64
    for number, event in enumerate(value["events"], 1):
        item = dict(event); digest = item.pop("digest")
        ensure(item["sequence"] == number and item["previous"] == previous and document_hash(item) == digest,
               "Execution event chain corrupted")
        previous = digest


def load_run(store, entry, storage, bundle_id, stack):
    identifier(bundle_id)
    record = store.records.get("executions", {}).get(entry["target_key"], {}).get(bundle_id)
    ensure(record is not None and "run_sha256" in record, "Execution evidence missing or initialization interrupted")
    state = stack.enter_context(owned_fd(open_beneath(storage["state"], record["directory"], os.O_RDONLY | os.O_DIRECTORY)))
    backup = stack.enter_context(owned_fd(open_beneath(storage["backup"], record["directory"], os.O_RDONLY | os.O_DIRECTORY)))
    value = read_private_json(state, "run.json")
    ensure(document_hash(value) == record["run_sha256"], "Journal/registry disagree; manual evidence review required")
    validate_events(value)
    ensure(value["manifest"]["bundle_id"] == bundle_id and manifest_hash(value["manifest"]) == record["manifest_sha256"],
           "Execution manifest mismatch")
    loads(canonical(value["manifest"]).encode("utf-8"))
    validate_binding(value["manifest"], entry)
    return Run(store, entry, record, state, backup, value)


def observe(root, descriptor):
    with parent_of(root, descriptor["path"]) as (parent, name):
        current = dir_snapshot(parent, name) if descriptor["kind"] in ("mkdir", "rmdir") else file_snapshot(parent, name)
        temporary = file_snapshot(parent, descriptor["temporary"]) if descriptor.get("temporary") else None
        destination = file_snapshot(parent, descriptor["new_path"].rpartition("/")[2]) if descriptor["kind"] == "rename_file" else None
        return dict(current=current, temporary=temporary, destination=destination, parent=identity(parent))


def classification(descriptor, observed):
    if observed["parent"] != descriptor["parent"]:
        return "UNKNOWN"
    current, after = observed["current"], descriptor.get("after")
    kind = descriptor["kind"]
    if kind in ("create_file", "replace_file"):
        if current == after and after is not None and observed["temporary"] is None:
            return "COMMITTED"
        if current == descriptor["before"] and observed["temporary"] == after and after is not None:
            return "NOT_COMMITTED"
    elif kind == "rename_file":
        if current is None and observed["destination"] == descriptor["before"]:
            return "COMMITTED"
        if current == descriptor["before"] and observed["destination"] is None:
            return "NOT_COMMITTED"
    elif kind in ("delete_file", "rmdir"):
        if current == descriptor["before"]:
            return "NOT_COMMITTED"
        if current is None and descriptor["status"] == "COMMITTED":
            return "COMMITTED"
    elif kind == "mkdir":
        if after is not None and current == after:
            return "COMMITTED"
        if current is None:
            return "NOT_COMMITTED"
    return "UNKNOWN"


def sync_adopted(root, descriptor):
    """Observation alone is not a durability boundary after interrupted publication."""
    with parent_of(root, descriptor["path"]) as (parent, name):
        if descriptor.get("restore_times"):
            from app.services.linux_safety import open_regular
            with owned_fd(open_regular(parent, name)) as fd:
                os.utime(fd, ns=tuple(descriptor["restore_times"])); os.fsync(fd)
        os.fsync(parent)
    descriptor["status"] = "COMMITTED"


def commit_descriptor(run, root, descriptor):
    ensure(classification(descriptor, observe(root, descriptor)) == "NOT_COMMITTED", "Publication precondition changed")
    with parent_of(root, descriptor["path"]) as (parent, name):
        kind = descriptor["kind"]
        if kind == "create_file": rename_noreplace(parent, descriptor["temporary"], name)
        elif kind == "replace_file": os.replace(descriptor["temporary"], name, src_dir_fd=parent, dst_dir_fd=parent)
        elif kind == "delete_file": os.unlink(name, dir_fd=parent)
        elif kind == "rmdir": os.rmdir(name, dir_fd=parent)
        elif kind == "rename_file": rename_noreplace(parent, name, descriptor["new_path"].rpartition("/")[2])
        elif kind == "mkdir":
            os.mkdir(name, 0o700, dir_fd=parent)
            with owned_fd(open_beneath(parent, name, os.O_RDONLY | os.O_DIRECTORY)) as fd:
                meta = descriptor["metadata"]
                os.fchown(fd, meta["uid"], meta["gid"]); os.fchmod(fd, meta["mode"])
                os.fsync(fd)
            descriptor["after"] = dir_snapshot(parent, name)
            actual = descriptor["after"]
            ensure(actual["uid"] == meta["uid"] and actual["gid"] == meta["gid"]
                   and stat.S_IMODE(actual["mode"]) == meta["mode"], "Created directory metadata mismatch")
        os.fsync(parent)
    descriptor["status"] = "COMMITTED"
    ensure(classification(descriptor, observe(root, descriptor)) == "COMMITTED", "Postcondition mismatch")
    if descriptor.get("restore_times"):
        with parent_of(root, descriptor["path"]) as (parent, name):
            from app.services.linux_safety import open_regular
            with owned_fd(open_regular(parent, name)) as fd:
                os.utime(fd, ns=tuple(descriptor["restore_times"])); os.fsync(fd)
            os.fsync(parent)
    run.save("operation-committed")


def prepare_descriptor(run, root, item, operation, *, source=None, restore=None):
    with parent_of(root, operation["path"]) as (parent, name):
        descriptor = dict(kind=operation["type"], path=operation["path"], parent=identity(parent),
                          status="PREPARING", before=None, after=None)
        item.update(descriptor)
        if "new_path" in operation: item["new_path"] = operation["new_path"]
        if operation["type"] not in ("create_file", "mkdir"):
            item["before"] = dir_snapshot(parent, name) if operation["type"] == "rmdir" else file_snapshot(parent, name)
            ensure(item["before"] is not None, "Source disappeared")
        if "metadata" in operation: item["metadata"] = operation["metadata"]
        run.save("operation-preparing")
        if source:
            source_dir, source_name, expected, metadata = source
            item["temporary"] = ".crossdisk-" + uuid.uuid4().hex
            run.save("temporary-intent")
            item["after"] = make_temporary(parent, source_dir, source_name, expected, metadata,
                                            item["temporary"], atime_ns=restore)
            if restore is not None:item["restore_times"] = [restore, metadata["mtime_ns"]]
        item["status"] = "PREPARED"
        run.save("operation-prepared")


def backup_original(run, root, op, item):
    if op["type"] not in ("replace_file", "delete_file"):
        return
    expected = op["precondition"]["object"]
    with parent_of(root, op["path"]) as (parent, name):
        saved = backup_file(parent, name, run.backup, uuid.uuid4().hex+".bin", expected)
        saved.update(path=op["path"], parent=identity(parent))
    metadata_file = uuid.uuid4().hex+".json"
    atomic_json(run.backup, metadata_file, saved)
    item["backup"] = dict(saved, metadata_file=metadata_file, metadata_sha256=document_hash(saved))
    run.save("backup-ready")


def verify_backup(run, saved):
    metadata = read_private_json(run.backup, saved["metadata_file"])
    expected = {k:v for k,v in saved.items() if k not in ("metadata_file", "metadata_sha256")}
    ensure(metadata == expected and document_hash(metadata) == saved["metadata_sha256"], "Backup metadata corrupted")
    verify_blob(run.backup, saved["file"], saved["snapshot"])


def execution_plan(run, root):
    observations = []
    for op, item in zip(run.value["manifest"]["operations"], run.value["operations"]):
        status = item["status"]
        try:
            if item.get("backup"):
                verify_backup(run, item["backup"])
            if "payload" in op:
                verify_blob(run.directory, op["id"]+".payload", op["payload"])
            if item.get("undo"):
                observed = observe(root, item["undo"])
                result = classification(item["undo"], observed)
                result = "ROLLED_BACK" if result == "COMMITTED" else "UNDO_PENDING" if result == "NOT_COMMITTED" else "UNKNOWN"
            elif status == "PENDING":
                observed = inspect_operation(root, op, run.entry["policy"])
                result = "PENDING"
            elif status == "PREPARING":
                observed = {}; result = "UNKNOWN"
            else:
                observed = observe(root, item)
                result = classification(item, observed)
                if status == "COMMITTED" and result != "COMMITTED":result = "UNKNOWN"
            observations.append(dict(id=op["id"], result=result, observed=observed))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            observations.append(dict(id=op["id"], result="UNKNOWN", error=str(exc)))
    plan = dict(bundle_id=run.value["manifest"]["bundle_id"], status=run.value["status"],
                journal_sha256=run.record["run_sha256"], observations=observations)
    plan["plan_sha256"] = document_hash(plan)
    return plan


def execute_remaining(run, root, storage):
    for op, item in zip(run.value["manifest"]["operations"], run.value["operations"]):
        recheck_anchors(run.entry, root, storage)
        if item["status"] == "COMMITTED":continue
        if item["status"] == "PENDING":
            inspect_operation(root, op, run.entry["policy"])
            backup_original(run, root, op, item)
            source = None
            if "payload" in op:
                meta = op.get("metadata") or op["precondition"]["object"]
                source = (run.directory, op["id"]+".payload", op["payload"], meta)
            prepare_descriptor(run, root, item, op, source=source)
            inspect_operation(root, op, run.entry["policy"])
        commit_descriptor(run, root, item)
    run.value["status"] = "COMPLETED"; run.save("bundle-completed")


def apply(bundle, target, confirm_uuid):
    require_linux()
    with registry() as store, registered_target(store, target) as (entry, root, storage), ExitStack() as stack:
        execution_authorized(entry, root, confirm_uuid)
        source = stack.enter_context(owned_fd(open_absolute_directory(os.path.abspath(bundle))))
        ensure(mount_for_fd(source)["filesystem"] in TRANSPORT_FILESYSTEMS, "Unsupported bundle transport")
        manifest = read_manifest(source); validate_binding(manifest, entry)
        ensure(len(manifest["operations"]) <= 100, "Executor V1 supports at most 100 operations")
        digest = manifest_hash(manifest)
        executions = store.records.setdefault("executions", {}).setdefault(entry["target_key"], {})
        for bid in executions:
            previous = load_run(store, entry, storage, bid, stack)
            ensure(previous.value["status"] in ("COMPLETED", "ROLLED_BACK"), "Target has an unfinished execution")
        if manifest["bundle_id"] in executions:
            previous = load_run(store, entry, storage, manifest["bundle_id"], stack)
            ensure(previous.record["manifest_sha256"] == digest, "Bundle ID already bound to another manifest")
            return dict(status=previous.value["status"], repeated=True, target_modified=False)
        semantic = deepcopy(manifest); semantic.pop("bundle_id")
        ensure(not any(r.get("semantic_sha256") == document_hash(semantic) for r in executions.values()),
               "Duplicate semantic operation request; no implicit reapplication")
        for record in store.records["runs"].get(entry["target_key"], {}).values():
            check_previous(record, record["manifest_sha256"], storage["state"])
        total = sum(op.get("payload", {}).get("size", 0) for op in manifest["operations"])
        backups = sum(op.get("precondition", {}).get("object", {}).get("size", 0)
                      for op in manifest["operations"] if op["type"] in ("delete_file", "replace_file"))
        ensure(total <= 512*1024*1024, "Payload staging limit exceeded")
        for fd in (root, storage["state"], storage["backup"]):
            space = os.fstatvfs(fd)
            ensure(space.f_bavail*space.f_frsize >= total+backups+32*1024*1024, "Insufficient execution space")
        for op in manifest["operations"]:inspect_operation(root, op, entry["policy"])
        name = "execution-"+uuid.uuid4().hex
        record = dict(status="INITIALIZING", directory=name, manifest_sha256=digest,
                      semantic_sha256=document_hash(semantic))
        executions[manifest["bundle_id"]] = record; store.save_records()
        for fd in storage.values():os.mkdir(name, 0o700, dir_fd=fd); os.fsync(fd)
        state = stack.enter_context(owned_fd(open_beneath(storage["state"], name, os.O_RDONLY | os.O_DIRECTORY)))
        backup = stack.enter_context(owned_fd(open_beneath(storage["backup"], name, os.O_RDONLY | os.O_DIRECTORY)))
        value = dict(status="STAGING", manifest=manifest, events=[], operations=[dict(status="PENDING") for op in manifest["operations"]])
        run = Run(store, entry, record, state, backup, value)
        try:
            run.save("execution-created")
            for op in manifest["operations"]:
                if "payload" in op:stage_payload(source, state, op)
            for op in manifest["operations"]:inspect_operation(root, op, entry["policy"])
            value["status"] = "APPLYING"; run.save("bundle-applying")
            execute_remaining(run, root, storage)
        except BaseException as exc:
            value["status"] = "NEEDS_RECOVERY"; value["error"] = str(exc)
            run.save("execution-stopped")
            raise
        return dict(status=value["status"], bundle_id=manifest["bundle_id"], repeated=False, target_modified=True)


def recover(target, bundle_id, *, action="check", confirm_uuid=None, confirm_plan=None):
    require_linux()
    with registry() as store, registered_target(store, target) as (entry, root, storage), ExitStack() as stack:
        ensure(entry["purpose"] == "bundle-test", "Registration is preflight-only")
        ensure(loop_image_identity(root) == entry["loop_image"], "Loop backing changed")
        run = load_run(store, entry, storage, bundle_id, stack)
        plan = execution_plan(run, root)
        if action == "check":return plan
        ensure(action in ("resume", "rollback"), "Unknown recovery action")
        execution_authorized(entry, root, confirm_uuid)
        ensure(confirm_plan == plan["plan_sha256"], "Recovery plan changed; run --check again")
        ensure(all(o["result"] != "UNKNOWN" for o in plan["observations"]), "Ambiguous evidence; manual review required")
        if run.value["status"] == "ROLLED_BACK":return plan
        if action == "resume" and run.value["status"] == "COMPLETED":return plan
        try:
            if action == "resume":
                ensure(not any(item.get("undo") for item in run.value["operations"]), "Rollback already started")
                for item, obs in zip(run.value["operations"], plan["observations"]):
                    if obs["result"] == "COMMITTED":
                        sync_adopted(root, item)
                run.value["status"] = "APPLYING"; run.save("explicit-resume")
                execute_remaining(run, root, storage)
            else:
                run.value["status"] = "ROLLING_BACK"; run.save("explicit-rollback")
                pairs = list(zip(run.value["manifest"]["operations"], run.value["operations"], plan["observations"]))
                for op, item, obs in reversed(pairs):
                    recheck_anchors(entry, root, storage)
                    if obs["result"] == "ROLLED_BACK":
                        sync_adopted(root, item["undo"])
                        run.save("rollback-result-adopted")
                        continue
                    if obs["result"] in ("PENDING", "NOT_COMMITTED"):continue
                    if not item.get("undo"):
                        ensure(classification(item, observe(root, item)) == "COMMITTED", "Rollback target changed")
                        kind = op["type"]
                        if kind in ("create_file", "mkdir"):
                            inverse = dict(type="delete_file" if kind == "create_file" else "rmdir", path=op["path"])
                            if kind == "mkdir":ensure(item["after"]["empty"], "Directory is not empty")
                            source_data = None; atime = None
                        elif kind == "rename_file":
                            inverse = dict(type="rename_file", path=op["new_path"], new_path=op["path"])
                            source_data = None; atime = None
                        else:
                            saved = item["backup"]; verify_backup(run, saved)
                            inverse = dict(type="create_file" if kind == "delete_file" else "replace_file", path=op["path"])
                            source_data = (run.backup, saved["file"], saved["snapshot"], saved["snapshot"])
                            atime = saved["atime_ns"]
                        item["undo"] = {}
                        prepare_descriptor(run, root, item["undo"], inverse, source=source_data, restore=atime)
                    commit_descriptor(run, root, item["undo"])
                run.value["status"] = "ROLLED_BACK"; run.save("rollback-completed")
        except BaseException as exc:
            run.value["status"] = "NEEDS_RECOVERY"; run.value["error"] = str(exc); run.save("recovery-stopped")
            raise
        return execution_plan(run, root)
