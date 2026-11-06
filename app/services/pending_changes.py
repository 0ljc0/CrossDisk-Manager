"""Conservative, transactional staging state; no disk access or direct writes."""
from copy import deepcopy
import uuid

from app.core.bundle import BundleError, path, validate, require


class PendingChangesService:
    def __init__(self, target):
        self._target = deepcopy(target)
        self._operations = []
        self._bundle_id = uuid.uuid4().hex
        # Validate target even while the actual pending list is empty.
        probe = self._manifest([dict(id="probe", type="mkdir", path="probe",
                                    precondition={"target": "absent"},
                                    metadata=dict(uid=1, gid=1, mode=0o700))])
        self._target = validate(probe)["target"]

    def _manifest(self, operations):
        return dict(format="crossdisk-bundle", version=3, bundle_id=self._bundle_id,
                    target=deepcopy(self._target), operations=deepcopy(operations))

    def manifest(self):
        require(bool(self._operations), "No pending changes to export")
        return validate(self._manifest(self._operations))

    def operations(self):
        return deepcopy(self._operations)

    def _commit(self, operations):
        if operations:
            validate(self._manifest(operations))
            require(sum(op.get("payload", {}).get("size", 0) for op in operations) <= 512 * 1024 * 1024,
                    "Pending bundle exceeds 512 MiB staging budget")
        if operations != self._operations:
            self._operations = deepcopy(operations)
            # A changed draft must never reuse the identity of an exported bundle.
            self._bundle_id = uuid.uuid4().hex

    def _existing(self, relative):
        path(relative)
        return next((op for op in self._operations if op["path"] == relative), None)

    def _stage(self, relative, kind, **fields):
        op = dict(id=uuid.uuid4().hex, type=kind, path=relative, **deepcopy(fields))
        self._commit(self._operations + [op])

    def create_file(self, relative, payload, metadata):
        require(self._existing(relative) is None, "Cancel the existing operation before creating this path")
        self._stage(relative, "create_file", precondition={"target": "absent"}, payload=payload, metadata=metadata)

    def replace_file(self, relative, payload, expected_state=None):
        previous = self._existing(relative)
        if previous:
            require(previous["type"] in ("create_file", "replace_file"), "Operation combination is unsupported")
            if previous["type"] == "replace_file" and expected_state is not None:
                require(previous["precondition"]["object"] == expected_state, "Original snapshot changed")
            updated = deepcopy(previous)
            updated["payload"] = deepcopy(payload)
            self._commit([updated if op["id"] == previous["id"] else op for op in self._operations])
        else:
            require(expected_state is not None, "Original snapshot required")
            self._stage(relative, "replace_file", precondition=dict(target="matches", object=expected_state),
                        payload=payload, metadata_policy="preserve_basic")

    def delete_file(self, relative, expected_state=None):
        previous = self._existing(relative)
        if previous:
            require(previous["type"] in ("create_file", "replace_file"), "Operation combination is unsupported")
            others = [op for op in self._operations if op["id"] != previous["id"]]
            if previous["type"] == "create_file":
                self._commit(others)
                return
            if expected_state is not None:
                require(previous["precondition"]["object"] == expected_state, "Original snapshot changed")
            updated = deepcopy(previous)
            updated.pop("payload")
            updated.pop("metadata_policy")
            updated["type"] = "delete_file"
            self._commit(others + [updated])
        else:
            require(expected_state is not None, "Original snapshot required")
            self._stage(relative, "delete_file", precondition=dict(target="matches", object=expected_state))

    def create_directory(self, relative, metadata):
        require(self._existing(relative) is None, "Path already staged")
        self._stage(relative, "mkdir", precondition={"target": "absent"}, metadata=metadata)

    def rename_file(self, relative, new_path, expected_state):
        require(self._existing(relative) is None, "Rename cannot be combined with an existing operation")
        self._stage(relative, "rename_file", new_path=new_path, source_precondition=expected_state,
                    destination_precondition={"target": "absent"})

    def cancel(self, operation_id):
        require(any(op["id"] == operation_id for op in self._operations), "Unknown pending operation")
        self._commit([op for op in self._operations if op["id"] != operation_id])

    def status(self, relative):
        path(relative)
        for op in self._operations:
            if relative in (op["path"], op.get("new_path")):
                return {"create_file": "PENDING_CREATE", "replace_file": "PENDING_UPDATE",
                        "delete_file": "PENDING_DELETE", "mkdir": "PENDING_CREATE",
                        "rename_file": "PENDING_RENAME"}[op["type"]]
        return "SYNCED"
