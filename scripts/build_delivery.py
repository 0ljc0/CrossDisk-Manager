"""Combine already-tested Windows and Ubuntu tools into a checksummed local delivery."""
import hashlib
import json
from pathlib import Path
import zipfile
from app.core.version import VERSION


def main():
    root=Path(__file__).resolve().parents[1]
    windows=root/f"dist/CrossDiskManager-{VERSION}-windows-x64.zip"
    ubuntu=root/"CrossDisk_Executor_Ubuntu_Kit.zip"
    report=root/f"docs/FROZEN_SMOKE_{VERSION}.json"
    evidence=json.loads(report.read_text(encoding="utf-8"))
    exe=root/"dist/CrossDiskManager/CrossDiskManager.exe"
    if evidence["version"]!=VERSION or evidence["executable_sha256"]!=hashlib.sha256(exe.read_bytes()).hexdigest():
        raise RuntimeError("Frozen smoke evidence does not match this executable")
    files={windows.name:windows,ubuntu.name:ubuntu,"QUICK_START_CN.md":root/"QUICK_START_CN.md",
           "FROZEN_SMOKE.json":report,"RELEASE_NOTES.md":root/"docs/RELEASE_RC2.md"}
    hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}
    output=root/f"dist/CrossDiskManager-{VERSION}-delivery.zip"
    manifest=dict(version=VERSION,files=hashes,unsigned=True,physical_ext4_apply_allowed=False)
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as archive:
        for name,path in files.items():archive.write(path,name)
        archive.writestr("SHA256.json",json.dumps(manifest,indent=2))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:raise RuntimeError("Delivery CRC failed")
        for name,digest in hashes.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest:raise RuntimeError("Delivery file mismatch")
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(digest+"  "+output.name+"\n",encoding="ascii")
    print(json.dumps(dict(output=str(output),bytes=output.stat().st_size,sha256=digest),indent=2))


if __name__=="__main__":main()
