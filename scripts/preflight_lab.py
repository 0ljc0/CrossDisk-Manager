"""Explicit Ubuntu integration lab. Only formats its own new regular image.

Run from the extracted kit: sudo python3 -m scripts.preflight_lab --run-disposable-tests
Creates fixed registration control files and a unique test registration. No apply exists.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import traceback
import uuid
import zipfile

from app.core.bundle import canonical, validate
from app.services.linux_preflight import preflight
from app.services.linux_registry import policy, register
from app.services.linux_safety import (
    ext4_mount, open_absolute_directory, owned_fd, private_directory, require_linux, trusted_command,
)
from scripts.g0_linux_prepare import prepare, snapshot


def bundle_at(work, name, manifest, payloads):
    folder = work / name
    folder.mkdir(mode=0o700)
    (folder / "files").mkdir(mode=0o700)
    for filename, content in payloads.items():
        (folder / "files" / filename).write_bytes(content)
    # Invalid-input test cases deliberately bypass validate() here.
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return folder


def content_state(root):
    """Known test files plus top-level directory entries; excludes atime."""
    names = ("empty", "nano-a.txt", "nano-b.txt", "hardlink.txt", "large.bin", "中文 空格.txt")
    return dict(files={name: snapshot(root / name) for name in names},
                entries=sorted(p.name for p in root.iterdir()))


def lab():
    require_linux()
    with owned_fd(private_directory("/var/lib/crossdisk-manager-lab", create=True)):
        pass
    token = uuid.uuid4().hex[:12]
    work = Path(tempfile.mkdtemp(prefix="preflight-", dir="/var/lib/crossdisk-manager-lab"))
    mount = Path("/mnt/crossdisk-preflight-" + token)
    mount.mkdir(mode=0o700)  # Exclusive; do not reuse a user mount directory.
    mounted, loop, nested = False, None, False
    results = dict(format="crossdisk-preflight-lab", version=1, linux=platform.platform(),
                   python=platform.python_version(), tests=[], apply_allowed=False, work=str(work))
    generated = None
    try:
        generated = prepare(work)
        image = generated / "g0.img"
        loop = trusted_command("losetup", "--find", "--show", str(image)).strip()
        trusted_command("mount", "-t", "ext4", "-o", "nosuid,nodev,noexec", loop, str(mount))
        mounted = True
        root = mount / "g0"
        # Negative fixtures only; all are inside this lab's new image.
        (root / "linkdir").symlink_to("/etc", target_is_directory=True)
        (root / "cross").mkdir()
        os.mkfifo(root / "fifo", 0o600)
        tagged = root / "tagged.txt"
        tagged.write_bytes(b"tagged")
        os.chown(tagged, 1000, 1000)
        os.chmod(tagged, 0o644)
        os.setxattr(tagged, "user.crossdisk-test", b"test")
        for kind in ("state", "backup", "alias-state", "alias-backup", "foreign"):
            (work / kind).mkdir(mode=0o700)
        with owned_fd(open_absolute_directory(str(mount))) as fd:
            fs_uuid = ext4_mount(fd, exact_path=str(mount))["uuid"]
        target = "lab-" + token
        allowed = policy([1000, 1001], [1000, 1001], [0o600, 0o640, 0o644, 0o750], [0o700, 0o755])
        register(target, str(mount), "g0", str(work/"state"), str(work/"backup"), allowed,
                 str(root), fs_uuid, initialize=True)
        results["target"] = target
        results["filesystem_uuid"] = fs_uuid
        initial = content_state(root)
        payloads = {"new.bin": b"new staged content\n", "replacement.bin": b"replacement staged content\n"}
        def payload(name):
            content = payloads[name]
            return dict(path="files/"+name, size=len(content), sha256=hashlib.sha256(content).hexdigest())
        manifest = dict(format="crossdisk-bundle", version=3, bundle_id="baseline-"+token,
                        target=dict(filesystem="ext4", fs_uuid=fs_uuid, mount_relative_root="g0"),
                        operations=[
                            dict(id="create", type="create_file", path="new.txt", precondition={"target":"absent"},
                                 metadata=dict(uid=1000,gid=1000,mode=0o644), payload=payload("new.bin")),
                            dict(id="replace", type="replace_file", path="nano-b.txt",
                                 precondition=dict(target="matches",object=snapshot(root/"nano-b.txt")),
                                 metadata_policy="preserve_basic", payload=payload("replacement.bin")),
                            dict(id="delete", type="delete_file", path="empty",
                                 precondition=dict(target="matches",object=snapshot(root/"empty"))),
                            dict(id="mkdir", type="mkdir", path="documents", precondition={"target":"absent"},
                                 metadata=dict(uid=1000,gid=1000,mode=0o755)),
                            dict(id="rename", type="rename_file", path="large.bin", new_path="renamed.bin",
                                 source_precondition=snapshot(root/"large.bin"), destination_precondition={"target":"absent"})])
        validate(copy.deepcopy(manifest))

        def attempt(name, value, expected, contents=None, expected_error=None):
            value = copy.deepcopy(value)
            if name not in ("repeat", "id-collision"):
                value["bundle_id"] = name+"-"+token
            location = bundle_at(work, name, value, payloads if contents is None else contents)
            try:
                report = preflight(str(location), target)
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                report = dict(status="PREFLIGHT_REJECTED", error=str(exc), apply_allowed=False)
            actual = report["status"] == "PREFLIGHT_OK"
            unchanged = content_state(root) == initial
            error_text = json.dumps(report)
            ok = actual == expected and unchanged and not report["apply_allowed"]
            if expected_error:
                ok = ok and expected_error in error_text
            results["tests"].append(dict(name=name, passed=ok, target_unchanged=unchanged, report=report))
            print(name + ": " + ("PASS" if ok else "FAIL"), flush=True)

        attempt("baseline", manifest, True)
        # Baseline ID in attempt() matches the original manifest ID.
        attempt("repeat", manifest, True)
        value = copy.deepcopy(manifest)
        value["target"]["fs_uuid"] = "0"*32
        attempt("wrong-uuid", value, False, expected_error="UUID")
        value = copy.deepcopy(manifest)
        value["operations"][1]["precondition"]["object"]["sha256"] = "0"*64
        attempt("changed-content", value, False, expected_error="sha256")
        value = copy.deepcopy(manifest)
        value["operations"][0]["path"] = "nano-a.txt"
        attempt("already-exists", value, False, expected_error="exists")
        value = copy.deepcopy(manifest)
        value["operations"][0]["metadata"]["uid"] = 12345
        attempt("wrong-owner", value, False, expected_error="authorized")
        value = copy.deepcopy(manifest)
        value["operations"][0]["path"] = "linkdir/new.txt"
        attempt("symlink-parent", value, False, expected_error="openat2")
        value = copy.deepcopy(manifest)
        value["operations"][0]["path"] = "missing/new.txt"
        attempt("missing-parent", value, False, expected_error="openat2")
        value = copy.deepcopy(manifest)
        value["operations"][2]["path"] = "nano-a.txt"
        source = snapshot(root/"nano-a.txt")
        source["nlink"] = 1  # Valid schema, but actual object is hard-linked.
        value["operations"][2]["precondition"]["object"] = source
        attempt("hardlink", value, False, expected_error="Hard-linked")
        value = copy.deepcopy(manifest)
        value["operations"][2]["path"] = "fifo"
        attempt("fifo", value, False, expected_error="regular")
        value = copy.deepcopy(manifest)
        value["operations"][2]["path"] = "tagged.txt"
        value["operations"][2]["precondition"]["object"] = snapshot(tagged)
        attempt("xattr", value, False, expected_error="xattr")
        attempt("corrupt-payload", manifest, False, dict(payloads, **{"new.bin":b"wrong"}), expected_error="Payload")
        trusted_command("mount", "--bind", str(work/"foreign"), str(root/"cross"))
        nested = True
        value = copy.deepcopy(manifest)
        value["operations"][0]["path"] = "cross/new.txt"
        attempt("cross-mount", value, False, expected_error="openat2")
        trusted_command("umount", str(root/"cross"))
        nested = False
        # Once a bundle ID is bound, a different manifest must be rejected.
        value = copy.deepcopy(manifest)
        value["operations"][0]["metadata"]["mode"] = 0o600
        attempt("id-collision", value, False, expected_error="another manifest")
        results["target_unchanged"] = content_state(root) == initial
        os.sync()
    except BaseException as exc:
        results["fatal_error"] = str(exc)
        results["traceback"] = traceback.format_exc()
        if isinstance(exc, subprocess.CalledProcessError):
            results["tool_stderr"] = exc.stderr
    finally:
        try:
            if nested:
                trusted_command("umount", str(mount/"g0/cross"))
            if mounted:
                trusted_command("umount", str(mount))
                mounted = False
            if loop:
                trusted_command("losetup", "--detach", loop)
                loop = None
            if generated is not None:
                # No repairs: a nonzero check result is a lab failure.
                output = trusted_command("e2fsck", "-fn", str(generated/"g0.img"))
                results["filesystem_check_ok"] = True
                results["filesystem_check_output"] = output
        except BaseException as exc:
            results["cleanup_error"] = str(exc)
            results["mounted_may_remain"] = str(mount)
        results["passed"] = (not results.get("fatal_error") and not results.get("cleanup_error")
                             and bool(results["tests"]) and all(t["passed"] for t in results["tests"]))
        results["registration_note"] = "Test registration retained; unmount invalidates it. No target write was applied."
        (work/"lab-report.json").write_text(json.dumps(results,ensure_ascii=True,indent=2),encoding="utf-8")
        export = Path.cwd() / ("CrossDisk_Preflight_Result_"+token+".zip")
        with zipfile.ZipFile(export,"x",zipfile.ZIP_DEFLATED) as archive:
            archive.write(work/"lab-report.json","lab-report.json")
            os.fchmod(archive.fp.fileno(),0o644)
        print("RESULT ZIP:",export,flush=True)
        print("RETAINED WORKSPACE:",work,flush=True)
        print("LAB:","PASS" if results["passed"] else "FAIL",flush=True)
    return 0 if results["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-disposable-tests",action="store_true",required=True)
    parser.parse_args()
    return lab()


if __name__ == "__main__":
    raise SystemExit(main())
