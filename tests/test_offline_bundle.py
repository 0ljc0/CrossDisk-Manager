from copy import deepcopy
import hashlib
import io
import json
import struct

import pytest

from app.backends.ext4_readonly import Ext4ReadOnlyBackend
from app.backends.offline_bundle import OfflineBundleBackend
from app.core.bundle import BundleError, loads
from app.services.pending_changes import PendingChangesService
from scripts.validate_bundle import check
from ext4_fixture import make_image


TARGET=dict(filesystem="ext4",fs_uuid="a"*32,mount_relative_root="home/demo")
META=dict(uid=1000,gid=1000,mode=0o644)
OLD=dict(kind="regular_file",size=3,sha256=hashlib.sha256(b"old").hexdigest(),mode=0o100644,
         uid=1000,gid=1000,mtime_ns=123,nlink=1,inode=14)


def payload(data=b"new",name="a.bin"):
    return dict(path="files/"+name,size=len(data),sha256=hashlib.sha256(data).hexdigest())


def test_new_edit_delete_cancels():
    pending=PendingChangesService(TARGET)
    pending.create_file("a",payload(),META)
    first=pending.manifest()["bundle_id"]
    pending.replace_file("a",payload(b"latest"))
    assert pending.manifest()["bundle_id"]!=first
    assert pending.manifest()["operations"][0]["type"]=="create_file"
    pending.delete_file("a")
    assert pending.operations()==[] and pending.status("a")=="SYNCED"
    with pytest.raises(BundleError):pending.manifest()


def test_repeated_edit_preserves_original_and_delete_discards_payload():
    pending=PendingChangesService(TARGET)
    pending.replace_file("a",payload(),OLD)
    pending.replace_file("a",payload(b"latest"))
    assert pending.manifest()["operations"][0]["precondition"]["object"]==OLD
    before=pending.manifest()
    with pytest.raises(BundleError):pending.replace_file("a",payload(),dict(OLD,inode=19))
    assert pending.manifest()==before
    pending.delete_file("a")
    assert pending.status("a")=="PENDING_DELETE"
    assert "payload" not in pending.manifest()["operations"][0]
    with pytest.raises(BundleError):pending.create_file("a",payload(),META)


def test_rename_reserves_both_names_and_rejects_dependencies_transactionally():
    pending=PendingChangesService(TARGET)
    pending.rename_file("a","b",OLD)
    before=pending.manifest()
    assert pending.status("a")==pending.status("b")=="PENDING_RENAME"
    for name in ("a","b","a/sub"):
        with pytest.raises(BundleError):pending.create_file(name,payload(),META)
        assert pending.manifest()==before
    copy=pending.operations();copy[0]["path"]="changed"
    assert pending.operations()[0]["path"]=="a"
    pending.cancel(before["operations"][0]["id"])
    assert pending.operations()==[]


def test_new_directory_cannot_be_used_in_same_bundle():
    pending=PendingChangesService(TARGET)
    pending.create_directory("dir",META)
    with pytest.raises(BundleError):pending.create_file("dir/a",payload(),META)
    assert len(pending.operations())==1


def test_bundle_budget_rejection_preserves_existing_draft():
    pending=PendingChangesService(TARGET)
    pending.create_file("valid",payload(),META)
    before=pending.manifest()
    huge=payload();huge["size"]=512*1024*1024
    with pytest.raises(BundleError,match="budget"):
        pending.create_file("too-large",huge,META)
    assert pending.manifest()==before


@pytest.fixture
def reader(tmp_path):
    image=make_image(tmp_path/"test.img")
    raw=bytearray(image.read_bytes())
    for inode in (14,15,16):
        position=5*1024+(inode-1)*256
        struct.pack_into("<H",raw,position+2,1000)
        struct.pack_into("<H",raw,position+24,1000)
    image.write_bytes(raw)
    before=hashlib.sha256(raw).hexdigest()
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        yield backend
        assert not backend.get_capabilities().write
    assert hashlib.sha256(image.read_bytes()).hexdigest()==before


def test_real_reader_five_operation_export(reader,tmp_path):
    with OfflineBundleBackend(reader,"home/demo",workspace_parent=tmp_path/"drafts") as writer:
        writer.create_file("CON",b"Windows reserved name is only in manifest",META)
        writer.replace_file("sample.txt",io.BytesIO(b"edited\x00binary"))
        writer.delete_file(".hidden")
        writer.rename_file("中文 空格.txt","renamed.txt")
        writer.create_directory("newdir",dict(META,mode=0o755))
        result=writer.export_bundle(tmp_path/"export")
        assert result["operations"]==5 and not result["applied"]
        report=check(tmp_path/"export")
        assert report["package_valid"] and not report["apply_allowed"]
        manifest=loads((tmp_path/"export/manifest.json").read_bytes())
        assert {op["type"] for op in manifest["operations"]}=={"create_file","replace_file","delete_file","mkdir","rename_file"}
        assert writer.export_bundle(tmp_path/"same-draft")["bundle_id"]==result["bundle_id"]
        with pytest.raises(FileExistsError):writer.export_bundle(tmp_path/"export")
        assert not writer.can_write_directly


def test_frozen_payload_cancel_cleanup_and_tamper(reader,tmp_path):
    writer=OfflineBundleBackend(reader,"home/demo",workspace_parent=tmp_path/"drafts")
    source=io.BytesIO(b"first")
    writer.create_file("new",source,META)
    source.seek(0);source.write(b"other")
    writer.export_bundle(tmp_path/"frozen")
    op=writer.pending.operations()[0]
    assert (tmp_path/"frozen"/op["payload"]["path"]).read_bytes()==b"first"
    writer.replace_file("new",b"latest")
    assert len(list((writer.workspace/"files").iterdir()))==1
    op=writer.pending.operations()[0]
    (writer.workspace/op["payload"]["path"]).write_bytes(b"tampered")
    with pytest.raises(BundleError):writer.export_bundle(tmp_path/"incomplete")
    assert not (tmp_path/"incomplete/manifest.json").exists()
    writer.cancel(op["id"])
    assert list((writer.workspace/"files").iterdir())==[]
    workspace=writer.workspace
    writer.close();writer.close()
    assert not workspace.exists()


def test_failure_keeps_draft_and_prunes_failed_payload(reader,tmp_path):
    with OfflineBundleBackend(reader,"home/demo",workspace_parent=tmp_path/"drafts") as writer:
        writer.create_file("new",b"valid",META)
        before=writer.pending.manifest()
        with pytest.raises(BundleError):writer.create_file("new",b"invalid",META)
        assert writer.pending.manifest()==before
        assert len(list((writer.workspace/"files").iterdir()))==1
        with pytest.raises(BundleError):writer.create_file("sample.txt",b"no",META)
        with pytest.raises(BundleError):writer.create_file("../escape",b"no",META)
