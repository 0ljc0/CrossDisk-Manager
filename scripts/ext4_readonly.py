"""独立只读验收进程：不启动 GUI、不提权、不修改源分区。

sample 操作只导出到自动生成的 Windows 临时新文件并校验，随后清理。
这不是任务 09 的通用导出/复制功能。
"""

import argparse
from dataclasses import asdict
import hashlib
from pathlib import Path
import tempfile

from app.backends.ext4_readonly import Ext4Error, Ext4ReadOnlyBackend, validate_path
from app.services.disk_inventory import DiskInventoryService, LINUX_DATA


def validate_sample(backend: Ext4ReadOnlyBackend, path: str) -> tuple[int, str]:
    count, digest = 0, hashlib.sha256()
    # 新生成、非已存在的普通 Windows 临时文件；没有用户指定目标或覆盖选项。
    with tempfile.TemporaryDirectory(prefix="CrossDisk-ext4-validation-") as directory:
        destination = Path(directory) / "sample-export.bin"
        with backend.open_read(path) as source, destination.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                count += len(chunk)
        exported = hashlib.sha256()
        with destination.open("rb") as check:
            while chunk := check.read(1024 * 1024):
                exported.update(chunk)
        if count != backend.stat(path).size or exported.digest() != digest.digest():
            raise Ext4Error("只读样本导出校验失败")
    return count, digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="独立 ext4 只读验收；真实分区仅人工显式选择")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--image", help="普通可丢弃 ext4 镜像")
    group.add_argument("--partition-id", help="本次扫描得到的稳定分区标识，不使用固定磁盘/分区号")
    parser.add_argument("--list-candidates", action="store_true", help="只查询 Storage 元数据，不读取原始分区")
    parser.add_argument("--action", choices=("ls", "sample"), default="ls")
    parser.add_argument("--path", default="/", help="ext4 路径；sample 必须明确指定普通样本文件")
    args = parser.parse_args()
    try:
        if args.list_candidates:
            inventory = DiskInventoryService().scan()
            for p in inventory.partitions:
                if p.gpt_type == LINUX_DATA:
                    print(f"{p.id}  disk={p.disk_number} partition={p.number} size={p.size} offset={p.offset}")
            return 0
        relative = args.path[1:] if args.path.startswith("/") else args.path
        validate_path(relative)
        if args.image:
            backend = Ext4ReadOnlyBackend.from_image(args.image)
        elif args.partition_id:
            inventory = DiskInventoryService().scan()
            part = next((p for p in inventory.partitions if p.id == args.partition_id), None)
            if part is None:
                raise Ext4Error("分区身份不在当前清单中，请重新列举候选")
            disk = next(d for d in inventory.disks if d.id == part.disk_id)
            backend = Ext4ReadOnlyBackend.from_partition(dict(disk=asdict(disk), partition=asdict(part)))
        else:
            parser.error("请选择 --image、--partition-id 或 --list-candidates")
        with backend:
            if args.action == "sample":
                count, digest = validate_sample(backend, relative)
                print(f"Validated bytes={count} SHA256={digest}; temporary export verified and removed")
            else:
                offset, fingerprint = 0, ""
                while True:
                    page = backend.list_dir(relative, offset=offset, fingerprint=fingerprint, show_hidden=True)
                    for entry in page.entries:
                        print(f"{'LINK' if entry.is_link else 'DIR' if entry.is_directory else 'FILE'}  {entry.name}")
                    if page.next_offset is None:
                        break
                    offset, fingerprint = page.next_offset, page.fingerprint
        return 0
    except Exception as exc:
        print(str(exc) if isinstance(exc, Ext4Error) else "只读验收失败，检查设备权限、镜像路径与 Storage 查询权限。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
