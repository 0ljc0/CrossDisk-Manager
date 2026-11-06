import hashlib
import json
import sys
from dataclasses import asdict
import pytest
from ext4_fixture import make_image
from app.backends.ext4_readonly import Ext4ReadOnlyBackend
from app.services.file_snapshot import read_snapshot
from scripts import g0_compare, g0_linux_prepare

@pytest.mark.parametrize("tamper", [False, True])
def test_sealed_report(tmp_path,monkeypatch,tamper):
    image=make_image(tmp_path/"g0.img")
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        files={"home/demo/sample.txt":asdict(read_snapshot(backend,"home/demo/sample.txt"))}
    truth=tmp_path/"truth.json"
    truth.write_text(json.dumps(dict(format="crossdisk-g0-truth",version=1,files=files,
        image_sha256="bad" if tamper else hashlib.sha256(image.read_bytes()).hexdigest(),filesystem_check_exit=0)),encoding="utf-8")
    monkeypatch.setattr(sys,"argv",["compare","--image",str(image),"--truth",str(truth)])
    if tamper:
        with pytest.raises(SystemExit): g0_compare.main()
    else:
        assert g0_compare.main()==0

def test_linux_tool_refuses_windows(tmp_path,monkeypatch):
    monkeypatch.setattr(g0_linux_prepare.platform,"system",lambda:"Windows")
    with pytest.raises(RuntimeError,match="Ubuntu"):
        g0_linux_prepare.prepare(tmp_path)
    assert list(tmp_path.iterdir())==[]
