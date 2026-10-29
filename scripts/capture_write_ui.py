"""任务10：仅在项目内新建临时目录验收，不写系统或Ubuntu。"""
import logging
import argparse
from contextlib import ExitStack
import ntpath
import os
import tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.backends.inventory_browser import InventoryBrowserSource
from app.backends.windows_native import NativeWindowsBackend
from app.services.disk_inventory import DiskInventoryService
from app.services.windows_write import WriteContext, read_text
from app.ui.write_dialog import WriteDialog
from app.core.capability_policy import CapabilityPolicy
from app.services.windows_write import BLOCKED


def main():
    application = QApplication([])
    project = Path(__file__).resolve().parents[1]
    inventory = DiskInventoryService().scan()
    source = InventoryBrowserSource(inventory)
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-root', default=str(project))
    options = parser.parse_args()
    base = Path(options.test_root)
    base_location = source.resolve_address(str(base))
    base_partition = source.metadata(base_location.partition_id)
    base_disk = next(d for d in inventory.disks if d.id == base_partition.disk_id)
    CapabilityPolicy().require_windows_write(base_partition, base_disk)
    if not base_location.path or any(p.casefold() in BLOCKED for p in base_location.path.split('/')):
        raise ValueError('测试根必须是普通数据目录，不能是卷根或系统目录')
    base_backend = NativeWindowsBackend(base_location.partition_id, source.roots[base_location.partition_id])
    with ExitStack() as guards:
        if not base.exists():
            parent = guards.enter_context(base_backend._guard(base_location.parent.path))
            os.mkdir(ntpath.join(parent, base.name))
        guards.enter_context(base_backend._guard(base_location.path))
        temporary = guards.enter_context(tempfile.TemporaryDirectory(prefix='write-validation-', dir=base))
        directory = Path(temporary)
        location = source.resolve_address(str(directory))
        partition = source.metadata(location.partition_id)
        disk = next(d for d in inventory.disks if d.id == partition.disk_id)
        backend = NativeWindowsBackend(partition.id, partition.volume_path,
                                       write_context=WriteContext(partition, disk, location.path))
        scope = location.path
        backend.create_dir(scope + '/folder')
        backend.create_file(scope + '/note.txt')
        version = read_text(backend, scope + '/note.txt')['version']
        result = backend.write_file(scope + '/note.txt', 'Windows 受控编辑验收\n'.encode(), version)
        assert list(directory.glob('*.bak'))[0].read_bytes() == b''
        backend.rename(scope + '/note.txt', scope + '/renamed.txt')
        backend.move(scope + '/renamed.txt', scope + '/folder/moved.txt')
        assert (directory / 'folder/moved.txt').read_text(encoding='utf-8') == 'Windows 受控编辑验收\n'
        current = read_text(backend, scope + '/folder/moved.txt')
        dialog = WriteDialog(backend)
        dialog.path.setText('folder/moved.txt')
        dialog.text.setPlainText(current['text'])
        dialog.version, dialog.loaded_path = current['version'], scope + '/folder/moved.txt'
        dialog.text.setReadOnly(False)
        dialog.text.document().setModified(False)
        dialog.status.setText(result['message'] + '\n新建/保存/备份/重命名/同卷移动已核对，仅操作指定测试目录的新临时子目录。')
        dialog.show()
        application.processEvents()
        dialog.grab().save(str(project / 'docs/screenshots/task10-write.png'))
        dialog.close()
        backend.delete(scope + '/folder/moved.txt', permanent=True, confirmed=True)
        backend.delete(scope + '/folder', permanent=True, confirmed=True)
        assert not (directory / 'folder').exists()
        print('Production identity/policy/Volume GUID validation: create/save/backup/rename/move/delete passed.')
        print('Only new temporary children of the selected test root written; no Ubuntu access; recycle Shell UI not automated.')


if __name__ == '__main__':
    main()
