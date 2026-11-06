"""New-image-only ENOSPC and controlled EIO injection experiment."""
import argparse
import errno
import hashlib
import json
import os
import shutil
from pathlib import Path
import tempfile
import traceback
import uuid
import zipfile

from app.core.io_failure import disposition
from app.services.linux_registry import atomic_json
from app.services.linux_safety import (ensure, owned_fd, private_directory, open_absolute_directory,
    open_regular, require_linux, snapshot_fd, trusted_command)
from scripts.g0_linux_prepare import prepare


def injected(point, selected):
    if point == selected:
        raise OSError(errno.EIO, "Controlled EIO injection: "+point)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-disposable-tests",action="store_true",required=True)
    parser.parse_args()
    require_linux()
    with owned_fd(private_directory("/var/lib/crossdisk-manager-io-lab",create=True)):pass
    work=Path(tempfile.mkdtemp(prefix="run-",dir="/var/lib/crossdisk-manager-io-lab"))
    token=uuid.uuid4().hex[:12]
    mount=Path("/mnt/crossdisk-io-"+token);mount.mkdir(mode=0o700)
    image=None;loop=None;mounted=False
    report=dict(format="crossdisk-io-fault-lab",version=1,cases=[],production_apply_allowed=False)
    try:
        ensure(shutil.disk_usage(work).free>=512*1024*1024,"Host needs 512 MiB free before this experiment")
        image=prepare(work)/"g0.img"
        loop=trusted_command("losetup","--find","--show",str(image)).strip()
        trusted_command("mount","-t","ext4","-o","nosuid,nodev,noexec",loop,str(mount));mounted=True
        with owned_fd(open_absolute_directory(str(mount/"g0"))) as target, \
                owned_fd(private_directory(str(work))) as state:
            ensure(os.fstat(target).st_dev!=os.fstat(state).st_dev,"External state required")
            def snap(name):
                with owned_fd(open_regular(target,name)) as fd:return snapshot_fd(fd)
            def create(name,data,sync_fault=None):
                fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=target)
                with os.fdopen(fd,"wb") as stream:
                    stream.write(data);stream.flush()
                    os.fchown(stream.fileno(),1000,1000);os.fchmod(stream.fileno(),0o600)
                    injected("temporary-fsync",sync_fault)
                    os.fsync(stream.fileno())
                os.fsync(target)
            # A real ENOSPC is confined to this fresh 128 MiB image, never the host.
            create("space-victim",b"original space victim")
            before=snap("space-victim")
            filler=".filler-"+uuid.uuid4().hex
            fd=os.open(filler,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=target)
            filler_identity=(os.fstat(fd).st_dev,os.fstat(fd).st_ino)
            filled=0;space_error=None
            try:
                chunk=b"x"*(1024*1024)
                while filled <= 2*image.stat().st_size:
                    filled+=os.write(fd,chunk)
                raise RuntimeError("Image did not become full within bounded allocation")
            except OSError as exc:
                ensure(exc.errno==errno.ENOSPC,"Unexpected error while filling test image")
                space_error=exc
            finally:os.close(fd)
            failure=disposition(space_error,publication_attempted=False)
            try:
                create("enospc-temporary",b"y"*(1024*1024))
            except OSError as exc:
                ensure(exc.errno==errno.ENOSPC,"Expected ENOSPC during replacement staging")
            else:raise RuntimeError("Replacement staging unexpectedly succeeded on full image")
            ensure(snap("space-victim")==before,"Original changed on ENOSPC")
            report["cases"].append(dict(name="real-image-enospc",passed=True,bytes_filled=filled,
                original_unchanged=True,scope="Allocation failure in disposable image",**failure))
            atomic_json(state,"enospc.json",report["cases"][-1])
            # Remove only the exclusive filler after checking its recorded identity.
            info=os.stat(filler,dir_fd=target,follow_symlinks=False)
            ensure((info.st_dev,info.st_ino)==filler_identity,"Filler identity changed")
            os.unlink(filler,dir_fd=target);os.fsync(target)
            for point in ("backup-read","backup-fsync","temporary-fsync","prepared-log","parent-fsync","committed-log"):
                victim="victim-"+point;temporary="temporary-"+point
                create(victim,b"original "+point.encode())
                before=snap(victim)
                publication=False;later_operations=0;expected_after=None
                try:
                    injected("backup-read",point)
                    with owned_fd(open_regular(target,victim)) as source:data=os.read(source,before["size"]+1)
                    fd=os.open(point+".backup",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=state)
                    with os.fdopen(fd,"wb") as backup:
                        backup.write(data);backup.flush();injected("backup-fsync",point);os.fsync(backup.fileno())
                    ensure(hashlib.sha256((work/(point+".backup")).read_bytes()).hexdigest()==before["sha256"],"Backup hash mismatch")
                    atomic_json(state,point+"-backup.json",before);os.fsync(state)
                    create(temporary,b"replacement "+point.encode(),point)
                    expected_after=snap(temporary)
                    injected("prepared-log",point)
                    atomic_json(state,point+"-prepared.json",dict(before=before,after=expected_after,temporary=temporary))
                    ensure(snap(victim)==before,"Source changed before publication")
                    publication=True
                    os.replace(temporary,victim,src_dir_fd=target,dst_dir_fd=target)
                    injected("parent-fsync",point);os.fsync(target)
                    injected("committed-log",point)
                    atomic_json(state,point+"-committed.json",dict(status="COMMITTED"))
                    later_operations+=1
                except OSError as exc:
                    ensure(exc.errno==errno.EIO,"Unexpected exception instead of injected EIO")
                    failure=disposition(exc,publication_attempted=publication)
                    current=snap(victim)
                    ensure(later_operations==0,"Execution continued after failure")
                    ensure(current==(expected_after if publication else before),"Unexpected file state")
                    ensure(failure["status"]==("NEEDS_RECOVERY" if publication else "FAILED_STOPPED"),"Wrong failure disposition")
                    result=dict(name=point,passed=True,injection="software EIO",publication_attempted=publication,
                        original_unchanged=current==before,later_operations=later_operations,observed=current,**failure)
                    report["cases"].append(result);atomic_json(state,point+"-failure.json",result)
                else:raise RuntimeError("Injection point was not reached")
    except BaseException as exc:
        report["error"]=str(exc);report["traceback"]=traceback.format_exc()
    finally:
        try:
            if mounted:trusted_command("umount",str(mount))
            if loop:trusted_command("losetup","--detach",loop)
            if image:
                report["e2fsck_output"]=trusted_command("e2fsck","-fn",str(image));report["filesystem_check_ok"]=True
        except BaseException as exc:report["cleanup_error"]=str(exc)
        report["passed"]=bool(len(report["cases"])==7 and report.get("filesystem_check_ok")
            and not report.get("error") and not report.get("cleanup_error"))
        report["limitations"]=["EIO is software injection, not physical-device failure",
            "ENOSPC tests image allocation, not backup-volume exhaustion", "No power loss or production executor",
            "Post-publication NEEDS_RECOVERY files remain in retained test image"]
        (work/"io-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        output=Path.cwd()/("CrossDisk_IO_Result_"+token+".zip")
        with zipfile.ZipFile(output,"x",zipfile.ZIP_DEFLATED) as archive:
            for source in work.glob("*.json"):archive.write(source,source.name)
            os.fchmod(archive.fp.fileno(),0o644)
        print("RESULT:",output);print("WORKSPACE:",work);print("LAB:","PASS" if report["passed"] else "FAIL")
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
