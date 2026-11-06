"""Portable package-only check; not Ubuntu target preflight or write authorization."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
from app.core.bundle import BundleError, loads, manifest_hash

def ordinary(root,relative):
    current=root
    for component in relative.split("/"):
        current=current/component
        info=current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400:
            raise BundleError("Links/reparse points are forbidden")
    if not stat.S_ISREG(info.st_mode): raise BundleError("Expected ordinary file")
    return current

def check(root):
    root=Path(root)
    if root.is_symlink() or not root.is_dir() or getattr(root.lstat(),"st_file_attributes",0)&0x400:
        raise BundleError("Bundle must be an ordinary directory")
    manifest=ordinary(root,"manifest.json")
    with manifest.open("rb") as stream:
        value=loads(stream.read(4*1024*1024+1))
    count=0
    for op in value["operations"]:
        if "payload" not in op: continue
        expected=op["payload"]
        source=ordinary(root,expected["path"])
        digest=hashlib.sha256(); size=0
        with source.open("rb") as stream:
            while chunk:=stream.read(1024*1024):
                size+=len(chunk)
                if size>expected["size"]: raise BundleError("Payload size mismatch")
                digest.update(chunk)
        if size!=expected["size"] or digest.hexdigest()!=expected["sha256"]:
            raise BundleError("Payload size/hash mismatch")
        count+=1
    return dict(package_valid=True,manifest_sha256=manifest_hash(value),operations=len(value["operations"]),
                payloads_checked=count,target_preflight="NOT_IMPLEMENTED",apply_allowed=False,
                limitation="Package-only check on stable local input; no race-safe staging or target authorization")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle",required=True)
    args=parser.parse_args()
    try:
        print(json.dumps(check(args.bundle),indent=2))
    except (ValueError,OSError) as exc:
        print(json.dumps(dict(package_valid=False,error=str(exc),apply_allowed=False)))
        return 1
    return 0

if __name__=="__main__":
    raise SystemExit(main())
