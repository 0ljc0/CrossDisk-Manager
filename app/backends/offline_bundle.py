"""Windows-local staging/export. The ext4 reader remains strictly read-only."""
from dataclasses import asdict
import hashlib
import io
import os
from pathlib import Path
import stat
import tempfile
import uuid

from app.core.bundle import canonical, loads, manifest_hash, path, require
from app.services.file_snapshot import read_snapshot
from app.services.pending_changes import PendingChangesService

MAX_PAYLOAD_BYTES = 512 * 1024 * 1024


class OfflineBundleBackend:
    can_stage_changes = True
    can_export_bundle = True
    can_write_directly = False

    def __init__(self, reader, fs_relative_root, *, workspace_parent):
        path(fs_relative_root)
        self.reader = reader
        self.root = fs_relative_root
        self._directory(self.root)
        self.pending = PendingChangesService(dict(filesystem="ext4", fs_uuid=reader.probe["uuid"],
                                                 mount_relative_root=self.root))
        parent = Path(workspace_parent).absolute()
        parent.mkdir(parents=True, exist_ok=True)
        require(not parent.is_symlink() and parent.is_dir(), "Workspace must be an ordinary local directory")
        self.workspace = Path(tempfile.mkdtemp(prefix="crossdisk-pending-", dir=parent)).resolve()
        (self.workspace / "files").mkdir()
        self._owned = set()
        self._closed = False
        self._anchors = [(p, (p.stat().st_dev, p.stat().st_ino))
                         for p in (self.workspace, self.workspace / "files")]

    def _open(self):
        require(not self._closed, "Staging workspace is closed")
        for directory, expected in self._anchors:
            info = directory.lstat()
            require(stat.S_ISDIR(info.st_mode) and not directory.is_symlink()
                    and not getattr(info, "st_file_attributes", 0) & 0x400
                    and (info.st_dev, info.st_ino) == expected, "Staging directory identity changed")

    def _directory(self, relative):
        entry = self.reader.stat(relative)
        require(entry.is_directory is True and entry.is_link is False and not entry.error,
                "Parent must be a readable ordinary ext4 directory")

    def _full(self, relative):
        return self.root + "/" + path(relative)

    def _absent(self, relative):
        full = self._full(relative)
        parent, _, name = full.rpartition("/")
        self._directory(parent)
        offset, fingerprint, pages = 0, "", 0
        while True:
            page = self.reader.list_dir(parent, offset=offset, show_hidden=True, fingerprint=fingerprint)
            require(not any(entry.error for entry in page.entries), "Directory contains unreadable names or metadata")
            require(not any(entry.name == name for entry in page.entries), "Target already exists on ext4")
            if page.next_offset is None:
                return
            require(page.next_offset > offset and pages < 10000, "Cannot establish target absence within scan budget")
            offset, fingerprint, pages = page.next_offset, page.fingerprint, pages + 1

    def _snapshot(self, relative):
        return asdict(read_snapshot(self.reader, self._full(relative)))

    def _payload(self, content):
        stream = io.BytesIO(content) if isinstance(content, bytes) else content
        require(hasattr(stream, "read"), "Content must be bytes or a binary stream")
        name = uuid.uuid4().hex + ".bin"
        self._owned.add(name)
        digest, size = hashlib.sha256(), 0
        with (self.workspace / "files" / name).open("xb") as target:
            while chunk := stream.read(1024 * 1024):
                require(isinstance(chunk, bytes), "Content stream must return bytes")
                size += len(chunk)
                require(size <= MAX_PAYLOAD_BYTES, "Payload exceeds 512 MiB staging budget")
                target.write(chunk)
                digest.update(chunk)
            target.flush()
            os.fsync(target.fileno())
        return dict(path="files/"+name, size=size, sha256=digest.hexdigest())

    def _prune(self):
        used = {op["payload"]["path"].split("/")[1] for op in self.pending.operations() if "payload" in op}
        for name in list(self._owned - used):
            file = self.workspace / "files" / name
            if file.exists():
                require(stat.S_ISREG(file.lstat().st_mode), "Workspace object was replaced")
                file.unlink()
            self._owned.remove(name)

    def _change(self, method, relative, content=None, **fields):
        self._open()
        try:
            if method in ("create_file", "replace_file"):
                fields["payload"] = self._payload(content)
            getattr(self.pending, method)(relative, **fields)
        finally:
            self._prune()

    def create_file(self, relative, content, metadata):
        self._open()
        self._absent(relative)
        self._change("create_file", relative, content, metadata=metadata)

    def replace_file(self, relative, content):
        self._open()
        created = self.pending.status(relative) == "PENDING_CREATE"
        expected = None if created else self._snapshot(relative)
        self._change("replace_file", relative, content, expected_state=expected)

    def delete_file(self, relative):
        self._open()
        created = self.pending.status(relative) == "PENDING_CREATE"
        self._change("delete_file", relative, expected_state=None if created else self._snapshot(relative))

    def create_directory(self, relative, metadata):
        self._open()
        self._absent(relative)
        self._change("create_directory", relative, metadata=metadata)

    def rename_file(self, relative, new_path):
        self._open()
        self._absent(new_path)
        self._change("rename_file", relative, new_path=new_path, expected_state=self._snapshot(relative))

    def cancel(self, operation_id):
        self._open()
        self.pending.cancel(operation_id)
        self._prune()

    def export_bundle(self, destination):
        self._open()
        manifest = self.pending.manifest()
        raw = canonical(manifest).encode("utf-8")
        loads(raw)  # Same byte limit and contract as Ubuntu.
        require(sum(op.get("payload", {}).get("size", 0) for op in manifest["operations"]) <= MAX_PAYLOAD_BYTES,
                "Bundle exceeds Ubuntu staging budget")
        output = Path(destination).absolute()
        output.mkdir(exist_ok=False)  # Never merge with or overwrite a user directory.
        (output / "files").mkdir()
        # manifest.json is the completion marker and is written last. On error,
        # keep the incomplete output for review; never recursively delete user paths.
        for op in manifest["operations"]:
            if "payload" not in op:
                continue
            payload = op["payload"]
            source = self.workspace / payload["path"]
            require(stat.S_ISREG(source.lstat().st_mode), "Workspace payload is not an ordinary file")
            digest, size = hashlib.sha256(), 0
            with source.open("rb") as reader, (output / payload["path"]).open("xb") as writer:
                while chunk := reader.read(1024 * 1024):
                    size += len(chunk)
                    require(size <= payload["size"], "Staged payload grew")
                    writer.write(chunk)
                    digest.update(chunk)
                require(size == payload["size"] and digest.hexdigest() == payload["sha256"], "Staged payload changed")
                writer.flush()
                os.fsync(writer.fileno())
        with (output / "manifest.json").open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return dict(directory=str(output), bundle_id=manifest["bundle_id"], manifest_sha256=manifest_hash(manifest),
                    operations=len(manifest["operations"]), applied=False)

    def close(self):
        if self._closed:
            return
        self._open()  # Refuse cleanup if the private directory was rebound.
        self._closed = True
        for name in list(self._owned):
            file = self.workspace / "files" / name
            if file.exists():
                require(stat.S_ISREG(file.lstat().st_mode), "Unexpected workspace object; retained for review")
                file.unlink()
            self._owned.remove(name)
        (self.workspace / "files").rmdir()
        self.workspace.rmdir()

    def __enter__(self):
        self._open()
        return self

    def __exit__(self, *args):
        self.close()
