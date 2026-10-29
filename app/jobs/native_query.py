"""只读目录查询子进程入口；请求通过 JSON stdin 传递，不使用 shell。"""

import json
import sys
from dataclasses import asdict

from app.backends.windows_native import NativeWindowsBackend, readable_error
from app.backends.ext4_readonly import Ext4ReadOnlyBackend, Ext4Error


def main() -> int:
    try:
        request = json.load(sys.stdin)
        spec = request.get("backend_spec")
        if spec:
            from dataclasses import replace
            backend = (Ext4ReadOnlyBackend.from_image(spec["image"], expected_fs=spec.get("fingerprint", ""))
                       if "image" in spec else Ext4ReadOnlyBackend.from_partition(spec, expected_fs=spec.get("fingerprint", "")))
            with backend:
                page = backend.list_dir(request["relative_path"], offset=request["offset"],
                    show_hidden=request["show_hidden"], fingerprint=request["fingerprint"])
                page = replace(page, source_info=backend.probe)
        else:
            backend = NativeWindowsBackend(request["partition_id"], request["root"])
            page = backend.list_dir(request["relative_path"], offset=request["offset"],
                show_hidden=request["show_hidden"], fingerprint=request["fingerprint"])
        result = {"page": asdict(page)}
    except Ext4Error as exc:
        result = {"error": str(exc)}
    except (OSError, ValueError) as exc:
        result = {"error": readable_error(exc)}
    except Exception:
        result = {"error": "目录读取失败，请刷新后重试。"}
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
