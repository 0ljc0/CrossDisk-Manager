"""任务00：只验证已有解码逻辑，不访问实际分区。"""
import codecs
import unittest
from preview_utils import decode_preview


class PreviewBaselineTests(unittest.TestCase):
    def test_utf8_and_exact_lf(self):
        text, encoding = decode_preview('Hello from Ubuntu\n中文'.encode('utf-8'))
        self.assertEqual(text, 'Hello from Ubuntu\n中文')
        self.assertEqual(encoding, 'utf-8')

    def test_utf8_bom(self):
        self.assertEqual(decode_preview(codecs.BOM_UTF8 + '中文'.encode())[0], '中文')

    def test_utf16_bom_both_orders(self):
        for bom, encoding in ((codecs.BOM_UTF16_LE, 'utf-16-le'), (codecs.BOM_UTF16_BE, 'utf-16-be')):
            with self.subTest(encoding=encoding):
                self.assertEqual(decode_preview(bom + 'Ubuntu 中文\n'.encode(encoding))[0], 'Ubuntu 中文\n')

    def test_gb18030(self):
        text, encoding = decode_preview('中文预览'.encode('gb18030'))
        self.assertEqual(text, '中文预览')
        self.assertEqual(encoding, 'gb18030')

    def test_empty(self):
        self.assertEqual(decode_preview(b'')[1], 'empty')

    def test_binary_nul(self):
        self.assertEqual(decode_preview(b'\x00\x01\x00\x02')[1], 'binary')

    def test_truncated_utf8_character(self):
        text, encoding = decode_preview(b'hello ' + '中'.encode()[:2])
        self.assertEqual(text, 'hello ')
        self.assertEqual(encoding, 'utf-8')

    def test_line_endings_are_not_converted_by_decoder(self):
        self.assertEqual(decode_preview(b'LF\nCRLF\r\n')[0], 'LF\nCRLF\r\n')


if __name__ == '__main__':
    unittest.main()
