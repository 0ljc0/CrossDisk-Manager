"""Build a standalone native-Ubuntu executor validation kit."""
import hashlib
import json
from pathlib import Path
import zipfile

FILES=("LICENSE","app/__init__.py","app/core/__init__.py","app/core/bundle.py",
       "app/services/__init__.py","app/services/linux_safety.py","app/services/linux_registry.py",
       "app/services/linux_preflight.py","app/services/linux_file_ops.py","app/services/linux_execution.py",
       "scripts/g0_linux_prepare.py","scripts/write_lab.py","scripts/executor_lab.py",
       "scripts/apply_bundle.py","scripts/recover_bundle.py","scripts/register_target.py",
       "docs/PHASE6_EXECUTOR.md")


def main():
    root=Path(__file__).resolve().parents[1];output=root/"CrossDisk_Executor_Ubuntu_Kit.zip"
    hashes={}
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            raw=(root/name).read_bytes();archive.writestr(name,raw);hashes[name]=hashlib.sha256(raw).hexdigest()
        archive.writestr("SHA256.json",json.dumps(hashes,indent=2))
        archive.writestr("README.txt","Bundle executor validation kit, native Ubuntu Python 3.10+.\n"
            "Extract and open a terminal in this directory:\n\n"
            "sudo python3 -m scripts.executor_lab --run-disposable-tests\n\n"
            "Return CrossDisk_Executor_Result_*.zip, even on FAIL.\n"
            "Only a newly generated loop test image is modified. Physical partitions remain blocked.\n"
            "See docs/PHASE6_EXECUTOR.md for capabilities and recovery limits.\n")
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:raise RuntimeError("Invalid archive")
    print(output)


if __name__=="__main__":main()
