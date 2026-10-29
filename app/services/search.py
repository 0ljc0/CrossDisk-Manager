"""迭代式只读搜索；不调用 open_read，不跟随目录链接。"""

from dataclasses import asdict
import time
from typing import Callable, Iterator

from app.core.search import SearchLimits, SearchQuery, SearchResult, SearchStats
from app.core.virtual_path import VirtualPath
from app.services.backend_access import open_backend
from app.services.messages import user_message


def search_events(sources: list[dict], query: SearchQuery, limits: SearchLimits,
                  cancelled: Callable[[], bool] = lambda: False, opener=open_backend) -> Iterator[dict]:
    stats = SearchStats(sources_total=len(sources))
    started = time.monotonic()
    batch, payload_bytes = [], 0
    error_details = 0
    def stopped():
        if cancelled():
            stats.cancelled, stats.stopped_reason = True, "用户取消，结果仅为已扫描部分"
        elif time.monotonic() - started >= limits.max_seconds:
            stats.stopped_reason = "达到搜索时间预算，结果仅为部分扫描"
        elif stats.entries >= limits.max_entries:
            stats.stopped_reason = "达到扫描数量预算，结果仅为部分扫描"
        return bool(stats.stopped_reason)
    def error(source, path, message):
        nonlocal error_details
        error_details += 1
        return dict(event="error", partition_name=source["partition_name"], path=path,
                    message=message) if error_details <= 100 else dict(event="suppressed")
    for source in sources:
        if stopped():
            break
        yield dict(event="progress", stats=asdict(stats))
        try:
            root = VirtualPath(source["partition_id"], source.get("relative_path", ""))
            spec = source.get("backend_spec", {})
            if spec.get("kind", "ext4") == "ext4" and not spec.get("fingerprint"):
                raise ValueError("ext4 尚未验证可读，请先人工打开并验证该分区")
            with opener(source) as backend:
                stack = [(root, 0)]
                seen_paths, seen_tokens = set(), set()
                scheduled = {root}
                path_storage = len(root.path.encode("utf-8")) + 128
                while stack and not stopped():
                    if stats.directories >= limits.max_directories:
                        stats.stopped_reason = "达到目录数量预算，结果仅为部分扫描"
                        break
                    location, depth = stack.pop()
                    if location in seen_paths:
                        continue
                    seen_paths.add(location)
                    stats.directories += 1
                    offset, fingerprint = 0, ""
                    try:
                        while not stopped():
                            page = backend.list_dir(location.path, offset=offset, show_hidden=True, fingerprint=fingerprint)
                            if offset == 0 and page.fingerprint and page.fingerprint in seen_tokens:
                                stats.skipped_repeated += 1
                                yield error(source, location.path, "目录身份重复，已跳过以防止循环")
                                break
                            if offset == 0 and page.fingerprint:
                                seen_tokens.add(page.fingerprint)
                            fingerprint = page.fingerprint
                            for entry in page.entries:
                                if stopped():
                                    break
                                stats.entries += 1
                                try:
                                    child = location.child(entry.name)
                                    if len(child.path.encode("utf-8")) > 32768:
                                        raise ValueError("路径超过搜索安全长度")
                                except ValueError as exc:
                                    stats.error_entries += 1
                                    yield error(source, location.path, str(exc))
                                    continue
                                if entry.error:
                                    stats.error_entries += 1
                                    yield error(source, child.path, entry.error)
                                if query.matches(entry, child.path, entry.backend_source):
                                    size = len(child.path.encode("utf-8")) + len(entry.name.encode("utf-8")) + 256
                                    if payload_bytes + size > 32 * 1024 * 1024:
                                        stats.stopped_reason = "达到结果内存预算，结果仅为部分扫描"
                                        break
                                    payload_bytes += size
                                    batch.append(asdict(SearchResult(root.partition_id, source["partition_name"], child.path, entry)))
                                    stats.matches += 1
                                    if len(batch) >= 50:
                                        yield dict(event="results", results=batch)
                                        batch = []
                                    if stats.matches >= limits.max_results:
                                        stats.stopped_reason = "达到结果数量上限，结果仅为部分扫描"
                                        break
                                if entry.is_link is True:
                                    stats.skipped_links += 1
                                elif entry.is_directory is True and entry.is_link is None and not entry.error:
                                    stats.error_entries += 1
                                    yield error(source, child.path, "目录链接状态未知，未递归")
                                elif entry.is_directory is None and not entry.error:
                                    stats.error_entries += 1
                                    yield error(source, child.path, "条目类型未知，未递归")
                                elif entry.is_directory is True and entry.is_link is False and not entry.error:
                                    if depth >= limits.max_depth:
                                        stats.skipped_depth += 1
                                        yield error(source, child.path, "达到目录深度上限，已跳过子目录")
                                    elif len(stack) + stats.directories >= limits.max_directories:
                                        stats.stopped_reason = "达到目录数量预算，结果仅为部分扫描"
                                        break
                                    elif child in scheduled:
                                        stats.skipped_repeated += 1
                                    elif path_storage + len(child.path.encode("utf-8")) + 128 > 16 * 1024 * 1024:
                                        stats.stopped_reason = "达到目录路径内存预算，结果仅为部分扫描"
                                        break
                                    else:
                                        scheduled.add(child)
                                        path_storage += len(child.path.encode("utf-8")) + 128
                                        stack.append((child, depth + 1))
                            if batch:
                                yield dict(event="results", results=batch)
                                batch = []
                            yield dict(event="progress", stats=asdict(stats))
                            if stopped() or page.next_offset is None:
                                break
                            if page.next_offset <= offset:
                                raise ValueError("后端分页未前进，已停止该目录以防止循环")
                            offset = page.next_offset
                    except Exception as exc:
                        stats.error_directories += 1
                        yield error(source, location.path, user_message(exc))
                        if stats.error_directories % 20 == 0:
                            yield dict(event="progress", stats=asdict(stats))
                stats.sources_done += 1
        except Exception as exc:
            stats.error_directories += 1
            stats.sources_done += 1
            yield error(source, source.get("relative_path", ""), user_message(exc))
    if batch:
        yield dict(event="results", results=batch)
    stats.complete = not (stats.stopped_reason or stats.error_directories or stats.error_entries or stats.skipped_depth or stats.skipped_repeated)
    yield dict(event="finished", stats=asdict(stats))
