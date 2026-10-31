"""CrossDisk Manager 安全的只读文本预览解码工具。"""
from __future__ import annotations

import codecs


def decode_preview(data: bytes) -> tuple[str, str]:
    """解码常见文本编码；不修改原始文件。返回 (文本, 编码说明)。"""
    if not data:
        return '[空文本文件]', 'empty'

    bom_encodings = (
        (codecs.BOM_UTF32_LE, 'utf-32-le'),
        (codecs.BOM_UTF32_BE, 'utf-32-be'),
        (codecs.BOM_UTF8, 'utf-8-sig'),
        (codecs.BOM_UTF16_LE, 'utf-16-le'),
        (codecs.BOM_UTF16_BE, 'utf-16-be'),
    )
    for bom, encoding in bom_encodings:
        if data.startswith(bom):
            payload = data[len(bom):]
            decoder = codecs.getincrementaldecoder(encoding)(errors='replace')
            return decoder.decode(payload, final=False), encoding + ' (BOM)'

    # UTF-16 LE / BE 无 BOM：大量交错的 NUL 通常表示 UTF-16 ASCII 片段。
    sample = data[:min(512, len(data))]
    if b'\x00' in sample:
        even = sample[0::2].count(0)
        odd = sample[1::2].count(0)
        pairs = len(sample) // 2
        candidate_encoding = None
        if pairs >= 3 and odd >= max(3, pairs // 2) and even <= pairs // 10:
            candidate_encoding = 'utf-16-le'
        elif pairs >= 3 and even >= max(3, pairs // 2) and odd <= pairs // 10:
            candidate_encoding = 'utf-16-be'
        if candidate_encoding:
            decoded = codecs.getincrementaldecoder(candidate_encoding)(errors='replace').decode(data, final=False)
            # 含有大量控制字符的结果更可能是二进制，而不是 UTF-16 文本。
            controls = sum(ord(char) < 32 and char not in '\t\r\n' for char in decoded[:512])
            if controls <= max(0, len(decoded[:512]) // 10):
                return decoded, candidate_encoding + '（推断）'
        return '[文件包含 NUL 字节，可能是二进制数据，已取消文本预览]', 'binary'

    # final=False 避免预览上限恰好截断多字节字符导致的编码误判。
    for encoding in ('utf-8', 'gb18030', 'cp1252'):
        try:
            decoder = codecs.getincrementaldecoder(encoding)(errors='strict')
            return decoder.decode(data, final=False), encoding
        except UnicodeDecodeError:
            continue
    return data.decode('latin-1', errors='replace'), 'latin-1（兜底）'
