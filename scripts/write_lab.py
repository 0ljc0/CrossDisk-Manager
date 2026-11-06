"""Single-file write/restore experiment, confined to a newly created test image.

No existing image, partition, target registration, or bundle can be supplied.
Interrupted runs are retained for inspection; this is not a production executor.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import traceback
import uuid
import zipfile

from app.services.linux_registry import atomic_json
from app.services.linux_safety import (
    ensure, owned_fd, private_directory, open_absolute_directory,
    open_regular, require_linux, snapshot_fd, trusted_command,
)
from scripts.g0_linux_prepare import prepare


def restored_equal(original, restored):
    fields = ("kind", "size", "sha256", "mode", "uid", "gid", "mtime_ns", "nlink")
    return all(original[key] == restored[key] for key in fields)


def publish_new(directory, source, destination):
    require_linux()
    libc = ctypes.CDLL(None, use_errno=True)
    ensure(hasattr(libc, "renameat2"), "renameat2 unavailable; no fallback")
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(directory, source.encode(), directory, destination.encode(), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-disposable-tests", action="store_true", required=True)
    parser.parse_args()
    require_linux()
    with owned_fd(private_directory("/var/lib/crossdisk-manager-write-lab", create=True)):
        pass
    work = Path(tempfile.mkdtemp(prefix="run-", dir="/var/lib/crossdisk-manager-write-lab"))
    token = uuid.uuid4().hex[:12]
    mount = Path("/mnt/crossdisk-write-"+token)
    mount.mkdir(mode=0o700)
    loop, mounted, image = None, False, None
    report = dict(format="crossdisk-write-lab", version=1, tests=[], events=[], production_apply_allowed=False)
    try:
        generated = prepare(work)
        image = generated/"g0.img"
        loop = trusted_command("losetup", "--find", "--show", str(image)).strip()
        trusted_command("mount", "-t", "ext4", "-o", "nosuid,nodev,noexec", loop, str(mount))
        mounted = True
        with owned_fd(open_absolute_directory(str(mount/"g0"))) as target, \
                owned_fd(private_directory(str(work))) as state:
            ensure(os.fstat(target).st_dev != os.fstat(state).st_dev, "Backup must be outside test filesystem")
            def snap(name):
                with owned_fd(open_regular(target,name)) as fd:
                    return snapshot_fd(fd)
            def event(action, status, **details):
                report["events"].append(dict(action=action,status=status,**details))
                atomic_json(state,"journal.json",report)
            def checked(name, condition):
                ensure(condition, "Experiment failed: "+name)
                report["tests"].append(dict(name=name,passed=True))
            def temporary(content, metadata, times=None):
                name=".write-lab-"+uuid.uuid4().hex
                event("temporary","INTENT",name=name)
                fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=target)
                with os.fdopen(fd,"wb") as stream:
                    stream.write(content);stream.flush()
                    os.fchown(stream.fileno(),metadata["uid"],metadata["gid"])
                    os.fchmod(stream.fileno(),stat.S_IMODE(metadata["mode"]))
                    if times is not None: os.utime(stream.fileno(),ns=times)
                    os.fsync(stream.fileno())
                os.fsync(target)
                actual=snap(name)
                checked("temporary-content",actual["sha256"]==hashlib.sha256(content).hexdigest())
                event("temporary","PREPARED",name=name,snapshot=actual)
                return name,actual
            # Fixed fixture created by prepare(); never takes a user file path.
            original=snap("nano-b.txt")
            with owned_fd(open_regular(target,"nano-b.txt")) as fd:
                times=(os.fstat(fd).st_atime_ns,original["mtime_ns"])
                content=os.read(fd,original["size"]+1)
            with (work/"original.bin").open("xb") as backup:
                backup.write(content);backup.flush();os.fsync(backup.fileno())
            checked("backup-hash",hashlib.sha256((work/"original.bin").read_bytes()).hexdigest()==original["sha256"])
            atomic_json(state,"backup.json",dict(path="nano-b.txt",snapshot=original,atime_ns=times[0]))
            os.fsync(state)
            event("replace","BACKUP_READY")
            temp,after=temporary(b"controlled replacement\n",original)
            checked("original-precondition",snap("nano-b.txt")==original)
            event("replace","PREPARED",temporary=temp,expected=original,result=after)
            os.replace(temp,"nano-b.txt",src_dir_fd=target,dst_dir_fd=target);os.fsync(target)
            checked("replace-result",snap("nano-b.txt")==after)
            event("replace","COMMITTED")
            # Prove a mismatched post-state cannot authorize restoration.
            wrong=dict(after,sha256="0"*64)
            checked("restore-conflict-detected",snap("nano-b.txt")!=wrong)
            restore,restored=temporary((work/"original.bin").read_bytes(),original,times)
            ensure(snap("nano-b.txt")==after,"Target changed before restore")
            event("restore","PREPARED",temporary=restore,result=restored)
            os.replace(restore,"nano-b.txt",src_dir_fd=target,dst_dir_fd=target);os.fsync(target)
            checked("restore-content-metadata",restored_equal(original,snap("nano-b.txt")))
            # Hash verification can update atime; restore promised times afterwards.
            with owned_fd(open_regular(target,"nano-b.txt")) as fd:
                os.utime(fd,ns=times);os.fsync(fd)
            event("restore","COMMITTED")
            temp,new=temporary(b"new file\n",original)
            event("create","PREPARED",temporary=temp,result=new)
            publish_new(target,temp,"write-created.txt");os.fsync(target)
            checked("create-result",snap("write-created.txt")==new)
            event("create","COMMITTED")
            duplicate,_=temporary(b"must not overwrite",original)
            try:
                publish_new(target,duplicate,"write-created.txt")
            except FileExistsError:
                checked("no-overwrite",snap("write-created.txt")==new)
            else:
                raise RuntimeError("No-replace unexpectedly overwrote an existing file")
            # Retain the rejected temporary file as evidence; no bulk cleanup.
            event("duplicate-create","REJECTED",temporary=duplicate)
            ensure(snap("write-created.txt")==new,"Created object changed before undo")
            event("undo-create","PREPARED",expected=new)
            os.unlink("write-created.txt",dir_fd=target);os.fsync(target)
            checked("undo-create",not (mount/"g0/write-created.txt").exists())
            event("undo-create","COMMITTED")
            report["happy_path_passed"]=True
    except BaseException as exc:
        report["error"]=str(exc);report["traceback"]=traceback.format_exc()
    finally:
        try:
            if mounted: trusted_command("umount",str(mount))
            if loop: trusted_command("losetup","--detach",loop)
            if image:
                report["e2fsck_output"]=trusted_command("e2fsck","-fn",str(image))
                report["filesystem_check_ok"]=True
        except BaseException as exc:
            report["cleanup_error"]=str(exc)
        report["passed"]=bool(report.get("happy_path_passed") and report.get("filesystem_check_ok")
                              and not report.get("cleanup_error") and not report.get("error"))
        report["limitations"]=["No crash/power-loss recovery validation", "No production apply or resume interface",
                                "Only a newly generated disposable image was used"]
        (work/"write-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        output=Path.cwd()/("CrossDisk_Write_Result_"+token+".zip")
        with zipfile.ZipFile(output,"x",zipfile.ZIP_DEFLATED) as archive:
            archive.write(work/"write-report.json","write-report.json")
            if (work/"journal.json").exists():archive.write(work/"journal.json","journal.json")
            os.fchmod(archive.fp.fileno(),0o644)
        print("RESULT:",output)
        print("WORKSPACE:",work)
        print("LAB:","PASS" if report["passed"] else "FAIL")
    return 0 if report["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
