"""Abrupt child-exit recovery lab; accepts no existing image or target."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import traceback
import uuid
import zipfile

from app.core.recovery import classify_replace, classify_evidence
from app.services.linux_registry import atomic_json, read_private_json
from app.services.linux_safety import (ensure, owned_fd, private_directory, open_absolute_directory,
    open_regular, require_linux, snapshot_fd, trusted_command)
from scripts.g0_linux_prepare import prepare
from scripts.write_lab import restored_equal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-disposable-tests",action="store_true",required=True)
    parser.parse_args()
    require_linux()
    with owned_fd(private_directory("/var/lib/crossdisk-manager-recovery-lab",create=True)): pass
    work=Path(tempfile.mkdtemp(prefix="run-",dir="/var/lib/crossdisk-manager-recovery-lab"))
    token=uuid.uuid4().hex[:12]
    mount=Path("/mnt/crossdisk-recovery-"+token);mount.mkdir(mode=0o700)
    loop=None;mounted=False;image=None
    report=dict(format="crossdisk-recovery-lab",version=2,cases=[],production_apply_allowed=False)
    try:
        image=prepare(work)/"g0.img"
        loop=trusted_command("losetup","--find","--show",str(image)).strip()
        trusted_command("mount","-t","ext4","-o","nosuid,nodev,noexec",loop,str(mount));mounted=True
        with owned_fd(open_absolute_directory(str(mount/"g0"))) as target:
            def snap(name):
                try:
                    with owned_fd(open_regular(target,name)) as fd: return snapshot_fd(fd)
                except FileNotFoundError: return None
            def make_temp(data,meta,restore=False):
                name=".recover-"+uuid.uuid4().hex
                fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=target)
                with os.fdopen(fd,"wb") as stream:
                    stream.write(data);stream.flush()
                    os.fchown(stream.fileno(),meta["uid"],meta["gid"])
                    os.fchmod(stream.fileno(),stat.S_IMODE(meta["mode"]))
                    if restore: os.utime(stream.fileno(),ns=(meta["mtime_ns"],meta["mtime_ns"]))
                    os.fsync(stream.fileno())
                os.fsync(target)
                ensure(snap(name)["sha256"]==hashlib.sha256(data).hexdigest(),"Temporary hash mismatch")
                return name
            for checkpoint,exitcode in (("before-publish",91),("after-publish-before-log",92)):
                folder=work/checkpoint;folder.mkdir(mode=0o700)
                with owned_fd(private_directory(str(folder))) as state:
                    ensure(os.fstat(state).st_dev!=os.fstat(target).st_dev,"External backup required")
                    original=snap("nano-b.txt")
                    with owned_fd(open_regular(target,"nano-b.txt")) as source:
                        old=os.read(source,original["size"]+1)
                    fd=os.open("original.bin",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=state)
                    with os.fdopen(fd,"wb") as stream:
                        stream.write(old);stream.flush();os.fsync(stream.fileno())
                    atomic_json(state,"backup.json",original);os.fsync(state)
                    pid=os.fork()
                    if pid==0:
                        try:
                            name=make_temp(b"replacement for recovery lab\n",original)
                            record=dict(status="PREPARED",before=original,after=snap(name),temporary=name)
                            atomic_json(state,"prepared.json",record)
                            ensure(snap("nano-b.txt")==original,"Source changed")
                            if exitcode==91: os._exit(91)
                            os.replace(name,"nano-b.txt",src_dir_fd=target,dst_dir_fd=target)
                            os.fsync(target)
                            os._exit(92) # No COMMITTED log and no Python cleanup.
                        except BaseException:
                            os._exit(99)
                    _,status=os.waitpid(pid,0)
                    actual_exit=os.waitstatus_to_exitcode(status)
                    ensure(actual_exit==exitcode,"Child did not reach injection point")
                    record=read_private_json(state,"prepared.json")
                    backup=read_private_json(state,"backup.json")
                    with owned_fd(open_regular(state,"original.bin")) as fd:
                        backup_bytes=os.read(fd,backup["size"]+1)
                    valid=(backup==record["before"] and len(backup_bytes)==backup["size"]
                           and hashlib.sha256(backup_bytes).hexdigest()==backup["sha256"])
                    current=snap("nano-b.txt");temporary=snap(record["temporary"])
                    decision=classify_replace(record,current,temporary,backup_valid=valid)
                    expected="NOT_COMMITTED" if exitcode==91 else "COMMITTED"
                    ensure(decision==expected,"Recovery classification mismatch")
                    ensure(classify_replace(record,current,temporary,backup_valid=False)=="UNKNOWN","Bad backup accepted")
                    changed=dict(current,sha256="0"*64)
                    ensure(classify_replace(record,changed,temporary,backup_valid=valid)=="UNKNOWN","Conflicting target accepted")
                    atomic_json(state,"check.json",dict(decision=decision,current=current,temporary=temporary))
                    if decision=="NOT_COMMITTED":
                        ensure(snap("nano-b.txt")==record["before"] and snap(record["temporary"])==record["after"],"Resume conflict")
                        atomic_json(state,"resume.json",dict(status="PREPARED",record=record))
                        os.replace(record["temporary"],"nano-b.txt",src_dir_fd=target,dst_dir_fd=target);os.fsync(target)
                    ensure(snap("nano-b.txt")==record["after"],"Committed result mismatch")
                    atomic_json(state,"resume.json",dict(status="COMMITTED",record=record))
                    restored=make_temp(backup_bytes,backup,restore=True)
                    rollback=dict(status="PREPARED",temporary=restored,before=record["after"],after=snap(restored))
                    atomic_json(state,"rollback-prepared.json",rollback)
                    raw=(folder/"rollback-prepared.json").read_bytes()
                    anchor=hashlib.sha256(raw).hexdigest()
                    atomic_json(state,"rollback-anchor.json",dict(sha256=anchor))
                    rollback_exit=93 if exitcode==91 else 94
                    pid=os.fork()
                    if pid==0:
                        try:
                            ensure(snap("nano-b.txt")==rollback["before"] and snap(restored)==rollback["after"],"Rollback conflict")
                            if rollback_exit==93:os._exit(93)
                            os.replace(restored,"nano-b.txt",src_dir_fd=target,dst_dir_fd=target);os.fsync(target)
                            os._exit(94)
                        except BaseException:os._exit(99)
                    _,status=os.waitpid(pid,0)
                    ensure(os.waitstatus_to_exitcode(status)==rollback_exit,"Rollback injection point missed")
                    raw=(folder/"rollback-prepared.json").read_bytes()
                    anchor=read_private_json(state,"rollback-anchor.json")["sha256"]
                    with owned_fd(open_regular(state,"original.bin")) as fd:backup_bytes=os.read(fd,backup["size"]+1)
                    current=snap("nano-b.txt");remaining=snap(restored)
                    rollback_decision=classify_evidence(raw,anchor,current,remaining,backup_bytes,backup)
                    ensure(rollback_decision==("NOT_COMMITTED" if rollback_exit==93 else "COMMITTED"),"Rollback recovery mismatch")
                    evidence_checks=[]
                    # Write and reread damaged evidence copies, preserving original records.
                    for bad_name,bad_raw in (("truncated.json",raw[:len(raw)//2]),("changed.json",raw+b" ")):
                        fd=os.open(bad_name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=state)
                        with os.fdopen(fd,"wb") as stream:stream.write(bad_raw);stream.flush();os.fsync(stream.fileno())
                        rejected=classify_evidence((folder/bad_name).read_bytes(),anchor,current,remaining,backup_bytes,backup)
                        ensure(rejected=="UNKNOWN","Damaged record accepted");evidence_checks.append(bad_name)
                    for bad_backup in (None,backup_bytes+b"corruption"):
                        ensure(classify_evidence(raw,anchor,current,remaining,bad_backup,backup)=="UNKNOWN","Missing/corrupt backup accepted")
                    evidence_checks.extend(["missing-backup","corrupt-backup"])
                    atomic_json(state,"rollback-check.json",dict(decision=rollback_decision,negative_checks=evidence_checks))
                    if rollback_decision=="NOT_COMMITTED":
                        ensure(snap("nano-b.txt")==rollback["before"] and snap(restored)==rollback["after"],"Rollback resume conflict")
                        os.replace(restored,"nano-b.txt",src_dir_fd=target,dst_dir_fd=target);os.fsync(target)
                    ensure(restored_equal(backup,snap("nano-b.txt")),"Rollback mismatch")
                    atomic_json(state,"rollback.json",dict(status="COMMITTED"))
                    report["cases"].append(dict(checkpoint=checkpoint,child_exit=actual_exit,decision=decision,
                        rollback_child_exit=rollback_exit,rollback_decision=rollback_decision,evidence_checks=evidence_checks,
                        passed=True,backup_checked=True,unknown_checks_passed=True,restored=snap("nano-b.txt")))
    except BaseException as exc:
        report["error"]=str(exc);report["traceback"]=traceback.format_exc()
    finally:
        try:
            if mounted: trusted_command("umount",str(mount))
            if loop: trusted_command("losetup","--detach",loop)
            if image:
                report["e2fsck_output"]=trusted_command("e2fsck","-fn",str(image));report["filesystem_check_ok"]=True
        except BaseException as exc: report["cleanup_error"]=str(exc)
        report["passed"]=bool(len(report["cases"])==2 and report.get("filesystem_check_ok")
                              and not report.get("error") and not report.get("cleanup_error"))
        report["limitations"]=["Process-exit injection, not power loss", "No production recovery CLI",
            "No ENOSPC/EIO or non-cooperating concurrent writer test", "atime restoration is not checked"]
        (work/"recovery-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        output=Path.cwd()/("CrossDisk_Recovery_Result_"+token+".zip")
        with zipfile.ZipFile(output,"x",zipfile.ZIP_DEFLATED) as archive:
            archive.write(work/"recovery-report.json","recovery-report.json")
            for folder in ("before-publish","after-publish-before-log"):
                if (work/folder).exists():
                    for source in (work/folder).glob("*.json"):archive.write(source,folder+"/"+source.name)
            os.fchmod(archive.fp.fileno(),0o644)
        print("RESULT:",output);print("WORKSPACE:",work);print("LAB:","PASS" if report["passed"] else "FAIL")
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
