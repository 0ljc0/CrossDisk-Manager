"""只用样本验证扫描解析、设备身份及失败路径。"""

import copy
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.inventory import InventoryError
from app.services.disk_inventory import (BASIC, EFI, LINUX_DATA, MSR, RECOVERY,
                                         DiskInventoryService, parse_inventory)


@pytest.fixture
def sample():
    disk = {"Number": 0, "FriendlyName": "测试磁盘", "Size": 1024**4,
            "Guid": "12345678-1234-1234-1234-123456789abc", "UniqueId": "test-id",
            "PartitionStyle": "GPT", "Status": "Online", "IsOffline": False, "IsReadOnly": False}
    partitions = [{"DiskNumber": 0, "PartitionNumber": n, "Guid": f"00000000-0000-0000-0000-{n:012d}",
                   "GptType": kind, "Offset": n * 1024**3, "Size": 1024**3,
                   "IsHidden": n in (1, 2, 5), "IsSystem": n == 1, "IsBoot": n == 3,
                   "DriveLetter": "C" if n == 3 else None, "AccessPaths": None, "Status": "Online"}
                  for n, kind in enumerate((EFI, MSR, BASIC, BASIC, RECOVERY, LINUX_DATA), 1)]
    volume = {"UniqueId": "test-volume", "Path": "test-path", "DriveLetter": "C",
              "FileSystemLabel": "用户给起的 EFI 昵称", "FileSystem": "NTFS", "Status": "OK"}
    return {"Disks": [disk], "Partitions": partitions, "Volumes": [volume]}


def parse(sample):
    return parse_inventory(json.dumps(sample, ensure_ascii=False))


def test_inventory_classification_and_no_letter(sample):
    inventory = parse(sample)
    assert len(inventory.disks) == 1
    assert len(inventory.partitions) == 6
    assert [p.category for p in inventory.partitions][:3] == ["EFI", "MSR", "普通数据"]
    assert inventory.partitions[0].status == "受保护"
    assert inventory.partitions[1].status == "不可浏览"
    assert inventory.partitions[2].category == "普通数据"  # 昵称不改变 GPT 分类
    assert inventory.partitions[2].filesystem == "NTFS"
    assert inventory.partitions[5].filesystem == "未识别"
    assert "ext4" not in inventory.partitions[5].filesystem
    assert inventory.partitions[5].drive_letter == ""


def test_singleton_null_and_empty_disk(sample):
    sample["Disks"] = sample["Disks"][0]
    sample["Partitions"] = sample["Partitions"][0]
    sample["Volumes"] = None
    assert len(parse(sample).partitions) == 1
    sample["Partitions"] = None
    assert not parse(sample).partitions
    assert not parse({"Disks": None, "Partitions": None, "Volumes": None}).disks


def test_volume_without_letter_associated_by_path(sample):
    sample["Partitions"][0]["AccessPaths"] = ["volume-path"]
    sample["Volumes"][0].update(DriveLetter=None, Path="volume-path", FileSystem="FAT32")
    assert parse(sample).partitions[0].filesystem == "FAT32"


def test_identity_survives_renumbering_and_detects_replacement(sample):
    original = parse(sample)
    sample["Disks"][0]["Number"] = 7
    for p in sample["Partitions"]:
        p["DiskNumber"] = 7
        p["PartitionNumber"] += 10
    renumbered = parse(sample)
    assert original.disks[0].id == renumbered.disks[0].id
    assert [p.id for p in original.partitions] == [p.id for p in renumbered.partitions]
    sample["Disks"][0]["Guid"] = "87654321-1234-1234-1234-123456789abc"
    assert parse(sample).partitions[0].id != original.partitions[0].id


def test_missing_identity_never_pretends_stable(sample):
    sample["Disks"][0].update(Guid=None, UniqueId=None)
    one, two = parse(sample), parse(sample)
    assert not one.disks[0].identity_stable
    assert one.partitions[0].id != two.partitions[0].id


@pytest.mark.parametrize("damage", ["missing_disk", "duplicate", "out_of_bounds", "bad_flag"])
def test_inconsistent_snapshot_rejected(sample, damage):
    if damage == "missing_disk":
        sample["Disks"] = []
    elif damage == "duplicate":
        sample["Partitions"].append(copy.deepcopy(sample["Partitions"][0]))
    elif damage == "out_of_bounds":
        sample["Partitions"][0]["Size"] = 2**50
    else:
        sample["Partitions"][0]["IsHidden"] = "false"
    with pytest.raises(InventoryError, match="格式无效"):
        parse(sample)


@pytest.mark.parametrize("error,message", [
    (FileNotFoundError(), "找不到"), (PermissionError(), "被拒绝"),
    (subprocess.TimeoutExpired("powershell", 1), "超时")])
def test_process_errors(error, message):
    with pytest.raises(InventoryError, match=message):
        DiskInventoryService(runner=Mock(side_effect=error)).scan()


def test_fixed_query_and_process_failure(sample):
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(sample)))
    assert len(DiskInventoryService(runner=runner).scan().partitions) == 6
    args, kwargs = runner.call_args
    assert args[0][-2] == "-EncodedCommand"
    assert kwargs["timeout"] == 30
    assert not kwargs.get("shell", False)
    runner.return_value = SimpleNamespace(returncode=1, stdout='{"Error":"permission"}')
    with pytest.raises(InventoryError, match="权限不足"):
        DiskInventoryService(runner=runner).scan()


@pytest.mark.parametrize("payload", ["not-json", "[]", "{}", '{"Error":"query"}'])
def test_invalid_output(payload):
    with pytest.raises(InventoryError):
        parse_inventory(payload)
