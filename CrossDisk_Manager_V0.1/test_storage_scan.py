"""不访问实际磁盘的分区信息解析单元测试。"""
import unittest
from storage_scan import decode_output, normalize_payload, partition_kind, is_protected_partition


class StorageInfoTests(unittest.TestCase):
    def test_normalize_single(self):
        data = normalize_payload({
            'disks': {'number': 0},
            'partitions': {'disk_number': 0, 'partition_number': 6},
        })
        self.assertEqual(len(data['disks']), 1)
        self.assertEqual(data['partitions'][0]['partition_number'], 6)

    def test_linux_partition_not_guessed_ext4(self):
        part = {'type': 'Unknown', 'gpt_type': '{0FC63DAF-8483-4772-8E79-3D69D8477DE4}'}
        self.assertEqual(partition_kind(part), 'Linux 文件系统分区')
        self.assertFalse(is_protected_partition(part))

    def test_protected_partition(self):
        self.assertTrue(is_protected_partition({'type': 'Reserved'}))
        self.assertTrue(is_protected_partition({'type': 'Recovery'}))
        self.assertTrue(is_protected_partition({'gpt_type': 'C12A7328-F81F-11D2-BA4B-00A0C93EC93B'}))

    def test_english_windows_text(self):
        self.assertEqual(decode_output('磁盘 0'.encode('utf-8')), '磁盘 0')

    def test_invalid_payload(self):
        with self.assertRaises(ValueError):
            normalize_payload(['invalid'])


if __name__ == '__main__':
    unittest.main()
