"""Build the IO lab kit with a single experiment entry point."""
import hashlib
import json
from pathlib import Path
import zipfile

FILES=("app/__init__.py","app/core/__init__.py","app/core/bundle.py","app/core/io_failure.py",
       "app/services/__init__.py","app/services/linux_safety.py","app/services/linux_registry.py",
       "scripts/g0_linux_prepare.py","scripts/io_fault_lab.py","docs/PHASE6_IO_FAULT_LAB.md")


def main():
    root=Path(__file__).resolve().parents[1]
    output=root/"CrossDisk_IO_Ubuntu_Kit.zip"
    hashes={}
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            raw=(root/name).read_bytes();archive.writestr(name,raw)
            hashes[name]=hashlib.sha256(raw).hexdigest()
        archive.writestr("SHA256.json",json.dumps(hashes,indent=2))
        archive.writestr("README.txt","IO failure lab, native Ubuntu Python 3.10+.\n"
            "Extract, open a terminal in this directory, then run:\n\n"
            "sudo python3 -m scripts.io_fault_lab --run-disposable-tests\n\n"
            "Return CrossDisk_IO_Result_*.zip. Only new disposable test image is used.\n"
            "Host needs at least 512 MiB free. EIO is software injection.\n"
            "Detailed instructions: docs/PHASE6_IO_FAULT_LAB.md\n")
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:raise RuntimeError("Archive integrity check failed")
    print(output)


if __name__=="__main__":main()
