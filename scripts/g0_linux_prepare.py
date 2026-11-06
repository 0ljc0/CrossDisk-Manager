"""Ubuntu-only disposable ext4 image and independent truth collector (Python 3.10+)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import tempfile


def digest(stream):
    value = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        value.update(chunk)
    return value.hexdigest()


def snapshot(path):
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        value = digest(stream)
        after = os.fstat(stream.fileno())
    fields = ("st_mode", "st_size", "st_uid", "st_gid", "st_mtime_ns", "st_nlink", "st_ino", "st_ctime_ns")
    if not stat.S_ISREG(before.st_mode) or any(getattr(before,k)!=getattr(after,k) for k in fields):
        raise RuntimeError("Sample changed while reading")
    return dict(kind="regular_file",size=before.st_size,sha256=value,mode=before.st_mode,
                uid=before.st_uid,gid=before.st_gid,mtime_ns=before.st_mtime_ns,
                nlink=before.st_nlink,inode=before.st_ino)


def run(*args):
    return subprocess.run(args,check=True,text=True,capture_output=True).stdout.strip()


def prepare(output):
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise RuntimeError("Run with sudo in Ubuntu")
    for tool in ("mkfs.ext4", "mount", "umount", "losetup", "e2fsck"):
        if not shutil.which(tool):
            raise RuntimeError("Missing tool: " + tool)
    # A fresh exclusive root-owned workspace; never accept an existing image or device.
    work = Path(tempfile.mkdtemp(prefix="crossdisk-g0-",dir=output.resolve()))
    image, mount = work/"g0.img", work/"mnt"
    mount.mkdir()
    with image.open("xb") as stream:
        stream.truncate(128*1024*1024)
    loop, mounted = None, False
    try:
        mkfs = run("mkfs.ext4","-F","-L","CDM-G0",str(image))
        loop = run("losetup","--find","--show",str(image))
        run("mount","-t","ext4","-o","nosuid,nodev,noexec",loop,str(mount))
        mounted = True
        root = mount/"g0"
        root.mkdir()
        cases = [("nano-a.txt",b"alpha",1000,1001,0o640,123456789),
                 ("nano-b.txt",b"beta",1001,1000,0o750,987654321),
                 ("empty",b"",1000,1000,0o600,0),
                 ("中文 空格.txt","测试\n".encode(),1000,1000,0o644,123456789),
                 ("large.bin",bytes(range(256))*65536,1000,1000,0o640,987654321)]
        for name,data,uid,gid,mode,nanos in cases:
            path=root/name
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fchown(stream.fileno(),uid,gid)
                os.fchmod(stream.fileno(),mode)
                os.utime(stream.fileno(),ns=(1700000000*10**9+nanos,)*2)
                os.fsync(stream.fileno())
        os.link(root/"nano-a.txt",root/"hardlink.txt")
        files={"g0/"+p.name:snapshot(p) for p in sorted(root.iterdir())}
        os.sync()
        run("umount",str(mount))
        mounted=False
        run("losetup","--detach",loop)
        loop=None
        check=subprocess.run(["e2fsck","-fn",str(image)],text=True,capture_output=True)
        (work/"e2fsck.txt").write_text(check.stdout+check.stderr,encoding="utf-8")
        if check.returncode != 0:
            raise RuntimeError("Filesystem check failed; keep workspace for diagnosis")
        with image.open("rb") as stream:
            image_hash=digest(stream)
        report=dict(format="crossdisk-g0-truth",version=1,linux=platform.platform(),
                    python=platform.python_version(),image_sha256=image_hash,files=files,
                    filesystem_check_exit=check.returncode,mkfs_output=mkfs)
        (work/"truth.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        for path in (image,work/"truth.json",work/"e2fsck.txt"):
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        os.sync()
        print("READY (unmounted):",work)
        return work
    finally:
        # If unmount fails, do not detach or remove anything; report the retained workspace.
        print("Workspace retained:",work)
        if mounted:
            run("umount",str(mount))
        if loop:
            run("losetup","--detach",loop)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-parent",type=Path,required=True)
    args=parser.parse_args()
    prepare(args.output_parent)

if __name__ == "__main__":
    main()
