"""Build a minimal, standard-library-only Ubuntu preflight test kit."""
import hashlib
import json
from pathlib import Path
import zipfile


FILES = (
    "app/__init__.py", "app/core/__init__.py", "app/core/bundle.py",
    "app/services/__init__.py", "app/services/linux_safety.py",
    "app/services/linux_registry.py", "app/services/linux_preflight.py",
    "scripts/register_target.py", "scripts/apply_bundle.py", "scripts/preflight_lab.py",
    "scripts/g0_linux_prepare.py", "docs/PHASE6_LINUX_PREFLIGHT.md",
)


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "CrossDisk_Preflight_Ubuntu_Kit.zip"
    hashes = {}
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            content = (root/name).read_bytes()
            archive.writestr(name, content)
            hashes[name] = hashlib.sha256(content).hexdigest()
        archive.writestr("SHA256.json", json.dumps(hashes, sort_keys=True, indent=2))
        archive.writestr("README.txt", (
            "Ubuntu 22.04 preflight-only test kit (Python 3.10+).\n"
            "Extract to a local Ubuntu directory. Open a terminal there and run:\n\n"
            "sudo python3 -m scripts.preflight_lab --run-disposable-tests\n\n"
            "Creates its own disposable image and a root-managed test registration.\n"
            "No actual bundle apply is implemented. Existing user files are not targets.\n"
            "Return CrossDisk_Preflight_Result_*.zip from this folder to Windows, even on FAIL.\n"
            "Detailed instructions: docs/PHASE6_LINUX_PREFLIGHT.md\n"
            "Windows unit tests do not substitute for this native Linux integration run.\n"
        ))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Corrupt output archive")
    print(output)
    print(hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
