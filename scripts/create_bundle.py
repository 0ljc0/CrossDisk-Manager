"""Create a schema 3 bundle from an ordinary ext4 image and a local staging plan."""
import argparse
import json
from pathlib import Path
import stat

from app.backends.ext4_readonly import Ext4ReadOnlyBackend
from app.backends.offline_bundle import OfflineBundleBackend
from app.core.bundle import keys, require


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--plan",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        info=args.image.lstat()
        require(stat.S_ISREG(info.st_mode) and not getattr(info,"st_file_attributes",0)&0x400,
                "Image must be an ordinary local file")
        def unique(items):
            result={}
            for name,value in items:
                require(name not in result,"Duplicate plan key")
                result[name]=value
            return result
        with args.plan.open("rb") as stream:
            raw=stream.read(4*1024*1024+1)
        require(len(raw)<=4*1024*1024,"Plan too large")
        plan=json.loads(raw.decode("utf-8"),object_pairs_hook=unique)
        keys(plan,"fs_relative_root operations")
        require(type(plan["operations"]) is list and 1<=len(plan["operations"])<=1000,"Invalid plan operation count")
        with Ext4ReadOnlyBackend.from_image(str(args.image)) as reader, OfflineBundleBackend(
                reader,plan["fs_relative_root"],workspace_parent=args.output.absolute().parent/".crossdisk-drafts") as writer:
            for op in plan["operations"]:
                require(type(op) is dict,"Plan operation must be an object")
                kind=op.get("type")
                if kind in ("create_file","replace_file"):
                    keys(op,"type path source"+(" metadata" if kind=="create_file" else ""))
                    source=Path(op["source"])
                    if not source.is_absolute():source=args.plan.absolute().parent/source
                    info=source.lstat()
                    require(stat.S_ISREG(info.st_mode) and not getattr(info,"st_file_attributes",0)&0x400,
                            "Payload source must be an ordinary local file")
                    with source.open("rb") as content:
                        if kind=="create_file":writer.create_file(op["path"],content,op["metadata"])
                        else:writer.replace_file(op["path"],content)
                elif kind=="delete_file":
                    keys(op,"type path");writer.delete_file(op["path"])
                elif kind=="mkdir":
                    keys(op,"type path metadata");writer.create_directory(op["path"],op["metadata"])
                elif kind=="rename_file":
                    keys(op,"type path new_path");writer.rename_file(op["path"],op["new_path"])
                else:raise ValueError("Unsupported plan operation")
            result=writer.export_bundle(args.output)
        print(json.dumps(result,ensure_ascii=True,indent=2))
        return 0
    except (OSError,ValueError,TypeError,KeyError,RecursionError) as exc:
        print(json.dumps(dict(exported=False,error=str(exc),applied=False)))
        return 1


if __name__=="__main__":raise SystemExit(main())
