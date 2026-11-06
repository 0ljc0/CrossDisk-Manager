import copy
import hashlib
import json
import pytest
from app.core.bundle import loads,canonical,BundleError
from scripts.validate_bundle import check

def sample():
    return dict(format="crossdisk-bundle",version=3,bundle_id="test",target=dict(filesystem="ext4",fs_uuid="a"*32,mount_relative_root="home/test"),operations=[dict(id="op1",type="create_file",path="a.txt",precondition=dict(target="absent"),payload=dict(path="files/a.bin",size=3,sha256=hashlib.sha256(b"abc").hexdigest()),metadata=dict(uid=1000,gid=1000,mode=420))])

def encode(v): return json.dumps(v).encode()

def test_roundtrip():
    value=loads(encode(sample()))
    assert loads(canonical(value).encode())==value
    assert canonical({"中":"\n"})=='{"中":"\\u000a"}'

@pytest.mark.parametrize("path",["/etc/x","../x","a/../x","a//x","a\\x",""])
def test_bad_paths(path):
    value=sample();value["operations"][0]["path"]=path
    with pytest.raises(BundleError): loads(encode(value))

@pytest.mark.parametrize("raw",[b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1.0}',b'{"a":-0}',b'{"a":true}'])
def test_ambiguous_json(raw):
    with pytest.raises(BundleError): loads(raw)

def test_overlap_and_metadata():
    value=sample(); other=copy.deepcopy(value["operations"][0]);other["id"]="op2"
    value["operations"].append(other)
    with pytest.raises(BundleError): loads(encode(value))
    value=sample();value["operations"][0]["metadata"]["mode"]=0o4755
    with pytest.raises(BundleError): loads(encode(value))

def test_payload_check(tmp_path):
    (tmp_path/"files").mkdir();(tmp_path/"files/a.bin").write_bytes(b"abc")
    (tmp_path/"manifest.json").write_bytes(encode(sample()))
    result=check(tmp_path)
    assert result["package_valid"] and not result["apply_allowed"]
    (tmp_path/"files/a.bin").write_bytes(b"abd")
    with pytest.raises(BundleError):check(tmp_path)
