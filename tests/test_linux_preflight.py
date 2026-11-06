"""Portable policy tests; real syscalls are separately exercised by preflight_lab."""
import copy
import errno
import os
import stat
import sys
from types import SimpleNamespace

import pytest

from app.services import linux_safety as safety
from app.services import linux_registry as registry
from app.services import linux_preflight as preflight
from scripts import apply_bundle, register_target


@pytest.mark.parametrize("root", ["/", "/etc", "/home", "/home/alice", "/var/tmp/test", "/mnt/test"])
def test_reject_broad_or_system_roots(root):
    with pytest.raises(ValueError):
        safety.allowed_test_root("/", root.lstrip("/"))


def test_test_root_mapping_and_system_mount_alias():
    assert safety.allowed_test_root("/home", "alice/CrossDisk_Test") == "/home/alice/CrossDisk_Test"
    assert safety.allowed_test_root("/mnt/test", "g0") == "/mnt/test/g0"
    with pytest.raises(ValueError):
        safety.allowed_test_root("/mnt/root", "etc/test")


def test_mountinfo_escapes_and_bind_root():
    records = safety.parse_mountinfo(
        "33 1 7:0 / /mnt/test\\040image rw,relatime shared:2 - ext4 /dev/loop0 rw\n"
        "34 1 7:0 /g0 /mnt/alias rw - ext4 /dev/loop0 rw\n")
    assert records[0]["mount_point"] == "/mnt/test image"
    assert records[1]["fsroot"] == "/g0"
    assert records[0]["device"] == records[1]["device"]


def test_registration_overlap_alias_and_sibling():
    old = dict(mount={"uuid": "a"*32}, relative_root="home/a/test", storage={})
    for root in ("home/a/test", "home/a", "home/a/test/sub"):
        with pytest.raises(ValueError, match="overlaps"):
            registry.no_registration_overlap({"old": old}, dict(old, relative_root=root))
    registry.no_registration_overlap({"old": old}, dict(old, relative_root="home/a/test2"))


@pytest.mark.parametrize("uids,gids,modes", [([0],[1000],[420]), ([True],[1000],[420]),
                                          ([1000],[1000],[0o4755]), ([1000,1000],[1000],[420])])
def test_policy_rejects_unauthorized_values(uids,gids,modes):
    with pytest.raises(ValueError):
        registry.policy(uids,gids,modes,[0o755])


def test_authorization_uses_separate_file_and_directory_modes():
    policy = registry.policy([1000],[1001],[0o640],[0o750])
    registry.authorize_metadata(dict(uid=1000,gid=1001,mode=0o100640),policy)
    for value in (dict(uid=0,gid=1001,mode=0o640), dict(uid=1000,gid=1001,mode=0o644)):
        with pytest.raises(ValueError): registry.authorize_metadata(value,policy)
    with pytest.raises(ValueError):
        registry.authorize_metadata(dict(uid=1000,gid=1001,mode=0o640),policy,directory=True)


def test_no_linux_fallback(monkeypatch):
    monkeypatch.setattr(safety.platform,"system",lambda:"Windows")
    with pytest.raises(ValueError,match="Linux"):
        safety.open_beneath(-1,"file",0)


def test_missing_openat2_does_not_fallback(monkeypatch):
    monkeypatch.setattr(safety,"require_linux",lambda:None)
    monkeypatch.setattr(safety.os,"O_NOFOLLOW",0x20000,raising=False)
    monkeypatch.setattr(safety.os,"O_CLOEXEC",0x80000,raising=False)
    class Missing:
        def __call__(self,*args): return -1
    monkeypatch.setattr(safety.ctypes,"CDLL",lambda *a,**k:SimpleNamespace(syscall=Missing()))
    monkeypatch.setattr(safety.ctypes,"get_errno",lambda:errno.ENOSYS)
    with pytest.raises(OSError) as caught:
        safety.open_beneath(1,"file",0)
    assert caught.value.errno == errno.ENOSYS


def test_binding_checks_both_uuid_and_root():
    entry=dict(mount={"uuid":"a"*32},relative_root="g0")
    manifest=dict(target=dict(fs_uuid="a"*32,mount_relative_root="g0"))
    preflight.validate_binding(manifest,entry)
    for field in ("fs_uuid","mount_relative_root"):
        bad=copy.deepcopy(manifest);bad["target"][field]="wrong"
        with pytest.raises(ValueError):preflight.validate_binding(bad,entry)


def test_mount_rebind_is_rejected():
    expected=dict(uuid="a"*32,device="7:0",mount_point="/mnt/test",fsroot="/",mount_id=1,
                  namespace=1,boot_id="boot",options=["rw"],super_options=["rw"])
    registry.verify_mount(expected,expected)
    for key in expected:
        with pytest.raises(ValueError):registry.verify_mount(dict(expected,**{key:"changed"}),expected)


def test_cli_has_no_apply_or_registry_override(monkeypatch):
    for option in ("--apply","--state-dir","--backup-dir","--registry"):
        monkeypatch.setattr(sys,"argv",["apply","--bundle","x","--target","t",option])
        with pytest.raises(SystemExit) as caught:apply_bundle.main()
        assert caught.value.code==2


def test_cli_reports_rejection_without_linux(monkeypatch,capsys):
    monkeypatch.setattr(safety.platform,"system",lambda:"Windows")
    monkeypatch.setattr(sys,"argv",["apply","--bundle","x","--target","t"])
    assert apply_bundle.main()==1
    assert '"apply_allowed": false' in capsys.readouterr().out


def test_conflict_detects_metadata_not_only_content():
    expected=dict(sha256="a"*64,uid=1000,mode=0o100644,inode=4)
    assert preflight.snapshot_differences(expected,dict(expected,mode=0o100600))==["mode"]


def test_absent_does_not_accept_dangling_link(monkeypatch):
    monkeypatch.setattr(preflight.os,"stat",lambda *a,**k:SimpleNamespace(st_mode=stat.S_IFLNK))
    with pytest.raises(ValueError,match="exists"):preflight.require_absent(0,"dangling")


def test_json_private_records_reject_duplicate_keys():
    with pytest.raises(ValueError):safety.json_unique(b'{"targets":{},"targets":{}}')
