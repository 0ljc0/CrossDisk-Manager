import sys
import pytest
from scripts import write_lab
from app.services import linux_safety


def test_restore_comparison_checks_metadata_but_not_recreated_inode():
    source=dict(kind="regular_file",size=3,sha256="a"*64,mode=0o100644,uid=1000,gid=1000,
                mtime_ns=123456789,nlink=1,inode=4)
    assert write_lab.restored_equal(source,dict(source,inode=5))
    for key,value in (("mode",0o100600),("uid",0),("mtime_ns",0),("sha256","b"*64)):
        assert not write_lab.restored_equal(source,dict(source,**{key:value}))


def test_lab_has_no_existing_target_option(monkeypatch):
    monkeypatch.setattr(sys,"argv",["write_lab","--run-disposable-tests","--image","existing.img"])
    with pytest.raises(SystemExit) as caught:write_lab.main()
    assert caught.value.code==2


def test_lab_refuses_windows_before_creating_files(monkeypatch):
    monkeypatch.setattr(sys,"argv",["write_lab","--run-disposable-tests"])
    monkeypatch.setattr(linux_safety.platform,"system",lambda:"Windows")
    with pytest.raises(ValueError,match="Linux"):write_lab.main()
