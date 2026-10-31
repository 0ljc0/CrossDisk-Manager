"""任务00只读Qt基线验收；测试样本仅在TemporaryDirectory内生成。

不改变业务代码，不挂载/卸载E盘，不写Ubuntu；测试替身仅接管消息框。
"""
import ctypes
import hashlib
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QTreeWidgetItemIterator
from main import CrossDiskWindow
from storage_scan import is_protected_partition
from volume_links import drive_mode_text


def main():
    application = QApplication.instance() or QApplication([])
    project = Path(__file__).resolve().parent
    output = project / 'docs/test_reports'
    output.mkdir(parents=True, exist_ok=True)
    result = dict(administrator=bool(ctypes.windll.shell32.IsUserAnAdmin()), checks=[], warnings=[])
    warnings = result['warnings']
    def message(parent, title, text, *args, **kwargs):
        warnings.append(dict(title=title, text=str(text)))
        return QMessageBox.StandardButton.No
    with patch.object(QMessageBox, 'warning', message), patch.object(QMessageBox, 'information', message):
        window = CrossDiskWindow()
        window.show()
        def wait_scan():
            started = time.monotonic()
            while window.scanner and window.scanner.isRunning():
                QTest.qWait(20)
                time.sleep(.01)
                if time.monotonic() - started > 65:
                    raise RuntimeError('扫描超过验收等待上限')
            QTest.qWait(100)
            if window.scan_error or not window.storage_data:
                raise RuntimeError('实机扫描失败：' + window.scan_error)
        try:
            wait_scan()
            result['checks'].append('real-gui-start-and-scan')
            result['disks'] = window.storage_data['disks']
            result['partitions'] = window.storage_data['partitions']
            result['drives'] = [dict(root=d.root, filesystem=d.filesystem, extent=d.extent,
                                     extent_note=d.extent_note, mode=drive_mode_text(d)) for d in window.drive_probes]
            result['links'] = [dict(disk=k[0], partition=k[1], root=v[0], evidence=v[1]) for k, v in window.verified_links.items()]
            for root in ('C:\\', 'D:\\'):
                window.path_edit.setText(root)
                window.go_to_address()
                if window.current_path != Path(root):
                    raise AssertionError('无法浏览 ' + root)
            result['checks'].append('C-D-address-navigation')
            iterator = QTreeWidgetItemIterator(window.navigation)
            count = 0
            while iterator.value():
                item = iterator.value()
                kind, data = item.data(0, Qt.ItemDataRole.UserRole) or ('', None)
                if kind == 'partition' and is_protected_partition(data):
                    count += 1
                    window.navigation.setCurrentItem(item)
                    window.navigation_clicked(item, 0)
                    window.associate_selected_partition()
                    assert warnings[-1]['title'] == '受保护分区'
                iterator += 1
            assert count >= 3
            result['protected_partitions_checked'] = count
            result['checks'].append('protected-partitions-reject-association')
            with tempfile.TemporaryDirectory(prefix='crossdisk-baseline-') as temp:
                folder = Path(temp)
                txt = folder / '中文.txt'
                txt.write_bytes(b'Hello from Ubuntu\n')
                (folder / 'sample.py').write_bytes(b'# preview only\nprint(123)\n')
                image = QImage(8, 8, QImage.Format.Format_RGB32)
                image.fill(0x225588)
                assert image.save(str(folder / 'sample.png'))
                original_hash = hashlib.sha256(txt.read_bytes()).hexdigest()
                window.open_dir(folder)
                for name in ('中文.txt', 'sample.py', 'sample.png'):
                    row = next(r for r in range(window.files.rowCount()) if window.files.item(r, 0).text() == name)
                    window.preview_row(row)
                    if name.endswith('.png'):
                        assert window.preview_stack.currentIndex() == 1
                    else:
                        assert 'Hello from Ubuntu' in window.preview_text.toPlainText() if name.endswith('.txt') else 'print(123)' in window.preview_text.toPlainText()
                assert original_hash == hashlib.sha256(txt.read_bytes()).hexdigest()
                result['checks'].append('temporary-txt-code-image-previews-and-unchanged-hash')
                window.refresh()
                wait_scan()
                assert window.current_path == folder
                result['checks'].append('refresh-preserves-current-directory')
                window.open_dir(project)
            # 只读查看任务指定的既有Ubuntu样本，不创建或修改E盘文件。
            if Path('E:\\').is_dir():
                window.open_dir(Path('E:\\'))
                assert window.current_path == Path('E:\\')
                sample = Path(r'E:\home\ljc\CrossDisk_Test\test.txt')
                if sample.is_file():
                    window.open_dir(sample.parent)
                    row = next(r for r in range(window.files.rowCount()) if window.files.item(r, 0).text() == sample.name)
                    before = hashlib.sha256(sample.read_bytes()).hexdigest()
                    window.preview_row(row)
                    after = hashlib.sha256(sample.read_bytes()).hexdigest()
                    assert before == after
                    result['ubuntu_sample'] = dict(status='readonly-preview-hash-unchanged', sha256=after,
                                                  linux_reference_hash_available=False)
                else:
                    result['ubuntu_sample'] = dict(status='mounted-but-task-sample-missing')
            else:
                result['ubuntu_sample'] = dict(status='E-not-mounted-skipped')
            window.open_dir(project)
            application.processEvents()
            window.grab().save(str(output / 'V0.3.1_基线界面.png'))
        finally:
            if window.scanner and window.scanner.isRunning():
                window.scanner.wait(65000)
            window.close()
            application.processEvents()
    (output / 'V0.3.1_实机自动检查.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
