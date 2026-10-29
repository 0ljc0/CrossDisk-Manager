"""名称和属性扫描：真实 Windows 临时目录、ext4 镜像与失败路径。"""

from contextlib import contextmanager
from dataclasses import asdict
import hashlib

import pytest

from app.core.browser import DirectoryPage, FileEntry, Partition
from app.core.search import SearchLimits, SearchQuery
from app.services.search import search_events
from app.backends.ext4_readonly import Ext4ReadOnlyBackend
from app.backends.windows_native import NativeWindowsBackend
from ext4_fixture import make_image
from test_inventory import sample, parse


def native_source(root, identifier="win"):
    partition = Partition(identifier, identifier, "NTFS", "只读", True, False, "fixture", "普通数据", "Windows")
    return dict(partition_id=identifier, partition_name=identifier, relative_path="", root=str(root),
                backend_spec=dict(kind="Windows", partition=asdict(partition)))


def results(events):
    return [r for event in events if event["event"] == "results" for r in event["results"]]


def test_query_glob_path_type_size_date_and_case():
    entry = FileEntry("Example.PY", False, 100, "2026-10-29 12:30:00", is_link=False)
    query = SearchQuery("*.py", ".py,.md", "home/*", "file", 10, 200, "2026-10-01", "2026-10-29")
    assert query.matches(entry, "home/demo/Example.PY", "Windows")
    assert not query.matches(entry, "home/demo/Example.PY", "ext4")
    assert SearchQuery("example", case_sensitive=False).matches(entry, "Example.PY", "ext4")
    assert not SearchQuery(min_size=101).matches(entry, "Example.PY", "Windows")
    assert not SearchQuery(modified_from="2026-10-30").matches(entry, "Example.PY", "Windows")
    assert not SearchQuery(min_size=1).matches(FileEntry("unknown", None), "unknown", "Windows")
    assert SearchQuery(extensions=".tar.gz").matches(FileEntry("archive.tar.gz", False), "archive.tar.gz", "Windows")
    with pytest.raises(ValueError):
        SearchQuery(modified_from="20261029")
    with pytest.raises(ValueError):
        SearchQuery(case_sensitive="true")


@pytest.mark.parametrize("options", [dict(min_size=-1), dict(min_size=2, max_size=1),
                                    dict(modified_from="bad"), dict(modified_from="2026-10-30", modified_to="2026-10-01")])
def test_invalid_query(options):
    with pytest.raises(ValueError):
        SearchQuery(**options)


def test_real_backends_metadata_only_cross_source(tmp_path, sample, monkeypatch):
    directory = tmp_path / "windows"
    (directory / "nested").mkdir(parents=True)
    (directory / "a.py").write_text("never execute", encoding="utf-8")
    (directory / "nested" / "b.PY").touch()
    (directory / "skip.txt").touch()
    image = make_image(tmp_path / "ext4.img", include_python=True)
    before = hashlib.sha256(image.read_bytes()).hexdigest()
    inventory = parse(sample)
    part, disk = inventory.partitions[5], inventory.disks[0]
    with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
        fingerprint = backend.probe["fingerprint"]
    ext4 = dict(partition_id=part.id, partition_name="ext4镜像", relative_path="home", root="",
                backend_spec=dict(kind="ext4", image=str(image), fingerprint=fingerprint,
                                  disk=asdict(disk), partition=asdict(part)))
    monkeypatch.setattr(NativeWindowsBackend, "open_read", lambda *a: pytest.fail("搜索不能读取文件内容"))
    monkeypatch.setattr(Ext4ReadOnlyBackend, "open_read", lambda *a: pytest.fail("搜索不能读取 ext4 文件内容"))
    events = list(search_events([native_source(directory), ext4], SearchQuery("*.py"), SearchLimits()))
    hits = results(events)
    assert {r["entry"]["name"] for r in hits} == {"a.py", "b.PY", "script.py"}
    assert {r["entry"]["backend_source"] for r in hits} == {"Windows", "ext4"}
    assert {r["partition_id"] for r in hits} == {"win", part.id}
    stats = events[-1]["stats"]
    assert stats["complete"] and stats["matches"] == 3 and stats["skipped_links"] == 1
    assert hashlib.sha256(image.read_bytes()).hexdigest() == before


def fake_source():
    return dict(partition_id="fake", partition_name="样本", relative_path="", root="", backend_spec=dict(kind="Windows"))


def test_permission_unknown_link_and_repeated_directory_are_partial():
    calls = []
    class Backend:
        def list_dir(self, path, **kwargs):
            calls.append(path)
            if path == "denied":
                raise PermissionError("private-path")
            if path == "repeat":
                return DirectoryPage((), None, "root-token")
            return DirectoryPage((FileEntry("ok.py", False, 10, is_link=False),
                                  FileEntry("denied", True, is_link=False),
                                  FileEntry("link", True, is_link=True),
                                  FileEntry("unknown-link", True),
                                  FileEntry("repeat", True, is_link=False)), None, "root-token")
    @contextmanager
    def opener(source):
        yield Backend()
    events = list(search_events([fake_source()], SearchQuery("*.py"), SearchLimits(), opener=opener))
    stats = events[-1]["stats"]
    assert not stats["complete"] and stats["error_directories"] == 1
    assert stats["error_entries"] == 1 and stats["skipped_links"] == 1 and stats["skipped_repeated"] == 1
    assert "link" not in calls and "unknown-link" not in calls
    assert "访问被拒绝" in str(events) and "private-path" not in str(events)
    assert results(events)[0]["entry"]["name"] == "ok.py"


def test_depth_result_and_cancel_limits(tmp_path):
    path = tmp_path
    for i in range(5):
        path = path / f"level{i}"
        path.mkdir()
        (path / f"file{i}.py").touch()
    events = list(search_events([native_source(tmp_path)], SearchQuery("*.py"), SearchLimits(max_depth=1)))
    assert events[-1]["stats"]["skipped_depth"] and not events[-1]["stats"]["complete"]
    events = list(search_events([native_source(tmp_path)], SearchQuery("*.py"), SearchLimits(max_results=1)))
    assert len(results(events)) == 1 and "结果数量" in events[-1]["stats"]["stopped_reason"]
    events = list(search_events([native_source(tmp_path)], SearchQuery(), SearchLimits(), cancelled=lambda: True))
    assert events[-1]["stats"]["cancelled"] and not events[-1]["stats"]["complete"]
    events = list(search_events([native_source(tmp_path)], SearchQuery(), SearchLimits(max_entries=1)))
    assert events[-1]["stats"]["entries"] == 1 and not events[-1]["stats"]["complete"]
    events = list(search_events([native_source(tmp_path)], SearchQuery(), SearchLimits(max_directories=1)))
    assert events[-1]["stats"]["directories"] == 1 and not events[-1]["stats"]["complete"]


def test_unverified_ext4_is_not_opened():
    source = fake_source()
    source["backend_spec"] = dict(kind="ext4", fingerprint="")
    @contextmanager
    def opener(source):
        pytest.fail("未验证 ext4 不应打开")
        yield
    events = list(search_events([source], SearchQuery(), SearchLimits(), opener=opener))
    assert events[-1]["stats"]["error_directories"] == 1
    assert not events[-1]["stats"]["complete"]
