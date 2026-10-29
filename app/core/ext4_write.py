"""ext4 写入扩展契约；证据说明不构成运行时写入授权。"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from app.core.virtual_path import VirtualPath

EXT4_WRITE_DISABLED = "只读：未接入已验证的受控写入驱动；ext4 写入禁用"


class UnsupportedWriteError(RuntimeError):
    """当前没有通过准入的 ext4 写入实现，禁止降级。"""


@dataclass(frozen=True)
class Ext4WriteCapabilities:
    write: bool = False
    operations: tuple[str, ...] = ()
    reason: str = EXT4_WRITE_DISABLED


@runtime_checkable
class Ext4WritableAdapter(Protocol):
    """未来驱动适配实现；路径携带稳定分区身份，版本令牌由实现定义。

    实现须在每次变更时重新检查驱动、分区身份、目录范围及权限；
    no-replace 语义不可静默降级，flush 必须由驱动兑现。
    """
    def get_capabilities(self) -> Ext4WriteCapabilities: ...
    def create_dir(self, location: VirtualPath) -> None: ...
    def create_file(self, location: VirtualPath) -> None: ...
    def write_file(self, location: VirtualPath, data: bytes, version: str) -> None: ...
    def rename(self, location: VirtualPath, target: VirtualPath) -> None: ...
    def move(self, location: VirtualPath, target: VirtualPath) -> None: ...
    def delete(self, location: VirtualPath, *, confirmed: bool = False) -> None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class Ext4AdmissionStatus:
    """当前构建的固定状态，不从配置/环境变量推断许可。"""
    enabled: bool = False
    reason: str = EXT4_WRITE_DISABLED
    missing: tuple[str, ...] = (
        "已选择并安装、授权且固定版本的驱动与受控接口",
        "目标 ext4 特征、权限、文件锁及同步语义验证",
        "可丢弃镜像或独立测试盘写入与 Linux 重挂载校验日志",
        "突然中断后的完整性及恢复验证",
        "真实目标备份和恢复证据、用户明确读写选择与风险确认",
        "稳定分区身份及允许的 /home 用户目录白名单复核",
    )


def ext4_admission_status() -> Ext4AdmissionStatus:
    return Ext4AdmissionStatus()
