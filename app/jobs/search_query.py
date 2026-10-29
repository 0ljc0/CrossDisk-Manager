"""搜索子进程只输出逐行 JSON 元数据事件，不写索引或读取文件内容。"""

import json
import sys

from app.core.search import SearchLimits, SearchQuery
from app.services.search import search_events
from app.services.messages import user_message


def main() -> int:
    try:
        request = json.load(sys.stdin)
        sources = request["sources"]
        if not isinstance(sources, list) or not 1 <= len(sources) <= 128:
            raise ValueError("搜索来源为空或过多")
        for event in search_events(sources, SearchQuery(**request["query"]), SearchLimits(**request["limits"])):
            if event["event"] == "suppressed":
                continue
            print(json.dumps(event, ensure_ascii=True), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps(dict(event="fatal", message=user_message(exc)), ensure_ascii=True), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
