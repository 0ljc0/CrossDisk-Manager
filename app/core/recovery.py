"""Conservative single-replace recovery classification; never performs I/O."""
import hashlib
from app.core.bundle import snapshot
from app.services.linux_safety import json_unique


def classify_evidence(raw_record, expected_digest, current, temporary, backup_bytes, expected_backup):
    """Reject missing/corrupt evidence before examining a recovery transition."""
    try:
        if not isinstance(raw_record, bytes) or not isinstance(backup_bytes, bytes):
            return "UNKNOWN"
        if hashlib.sha256(raw_record).hexdigest() != expected_digest:
            return "UNKNOWN"
        snapshot(expected_backup)
        valid = (len(backup_bytes) == expected_backup["size"]
                 and hashlib.sha256(backup_bytes).hexdigest() == expected_backup["sha256"])
        record = json_unique(raw_record)
        # For rollback, the backup describes the destination state, not its old inode.
        fields = ("kind", "size", "sha256", "mode", "uid", "gid", "mtime_ns", "nlink")
        bound = any(all(record[side][k] == expected_backup[k] for k in fields)
                    for side in ("before", "after"))
        return classify_replace(record, current, temporary, backup_valid=valid and bound)
    except (ValueError, KeyError, TypeError):
        return "UNKNOWN"


def classify_replace(record, current, temporary, *, backup_valid):
    """Classify only a durable PREPARED record with verified backup evidence."""
    try:
        if not backup_valid or type(record) is not dict or record.get("status") != "PREPARED":
            return "UNKNOWN"
        before, after = record["before"], record["after"]
        snapshot(before)
        snapshot(after)
        if before == after:
            return "UNKNOWN"
        if current == before and temporary == after:
            return "NOT_COMMITTED"
        if current == after and temporary is None:
            return "COMMITTED"
    except (ValueError, KeyError, TypeError):
        pass
    return "UNKNOWN"
