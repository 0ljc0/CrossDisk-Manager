"""所有后端异常转换为同一种可展示的中文消息。"""

from app.backends.ext4_readonly import Ext4Error
from app.backends.windows_native import readable_error
from app.core.inventory import InventoryError


def user_message(error: BaseException) -> str:
    if isinstance(error, (Ext4Error, InventoryError)):
        return str(error)
    if isinstance(error, (OSError, ValueError)):
        return readable_error(error)
    return "只读操作失败，请刷新后重试。"
