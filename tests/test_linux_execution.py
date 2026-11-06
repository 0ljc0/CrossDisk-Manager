import copy
import sys
from types import SimpleNamespace
from contextlib import contextmanager

import pytest

from app.services import linux_execution as execution
from app.services.linux_execution import classification, validate_events
from app.services.linux_registry import document_hash
from scripts import apply_bundle, recover_bundle


PARENT=dict(dev=1,inode=2)
BEFORE=dict(kind="regular_file",size=1,sha256="a"*64,mode=0o100644,uid=1000,gid=1000,
            mtime_ns=123,nlink=1,inode=3)
AFTER=dict(BEFORE,sha256="b"*64,inode=4)


def observation(current,temporary=None,destination=None):
    return dict(parent=PARENT,current=current,temporary=temporary,destination=destination)


@pytest.mark.parametrize("kind",["create_file","replace_file"])
def test_file_publish_classification_requires_inode_and_temp_disappearance(kind):
    before=None if kind=="create_file" else BEFORE
    item=dict(kind=kind,status="PREPARED",parent=PARENT,before=before,after=AFTER)
    assert classification(item,observation(before,AFTER))=="NOT_COMMITTED"
    assert classification(item,observation(AFTER))=="COMMITTED"
    assert classification(item,observation(dict(AFTER,inode=5)))=="UNKNOWN"
    assert classification(item,observation(AFTER,AFTER))=="UNKNOWN"


@pytest.mark.parametrize("kind",["delete_file","rmdir"])
def test_disappearance_alone_cannot_prove_interrupted_deletion(kind):
    item=dict(kind=kind,status="PREPARED",parent=PARENT,before=BEFORE,after=None)
    assert classification(item,observation(None))=="UNKNOWN"
    assert classification(dict(item,status="COMMITTED"),observation(None))=="COMMITTED"


def test_rename_must_bind_original_object():
    item=dict(kind="rename_file",status="PREPARED",parent=PARENT,before=BEFORE)
    assert classification(item,observation(BEFORE))=="NOT_COMMITTED"
    assert classification(item,observation(None,destination=BEFORE))=="COMMITTED"
    assert classification(item,observation(None,destination=AFTER))=="UNKNOWN"


def test_directory_created_without_recorded_identity_is_unknown():
    directory=dict(kind="directory",dev=1,inode=7,mode=0o40755,uid=1000,gid=1000,mtime_ns=1,empty=True)
    item=dict(kind="mkdir",status="PREPARED",parent=PARENT,before=None,after=None)
    assert classification(item,observation(directory))=="UNKNOWN"
    item["after"]=directory
    assert classification(item,observation(directory))=="COMMITTED"


def test_execution_event_chain_rejects_edit_or_truncation_of_link():
    first=dict(sequence=1,previous="0"*64,event="created");first["digest"]=document_hash(first)
    second=dict(sequence=2,previous=first["digest"],event="prepared");second["digest"]=document_hash(second)
    value=dict(events=[first,second]);validate_events(value)
    changed=copy.deepcopy(value);changed["events"][0]["event"]="tampered"
    with pytest.raises(ValueError):validate_events(changed)
    with pytest.raises(ValueError):validate_events(dict(events=[second]))


def test_preflight_registration_never_grants_write():
    with pytest.raises(ValueError,match="authorize"):
        execution.execution_authorized(dict(purpose="preflight-only"),0,"a"*32)


def test_recovery_requires_all_confirmations(monkeypatch):
    monkeypatch.setattr(sys,"argv",["recover","--target","t","--bundle-id","b","--rollback"])
    with pytest.raises(SystemExit) as caught:recover_bundle.main()
    assert caught.value.code==2


def test_apply_failure_does_not_claim_target_unchanged(monkeypatch,capsys):
    def fail(*args):raise OSError("injected I/O error")
    monkeypatch.setattr(apply_bundle,"apply",fail)
    monkeypatch.setattr(sys,"argv",["apply","--target","t","--bundle","b","--apply",
        "--confirm-uuid","a"*32,"--confirm-maintenance-window"])
    assert apply_bundle.main()==1
    assert '"target_modified": null' in capsys.readouterr().out


def test_adopting_observed_commit_syncs_before_marking_done(monkeypatch):
    item=dict(path="file",status="PREPARED")
    @contextmanager
    def parent(root,path):yield 123,"file"
    calls=[]
    def sync(fd):
        assert item["status"]=="PREPARED"
        calls.append(fd)
    monkeypatch.setattr(execution,"parent_of",parent)
    monkeypatch.setattr(execution.os,"fsync",sync)
    execution.sync_adopted(0,item)
    assert calls==[123] and item["status"]=="COMMITTED"
