"""完全基于模拟分区记录和临时目录的测试，不碰真实磁盘。"""
import tempfile
import unittest
from pathlib import Path

from fs_adapters import ReadOnlyMountedAdapter
from volume_links import DriveInfo, drive_mode_text, resolve_verified_links


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.parts = [
            {'disk_number': 0, 'partition_number': 3, 'offset': 1000000,
             'size': 3000000, 'drive_letter': 'C', 'access_paths': ['C:\\']},
            {'disk_number': 0, 'partition_number': 6, 'offset': 9000000,
             'size': 16000000, 'drive_letter': '', 'access_paths': []},
        ]

    def test_match_physical_extent(self):
        drives = [DriveInfo('E:\\', filesystem='EXT4', extent=(0, 9000000, 16000000))]
        self.assertEqual(resolve_verified_links(self.parts, drives)[(0, 6)][0], 'E:\\')

    def test_no_guess_by_drive_letter_or_volume_type(self):
        drives = [DriveInfo('E:\\', filesystem='EXT4', label='Ubuntu')]
        self.assertNotIn((0, 6), resolve_verified_links(self.parts, drives))

    def test_partition_reported_drive_letter(self):
        drives = [DriveInfo('C:\\', filesystem='NTFS')]
        self.assertEqual(resolve_verified_links(self.parts, drives)[(0, 3)][0], 'C:\\')

    def test_extent_conflict_overrides_drive_letter(self):
        drives = [DriveInfo('C:\\', filesystem='NTFS', extent=(0, 9000000, 16000000))]
        self.assertNotIn((0, 3), resolve_verified_links(self.parts, drives))
        self.assertIn((0, 6), resolve_verified_links(self.parts, drives))

    def test_ambiguity_rejected(self):
        drives = [DriveInfo('E:\\', extent=(0, 9000000, 16000000)),
                  DriveInfo('F:\\', extent=(0, 9000000, 16000000))]
        self.assertNotIn((0, 6), resolve_verified_links(self.parts, drives))

    def test_invalid_length_rejected(self):
        drives = [DriveInfo('E:\\', extent=(0, 9000000, 16000001))]
        self.assertNotIn((0, 6), resolve_verified_links(self.parts, drives))

    def test_file_system_flag_is_not_write_claim(self):
        self.assertIn('不代表实际可写', drive_mode_text(DriveInfo('E:\\', read_only_flag=False)))


class AdapterTests(unittest.TestCase):
    def test_read_only_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'test.txt').write_bytes(b'Hello from Ubuntu\n')
            adapter = ReadOnlyMountedAdapter(root)
            files, truncated = adapter.list_dir(root)
            self.assertFalse(truncated)
            self.assertEqual([e.name for e in files], ['test.txt'])
            self.assertEqual(adapter.read_bytes(root / 'test.txt', 1024), b'Hello from Ubuntu\n')
            self.assertFalse(adapter.capabilities.edit)
            self.assertFalse(adapter.capabilities.delete)
            with self.assertRaises(PermissionError):
                adapter.write_file(root / 'test.txt', b'changed')
            with self.assertRaises(PermissionError):
                adapter.delete_file(root / 'test.txt')
            self.assertEqual((root / 'test.txt').read_text(encoding='utf-8'), 'Hello from Ubuntu\n')

    def test_outside_root_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'volume'
            folder.mkdir()
            adapter = ReadOnlyMountedAdapter(folder)
            with self.assertRaises(PermissionError):
                adapter.list_dir(Path(temp))


if __name__ == '__main__':
    unittest.main()
