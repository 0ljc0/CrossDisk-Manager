"""写入适配选择点；当前构建不注册任何实际 ext4 写驱动。"""
from app.backends.unsupported_write import UnsupportedWriteBackend
from app.core.ext4_write import Ext4WritableAdapter


def get_ext4_write_backend() -> Ext4WritableAdapter:
    # 不接受 driver 名称、盘符、enabled 标志或插件对象作为授权。
    # 将来接入驱动须通过代码审查、独立验证及单独的每次请求准入。
    return UnsupportedWriteBackend()
