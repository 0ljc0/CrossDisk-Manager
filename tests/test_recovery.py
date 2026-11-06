import pytest
import hashlib
import json
from app.core.recovery import classify_replace, classify_evidence


def states():
    before=dict(kind="regular_file",size=4,sha256="a"*64,mode=0o100644,uid=1000,gid=1000,
                mtime_ns=123,nlink=1,inode=10)
    after=dict(before,sha256="b"*64,inode=11)
    return dict(status="PREPARED",before=before,after=after),before,after


def test_known_crash_windows():
    record,before,after=states()
    assert classify_replace(record,before,after,backup_valid=True)=="NOT_COMMITTED"
    assert classify_replace(record,after,None,backup_valid=True)=="COMMITTED"


@pytest.mark.parametrize("change",["missing-backup","missing-temp","conflict","old-inode","bad-mode","both-present","bad-record"])
def test_ambiguous_states_never_resume(change):
    record,before,after=states();current=before;temporary=after;valid=True
    if change=="missing-backup":valid=False
    if change=="missing-temp":temporary=None
    if change=="conflict":current=dict(before,sha256="c"*64)
    if change=="old-inode":current=dict(after,inode=before["inode"]);temporary=None
    if change=="bad-mode":record["after"]["mode"]=0o104644
    if change=="both-present":current=after
    if change=="bad-record":record={}
    assert classify_replace(record,current,temporary,backup_valid=valid)=="UNKNOWN"


@pytest.mark.parametrize("failure",[None,"truncated","altered","missing-backup","bad-backup","missing-record"])
def test_evidence_integrity(failure):
    record,before,after=states()
    data=b"test"
    before["sha256"]=hashlib.sha256(data).hexdigest()
    raw=json.dumps(record).encode();anchor=hashlib.sha256(raw).hexdigest()
    if failure=="truncated":raw=raw[:10]
    if failure=="altered":raw+=b" "
    if failure=="missing-backup":data=None
    if failure=="bad-backup":data=b"evil"
    if failure=="missing-record":raw=None
    result=classify_evidence(raw,anchor,before,after,data,before)
    assert result==("NOT_COMMITTED" if failure is None else "UNKNOWN")


def test_rollback_evidence_binds_original_backup_to_destination():
    record,before,after=states()
    data=b"test";after["sha256"]=hashlib.sha256(data).hexdigest()
    raw=json.dumps(record).encode()
    assert classify_evidence(raw,hashlib.sha256(raw).hexdigest(),after,None,data,dict(after,inode=99))=="COMMITTED"
