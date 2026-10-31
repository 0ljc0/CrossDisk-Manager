"""Windows 磁盘/分区查询：只有 Get-* 命令，无挂载、格式化或写入操作。

此模块不依赖 PySide6，可以独立测试。数据来自 Windows Storage PowerShell 模块。
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any

# 固定脚本：禁止插入用户可控的 PowerShell 指令。
# 以压缩 JSON 输出，使用数组避免只有一项时 ConvertTo-Json 产生结构变化。
SCAN_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$diskRows = @(
    foreach ($d in @(Get-Disk -ErrorAction Stop)) {
        [pscustomobject]@{
            number = [int]$d.Number
            name = [string]$d.FriendlyName
            size = [long]$d.Size
            partition_style = [string]$d.PartitionStyle
            health = [string]$d.HealthStatus
            operational = [string]$d.OperationalStatus
            bus_type = [string]$d.BusType
        }
    }
)
$partitionRows = @(
    foreach ($p in @(Get-Partition -ErrorAction Stop)) {
        $v = $null
        try {
            $matches = @(Get-Volume -Partition $p -ErrorAction Stop)
            if ($matches.Count -gt 0) { $v = $matches[0] }
        } catch { }
        $letter = [string]$p.DriveLetter
        if ($letter -notmatch '^[a-zA-Z]$') { $letter = '' }
        $gpt = ''
        if ($p.PSObject.Properties.Name -contains 'GptType') { $gpt = [string]$p.GptType }
        [pscustomobject]@{
            disk_number = [int]$p.DiskNumber
            partition_number = [int]$p.PartitionNumber
            type = [string]$p.Type
            gpt_type = $gpt
            offset = [long]$p.Offset
            size = [long]$p.Size
            is_hidden = [bool]$p.IsHidden
            is_read_only = [bool]$p.IsReadOnly
            drive_letter = $letter
            access_paths = @($p.AccessPaths | Where-Object { $_ })
            file_system = $(if ($null -ne $v) { [string]$v.FileSystemType } else { '' })
            volume_label = $(if ($null -ne $v) { [string]$v.FileSystemLabel } else { '' })
            volume_size = $(if ($null -ne $v) { [long]$v.Size } else { 0 })
            free_space = $(if ($null -ne $v) { [long]$v.SizeRemaining } else { 0 })
        }
    }
)
[pscustomobject]@{ disks = @($diskRows); partitions = @($partitionRows) } |
    ConvertTo-Json -Depth 5 -Compress
'''

GPT_TYPES = {
    'C12A7328-F81F-11D2-BA4B-00A0C93EC93B': 'EFI 系统分区',
    'E3C9E316-0B5C-4DB8-817D-F92DF00215AE': 'Microsoft 保留分区 (MSR)',
    'DE94BBA4-06D1-4D40-A16A-BFD50179D6AC': 'Windows 恢复分区',
    '0FC63DAF-8483-4772-8E79-3D69D8477DE4': 'Linux 文件系统分区',
    '0657FD6D-A4AB-43C4-84E5-0933C84B4F4F': 'Linux Swap 分区',
    'E6D6D379-F507-44C2-A23C-238F2A3DF928': 'Linux LVM 分区',
    'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7': '基本数据分区',
}


def normalize_payload(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """标准化 PowerShell JSON；不补猜缺失的盘符、文件系统。"""
    if not isinstance(payload, dict):
        raise ValueError('分区扫描结果不是 JSON 对象')
    disks = payload.get('disks', [])
    parts = payload.get('partitions', [])
    if isinstance(disks, dict):
        disks = [disks]
    if isinstance(parts, dict):
        parts = [parts]
    if not isinstance(disks, list) or not isinstance(parts, list):
        raise ValueError('JSON 磁盘或分区字段格式错误')
    if any(not isinstance(v, dict) for v in disks + parts):
        raise ValueError('JSON 磁盘或分区项格式错误')
    return {'disks': disks, 'partitions': parts}


def partition_kind(part: dict[str, Any]) -> str:
    """根据官方 GPT 类型标记分区用途，不将 Linux 类型 GUID 直接等同于 ext4。"""
    guid = str(part.get('gpt_type') or '').strip('{}').upper()
    if guid in GPT_TYPES:
        return GPT_TYPES[guid]
    generic = str(part.get('type') or '').strip()
    return {'System': 'EFI / 系统分区',
            'Reserved': '保留分区',
            'Recovery': '恢复分区',
            'Basic': '基本数据分区',
            'Unknown': '未知分区类型'}.get(generic, generic or '未知分区类型')


def is_protected_partition(part: dict[str, Any]) -> bool:
    """保留、EFI、Recovery 等在本程序内不提供直接浏览入口。"""
    guid = str(part.get('gpt_type') or '').strip('{}').upper()
    kind = str(part.get('type') or '').lower()
    return guid in {
        'C12A7328-F81F-11D2-BA4B-00A0C93EC93B',
        'E3C9E316-0B5C-4DB8-817D-F92DF00215AE',
        'DE94BBA4-06D1-4D40-A16A-BFD50179D6AC',
    } or kind in {'system', 'reserved', 'recovery'}


def decode_output(raw: bytes) -> str:
    """PowerShell 优先 UTF-8；兼容部分中文 Windows 环境的控制台编码。"""
    for coding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(coding)
        except UnicodeDecodeError:
            pass
    return raw.decode('utf-8', errors='replace')


def scan_storage(timeout: int = 45) -> dict[str, list[dict[str, Any]]]:
    if os.name != 'nt':
        raise RuntimeError('磁盘分区扫描仅适用于 Windows；在其他系统下请运行单元测试。')
    command = SCAN_SCRIPT.encode('utf-16le')
    import base64
    encoded = base64.b64encode(command).decode('ascii')
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        proc = subprocess.run(
            ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
             '-EncodedCommand', encoded],
            capture_output=True,
            timeout=timeout,
            creationflags=creationflags,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError('找不到 Windows PowerShell，请检查系统环境。') from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'磁盘扫描超过 {timeout} 秒，已停止等待。') from exc
    if proc.returncode != 0:
        err = decode_output(proc.stderr).strip()
        raise RuntimeError('Windows 分区查询失败：' + (err[-600:] if err else '无具体错误信息'))
    output = decode_output(proc.stdout).strip()
    try:
        # PowerShell 偶发包含 BOM；通常仅输出一行 JSON。
        return normalize_payload(json.loads(output))
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError('磁盘查询返回的数据无法解析：' + str(exc)) from exc
