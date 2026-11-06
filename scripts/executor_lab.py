"""End-to-end CLI validation on a newly created disposable ext4 image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import uuid
import zipfile

from app.services.linux_registry import register, policy
from app.services.linux_safety import (require_linux, private_directory, owned_fd, open_absolute_directory,
    ext4_mount, trusted_command, ensure)
from scripts.g0_linux_prepare import prepare, snapshot
from scripts.write_lab import restored_equal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-disposable-tests",action="store_true",required=True)
    parser.parse_args();require_linux()
    with owned_fd(private_directory("/var/lib/crossdisk-manager-executor-lab",create=True)):pass
    work=Path(tempfile.mkdtemp(prefix="run-",dir="/var/lib/crossdisk-manager-executor-lab"))
    token=uuid.uuid4().hex[:12];target="exec-"+token
    mount=Path("/mnt/crossdisk-executor-"+token);mount.mkdir(mode=0o700)
    image=None;loop=None;mounted=False
    report=dict(format="crossdisk-executor-lab",version=1,tests=[],physical_partition_apply_allowed=False)
    def checked(name,condition,details=None):
        ensure(condition,"End-to-end assertion failed: "+name)
        report["tests"].append(dict(name=name,passed=True,details=details))
        print(name+": PASS",flush=True)
    def cli(module,*args,success=True):
        result=subprocess.run([sys.executable,"-m",module,*args],capture_output=True,text=True,timeout=120)
        value=json.loads(result.stdout)
        ensure((result.returncode==0)==success,module+" unexpected exit: "+result.stdout+result.stderr)
        return value
    try:
        image=prepare(work)/"g0.img"
        loop=trusted_command("losetup","--find","--show",str(image)).strip()
        trusted_command("mount","-t","ext4","-o","nosuid,nodev,noexec",loop,str(mount));mounted=True
        root=mount/"g0"
        for name in ("state","backup"):(work/name).mkdir(mode=0o700)
        with owned_fd(open_absolute_directory(str(mount))) as fd:fs_uuid=ext4_mount(fd,exact_path=str(mount))["uuid"]
        register(target,str(mount),"g0",str(work/"state"),str(work/"backup"),
                 policy([1000,1001],[1000,1001],[0o600,0o640,0o644,0o750],[0o700,0o755]),
                 str(root),fs_uuid,initialize=True,enable_bundle_apply=True)
        confirmations=("--confirm-uuid",fs_uuid,"--confirm-maintenance-window")
        def make_bundle(label):
            folder=work/label;folder.mkdir();(folder/"files").mkdir()
            def payload(name,data):
                (folder/"files"/name).write_bytes(data)
                return dict(path="files/"+name,size=len(data),sha256=hashlib.sha256(data).hexdigest())
            originals={name:snapshot(root/name) for name in ("empty","nano-b.txt","large.bin")}
            manifest=dict(format="crossdisk-bundle",version=3,bundle_id=label+"-"+token,
                target=dict(filesystem="ext4",fs_uuid=fs_uuid,mount_relative_root="g0"),operations=[
                dict(id="create",type="create_file",path="created.txt",precondition={"target":"absent"},
                     payload=payload("create.bin",("created-"+label).encode()),metadata=dict(uid=1000,gid=1000,mode=0o644)),
                dict(id="replace",type="replace_file",path="nano-b.txt",precondition=dict(target="matches",object=originals["nano-b.txt"]),
                     payload=payload("replace.bin",("replacement-"+label).encode()),metadata_policy="preserve_basic"),
                dict(id="delete",type="delete_file",path="empty",precondition=dict(target="matches",object=originals["empty"])),
                dict(id="mkdir",type="mkdir",path="created-dir",precondition={"target":"absent"},metadata=dict(uid=1000,gid=1000,mode=0o755)),
                dict(id="rename",type="rename_file",path="large.bin",new_path="large-renamed.bin",
                     source_precondition=originals["large.bin"],destination_precondition={"target":"absent"})])
            (folder/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
            return folder,manifest,originals
        def recovery(bundle_id,mode,plan=None):
            arguments=["--target",target,"--bundle-id",bundle_id,"--"+mode]
            if mode!="check":arguments += ["--confirm-plan",plan["plan_sha256"],*confirmations]
            return cli("scripts.recover_bundle",*arguments)
        def assert_restored(originals):
            return (all(restored_equal(value,snapshot(root/name)) for name,value in originals.items())
                    and not (root/"created.txt").exists() and not (root/"created-dir").exists()
                    and not (root/"large-renamed.bin").exists())
        folder,manifest,originals=make_bundle("normal")
        value=cli("scripts.apply_bundle","--bundle",str(folder),"--target",target)
        checked("default-is-preflight",value["status"]=="PREFLIGHT_OK" and assert_restored(originals))
        value=cli("scripts.apply_bundle","--bundle",str(folder),"--target",target,"--apply",
                  "--confirm-uuid","0"*32,"--confirm-maintenance-window",success=False)
        checked("wrong-confirmation-rejected",assert_restored(originals),value)
        value=cli("scripts.apply_bundle","--bundle",str(folder),"--target",target,"--apply",*confirmations)
        checked("five-operation-apply",value["status"]=="COMPLETED" and not (root/"empty").exists()
                and (root/"created-dir").is_dir() and (root/"large-renamed.bin").exists(),value)
        value=cli("scripts.apply_bundle","--bundle",str(folder),"--target",target,"--apply",*confirmations)
        checked("repeat-does-not-reapply",value.get("repeated") is True and value["target_modified"] is False)
        plan=recovery(manifest["bundle_id"],"check")
        checked("completed-check",all(o["result"]=="COMMITTED" for o in plan["observations"]),plan)
        value=recovery(manifest["bundle_id"],"rollback",plan)
        checked("five-operation-rollback",value["status"]=="ROLLED_BACK" and assert_restored(originals),value)
        value=cli("scripts.apply_bundle","--bundle",str(folder),"--target",target,"--apply",*confirmations)
        checked("rolled-back-id-not-replayed",value["status"]=="ROLLED_BACK" and not value["target_modified"] and assert_restored(originals))
        folder,manifest,originals=make_bundle("interrupted")
        pid=os.fork()
        if pid==0:
            try:
                from app.services import linux_execution
                original_save=linux_execution.Run.save
                def crash_before_commit_log(self,event):
                    if event=="operation-committed":os._exit(95)
                    return original_save(self,event)
                linux_execution.Run.save=crash_before_commit_log
                linux_execution.apply(str(folder),target,fs_uuid)
            except BaseException:os._exit(99)
            os._exit(98)
        _,status=os.waitpid(pid,0)
        checked("process-exit-injection",os.waitstatus_to_exitcode(status)==95)
        plan=recovery(manifest["bundle_id"],"check")
        checked("prepared-publication-detected",plan["observations"][0]["result"]=="COMMITTED"
                and all(o["result"]=="PENDING" for o in plan["observations"][1:]),plan)
        value=recovery(manifest["bundle_id"],"resume",plan)
        checked("explicit-resume",value["status"]=="COMPLETED",value)
        plan=recovery(manifest["bundle_id"],"check")
        value=recovery(manifest["bundle_id"],"rollback",plan)
        checked("rollback-after-resume",value["status"]=="ROLLED_BACK" and assert_restored(originals),value)
    except BaseException as exc:
        report["error"]=str(exc);report["traceback"]=traceback.format_exc()
    finally:
        try:
            if mounted:trusted_command("umount",str(mount))
            if loop:trusted_command("losetup","--detach",loop)
            if image:
                report["e2fsck_output"]=trusted_command("e2fsck","-fn",str(image));report["filesystem_check_ok"]=True
        except BaseException as exc:report["cleanup_error"]=str(exc)
        report["passed"]=bool(len(report["tests"])==11 and report.get("filesystem_check_ok")
                              and not report.get("error") and not report.get("cleanup_error"))
        report["limitations"]=["Loop test images only", "No power-loss validation", "Native results require review"]
        (work/"executor-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        output=Path.cwd()/("CrossDisk_Executor_Result_"+token+".zip")
        with zipfile.ZipFile(output,"x",zipfile.ZIP_DEFLATED) as archive:
            archive.write(work/"executor-report.json","executor-report.json")
            for directory in (work/"state",work/"backup"):
                if directory.exists():
                    for source in directory.rglob("*.json"):
                        if source.is_file() and not source.is_symlink():archive.write(source,str(source.relative_to(work)))
            os.fchmod(archive.fp.fileno(),0o644)
        print("RESULT:",output);print("WORKSPACE:",work);print("LAB:","PASS" if report["passed"] else "FAIL")
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
