import errno
import sys
import pytest
from app.core.io_failure import disposition
from scripts import io_fault_lab
from app.services import linux_safety


@pytest.mark.parametrize("code",[errno.ENOSPC,errno.EIO,errno.EROFS])
@pytest.mark.parametrize("published",[False,True])
def test_failure_stops_and_never_retries(code,published):
    result=disposition(OSError(code,"test"),publication_attempted=published)
    assert result["status"]==("NEEDS_RECOVERY" if published else "FAILED_STOPPED")
    assert not result["automatic_retry_allowed"] and not result["continue_later_operations"]
    assert result["no_space"]==(code==errno.ENOSPC)


def test_injection_is_explicit_and_only_at_selected_boundary():
    io_fault_lab.injected("backup-read","parent-fsync")
    with pytest.raises(OSError) as caught:io_fault_lab.injected("parent-fsync","parent-fsync")
    assert caught.value.errno==errno.EIO


def test_existing_image_cannot_be_supplied(monkeypatch):
    monkeypatch.setattr(sys,"argv",["lab","--run-disposable-tests","--image","real.img"])
    with pytest.raises(SystemExit) as caught:io_fault_lab.main()
    assert caught.value.code==2


def test_refuses_windows_before_creating_files(monkeypatch):
    monkeypatch.setattr(sys,"argv",["lab","--run-disposable-tests"])
    monkeypatch.setattr(linux_safety.platform,"system",lambda:"Windows")
    with pytest.raises(ValueError,match="Linux"):io_fault_lab.main()
