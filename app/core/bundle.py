"""Strict schema 3 validation. No filesystem writes or authorization."""
import hashlib
import json
import re
import stat

class BundleError(ValueError):
    pass

def require(value, message):
    if not value: raise BundleError(message)

def keys(value, fields):
    require(type(value) is dict and set(value)==set(fields.split()), "Missing or unknown fields")

def integer(value, low=0, high=2**63-1):
    require(type(value) is int and low<=value<=high,"Invalid integer")

def path(value):
    require(type(value) is str and value and len(value.encode("utf-8"))<=4096,"Invalid path")
    require(not any(p in ("", ".", "..") for p in value.split("/")) and "\\" not in value and "\0" not in value,"Unsafe relative path")
    return value

def identifier(value):
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,64}",value),"Invalid ID")

def sha(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}",value),"Invalid digest")

def snapshot(value):
    keys(value,"kind size sha256 mode uid gid mtime_ns nlink inode")
    require(value["kind"]=="regular_file","Not a regular file")
    sha(value["sha256"])
    for name in ("size","mode","uid","gid","mtime_ns","nlink","inode"):
        integer(value[name],-2**63 if name=="mtime_ns" else 0)
    require(value["nlink"]==1 and value["inode"]>0,"Unsupported object identity")
    require(stat.S_ISREG(value["mode"]) and value["mode"] & ~0o100777 == 0,"Unsupported mode")
    require(value["uid"]>0 and value["gid"]>0,"Root ownership unsupported")

def metadata(value):
    keys(value,"uid gid mode")
    integer(value["uid"],1,2**32-2); integer(value["gid"],1,2**32-2)
    integer(value["mode"],0,0o777)

def validate(value):
    keys(value,"format version bundle_id target operations")
    require(value["format"]=="crossdisk-bundle" and type(value["version"]) is int and value["version"]==3,"Unsupported format")
    identifier(value["bundle_id"])
    target=value["target"]
    keys(target,"filesystem fs_uuid mount_relative_root")
    require(target["filesystem"]=="ext4","Unsupported filesystem")
    uuid=target["fs_uuid"]
    require(type(uuid) is str and re.fullmatch(r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",uuid),"Invalid UUID")
    target["fs_uuid"]=uuid.replace("-", "").lower()
    path(target["mount_relative_root"])
    ops=value["operations"]
    require(type(ops) is list and 1<=len(ops)<=1000,"Invalid operation count")
    ids=set(); paths=[]
    extras={"create_file":"precondition payload metadata","replace_file":"precondition payload metadata_policy","delete_file":"precondition","mkdir":"precondition metadata","rename_file":"new_path source_precondition destination_precondition"}
    for op in ops:
        require(type(op) is dict and type(op.get("type")) is str and op["type"] in extras,"Unknown operation")
        kind=op["type"]
        keys(op,"id type path "+extras[kind]); identifier(op["id"])
        require(op["id"] not in ids,"Duplicate operation ID"); ids.add(op["id"])
        paths.append(path(op["path"]))
        if kind=="rename_file":
            paths.append(path(op["new_path"]))
            require(op["path"].rpartition("/")[0]==op["new_path"].rpartition("/")[0],"Cross-directory rename")
            snapshot(op["source_precondition"])
            require(op["destination_precondition"]=={"target":"absent"},"Destination must be absent")
        elif kind in ("create_file","mkdir"):
            require(op["precondition"]=={"target":"absent"},"Target must be absent")
            metadata(op["metadata"])
            if kind=="mkdir": require("/" not in op["path"],"Only immediate mkdir supported")
        else:
            keys(op["precondition"],"target object")
            require(op["precondition"]["target"]=="matches","Expected state required")
            snapshot(op["precondition"]["object"])
        if kind=="replace_file": require(op["metadata_policy"]=="preserve_basic","Unknown metadata policy")
        if "payload" in op:
            payload=op["payload"]; keys(payload,"path size sha256")
            path(payload["path"]); require(payload["path"].startswith("files/"),"Payload outside files")
            integer(payload["size"]); sha(payload["sha256"])
    for i,left in enumerate(paths):
        for right in paths[i+1:]:
            require(left!=right and not left.startswith(right+"/") and not right.startswith(left+"/"),"Overlapping operation paths")
    return value

def loads(raw):
    require(len(raw)<=4*1024*1024,"Manifest too large")
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,"Duplicate JSON key")
            result[key]=value
        return result
    def bad(value): raise BundleError("Non-integer numeric value")
    def number(value):
        require(value!="-0","Negative zero")
        return int(value)
    try:
        result=json.loads(raw.decode("utf-8"),object_pairs_hook=pairs,parse_float=bad,parse_constant=bad,parse_int=number)
        canonical(result) # reject surrogate Unicode, including unknown fields
        return validate(result)
    except (UnicodeError,RecursionError,json.JSONDecodeError) as exc:
        raise BundleError("Invalid JSON encoding or structure") from exc

def canonical(value):
    if type(value) is str:
        value.encode("utf-8")
        return '"'+''.join('\\'+c if c in ('"','\\') else "\\u%04x"%ord(c) if ord(c)<32 else c for c in value)+'"'
    if type(value) is int: return str(value)
    if type(value) is list: return '['+','.join(canonical(v) for v in value)+']'
    if type(value) is dict: return '{'+','.join(canonical(k)+':'+canonical(value[k]) for k in sorted(value))+'}'
    raise BundleError("Unsupported JSON value")

def manifest_hash(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
