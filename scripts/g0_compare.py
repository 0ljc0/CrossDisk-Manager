"""Read-only comparison against a Linux truth report; never grants write access."""
import argparse
from dataclasses import asdict
import hashlib
import json
import platform
from pathlib import Path
import pytsk3
from app.backends.ext4_readonly import Ext4ReadOnlyBackend
from app.services.file_snapshot import read_snapshot

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",required=True)
    parser.add_argument("--truth",required=True)
    args=parser.parse_args()
    image=Path(args.image)
    if not image.is_file() or str(image).startswith(("\\\\.\\", "\\\\?\\")):
        parser.error("Only ordinary image files are supported")
    truth=json.loads(Path(args.truth).read_text(encoding="utf-8"))
    def image_hash():
        with image.open("rb") as stream:
            return hashlib.file_digest(stream,"sha256").hexdigest()
    before=image_hash()
    if truth.get("format") != "crossdisk-g0-truth" or truth.get("version") != 1 or not truth.get("files"):
        parser.error("Missing or unsupported Linux truth report")
    if truth.get("image_sha256") != before or truth.get("filesystem_check_exit") != 0:
        parser.error("Image hash differs from sealed Linux report or filesystem check failed")
    differences=[]
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        for path,expected in truth["files"].items():
            actual=asdict(read_snapshot(backend,path))
            for key in actual.keys() | expected.keys():
                if actual.get(key)!=expected.get(key):
                    differences.append(dict(path=path,field=key,expected=expected.get(key),actual=actual.get(key)))
    result=dict(python=platform.python_version(),pytsk3=pytsk3.get_version(),image_sha256=before,
                image_unchanged=before==image_hash(),differences=differences,
                note="Comparison only; G0 requires independently verified Linux provenance and coverage.")
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return 1 if differences or not result["image_unchanged"] else 0

if __name__=="__main__":
    raise SystemExit(main())
