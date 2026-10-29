"""只读目录查询子进程入口；请求通过 JSON stdin 传递，不使用 shell。"""

import json
import sys
from dataclasses import asdict

from app.backends.windows_native import NativeWindowsBackend, readable_error
from app.backends.ext4_readonly import Ext4ReadOnlyBackend, Ext4Error
from app.services.backend_access import query_page
from app.services.messages import user_message


def main() -> int:
    try:
        request = json.load(sys.stdin)
        page = query_page(request)
        result = {"page": asdict(page)}
    except Exception as exc:
        result = {"error": user_message(exc)}
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
