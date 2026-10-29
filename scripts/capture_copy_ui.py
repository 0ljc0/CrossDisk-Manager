"""任务09：镜像 /home 导出到项目内 Windows 临时目录；不访问 Ubuntu 实盘。"""
from dataclasses import asdict
import hashlib
import sys
import tempfile
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app.backends.inventory_browser import InventoryBrowserSource
from app.backends.ext4_readonly import Ext4ReadOnlyBackend
from app.core.copy_job import CopyJob
from app.services.disk_inventory import DiskInventoryService
from app.ui.copy_dialog import CopyDialog


def main():
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project / 'tests'))
    from ext4_fixture import make_image
    application = QApplication([])
    source = InventoryBrowserSource(DiskInventoryService().scan())
    with tempfile.TemporaryDirectory(prefix='copy-validation-', dir=project) as temporary:
        root = Path(temporary)
        destination = root / 'export'
        destination.mkdir()
        native = root / 'native'
        native.mkdir()
        (native / 'sample.txt').write_text('Windows copy validation', encoding='utf-8')
        def request(path):
            location = source.resolve_address(str(path))
            return dict(partition_id=location.partition_id, root=source.roots[location.partition_id],
                        relative_path=location.path, backend_spec=source.request_spec(location.partition_id))
        target = request(destination)
        image = make_image(root / 'image.ext4', include_python=True)
        before = hashlib.sha256(image.read_bytes()).digest()
        # 仅用镜像测试元数据，不将真实候选设备交给后端。
        from test_inventory import parse, sample
        inventory = parse(sample.__wrapped__())
        partition = inventory.partitions[5]
        with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
            fingerprint = backend.probe['fingerprint']
            with backend.open_read('home/demo/script.py') as stream:
                expected = stream.read()
        ext4 = dict(partition_id=partition.id, root='', relative_path='home/demo',
                    backend_spec=dict(kind='ext4', image=str(image), fingerprint=fingerprint,
                                      partition=asdict(partition), disk=asdict(inventory.disks[0])))
        dialog = CopyDialog()
        dialog.enqueue(CopyJob(request(native / 'sample.txt'), target))
        dialog.enqueue(CopyJob(ext4, target))
        for _ in range(3000):
            QTest.qWait(10)
            time.sleep(.01)
            if not dialog.worker:
                break
        assert dialog.worker is None
        assert (destination / 'sample.txt').read_bytes() == (native / 'sample.txt').read_bytes()
        assert (destination / 'demo' / 'script.py').read_bytes() == expected
        assert hashlib.sha256(image.read_bytes()).digest() == before
        dialog.grab().save(str(project / 'docs/screenshots/task09-copy.png'))
        print('Production Volume GUID target: Windows copy and ext4-image /home export passed; hashes unchanged.')
        print('No real Ubuntu partition accessed; temporary destination inside project cleaned.')
        dialog.close()


if __name__ == '__main__':
    main()
