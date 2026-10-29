"""无 I/O 的拒绝后端；绝不接触 pytsk3、设备、驱动或挂载命令。"""
from app.core.ext4_write import Ext4WriteCapabilities, UnsupportedWriteError


class UnsupportedWriteBackend:
    def get_capabilities(self) -> Ext4WriteCapabilities:
        return Ext4WriteCapabilities()

    def _deny(self):
        raise UnsupportedWriteError(self.get_capabilities().reason)

    def create_dir(self, location):
        self._deny()

    def create_file(self, location):
        self._deny()

    def write_file(self, location, data, version):
        self._deny()

    def rename(self, location, target):
        self._deny()

    def move(self, location, target):
        self._deny()

    def delete(self, location, *, confirmed=False):
        self._deny()

    def flush(self):
        self._deny()

    def close(self):
        pass
