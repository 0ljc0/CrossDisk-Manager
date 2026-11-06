"""Explicit image-only frozen UI smoke check; never accepts raw device sources."""
import json
from pathlib import Path
import stat
import time

from PySide6.QtCore import QTimer
from app.core.bundle import require
from app.ui.bundle_dialog import BundleDialog


def run(application, request_file):
    request_file=Path(request_file)
    payload=json.loads(request_file.read_text(encoding="utf-8"))
    spec=payload["request"]["backend_spec"]
    require(spec["kind"]=="ext4" and "image" in spec,"Smoke source must be an ordinary ext4 image")
    image=Path(spec["image"])
    info=image.lstat()
    require(stat.S_ISREG(info.st_mode) and not getattr(info,"st_file_attributes",0)&0x400,"Invalid smoke image")
    output=request_file.absolute().parent/"bundle-smoke-output"
    source=request_file.absolute().parent/"bundle-smoke-content.txt"
    with source.open("xb") as stream:stream.write(b"frozen staging validation\n")
    dialog=BundleDialog(payload["request"],payload["scope"],request_file.absolute().parent/"drafts")
    dialog.show();dialog.start()
    stage=0;started=time.monotonic()
    timer=QTimer(dialog)
    def finish(code):
        timer.stop()
        dialog.exported_id=dialog.bundle_id
        dialog.close()
        application.exit(code)
    def poll():
        nonlocal stage
        if time.monotonic()-started>45:
            if dialog.worker:return
            finish(5);return
        if dialog.worker:return
        if dialog.backend is None or dialog.status.text().startswith("未暂存"):
            finish(6);return
        if stage==0:
            stage=1
            dialog.start("create_file",path="frozen-new.txt",source=str(source),metadata=dict(uid=1000,gid=1000,mode=420))
        elif stage==1:
            if len(dialog.operations)!=1:finish(7);return
            stage=2;dialog.start("export",destination=str(output))
        else:
            good=(output/"manifest.json").is_file() and dialog.exported_id==dialog.bundle_id
            finish(0 if good else 8)
    timer.timeout.connect(poll);timer.start(50)
    return application.exec()
