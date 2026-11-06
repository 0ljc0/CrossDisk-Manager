import hashlib
import struct
from dataclasses import asdict
import pytest
from ext4_fixture import make_image, SAMPLE
from app.backends.ext4_readonly import Ext4ReadOnlyBackend
from app.services.file_snapshot import read_snapshot

@pytest.mark.parametrize("nanos,nlink", [(123456789,1),(987654321,2),(0,1)])
def test_raw_metadata_mapping(tmp_path,nanos,nlink):
    image=make_image(tmp_path / "test.img")
    data=bytearray(image.read_bytes())
    pos=5*1024+13*256
    struct.pack_into("<H",data,pos,0o100640)
    struct.pack_into("<H",data,pos+2,1000)
    struct.pack_into("<H",data,pos+24,1001)
    struct.pack_into("<H",data,pos+26,nlink)
    struct.pack_into("<H",data,pos+128,32)
    struct.pack_into("<I",data,pos+136,nanos<<2)
    image.write_bytes(data)
    before=hashlib.sha256(data).hexdigest()
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        result=asdict(read_snapshot(backend,"home/demo/sample.txt"))
        assert result == dict(kind="regular_file",size=len(SAMPLE),sha256=hashlib.sha256(SAMPLE).hexdigest(),mode=0o100640,uid=1000,gid=1001,mtime_ns=1700000000*10**9+nanos,nlink=nlink,inode=14)
        with pytest.raises(ValueError):
            read_snapshot(backend,"home/demo")
        assert not backend.get_capabilities().write
    assert hashlib.sha256(image.read_bytes()).hexdigest()==before


def test_snapshot_rejects_changed_metadata(tmp_path, monkeypatch):
    from app.services import file_snapshot
    image=make_image(tmp_path / "test.img")
    original=file_snapshot._metadata
    calls=0
    def changed(backend,path):
        nonlocal calls
        calls+=1
        values=original(backend,path)
        return values if calls==1 else (*values[:-1],values[-1]+1)
    monkeypatch.setattr(file_snapshot,"_metadata",changed)
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        with pytest.raises(ValueError,match="changed"):
            read_snapshot(backend,"home/demo/sample.txt")
