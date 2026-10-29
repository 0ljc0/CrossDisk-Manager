"""合成单组、无日志、extent ext4 测试镜像；仅写普通临时文件，绝不格式化设备。"""

import struct
from pathlib import Path


SAMPLE = "CrossDisk ext4 只读样本\n".encode("utf-8")


def make_image(path: Path) -> Path:
    data = bytearray(4 * 1024 * 1024)
    sb = memoryview(data)[1024:2048]
    def u32(where, value):
        struct.pack_into("<I", sb, where, value)
    for where, value in ((0, 128), (4, 4096), (12, 4000), (16, 110), (20, 1),
                         (24, 0), (28, 0), (32, 8192), (36, 8192), (40, 128),
                         (76, 1), (84, 11), (96, 0x42)):
        u32(where, value)
    struct.pack_into("<HH", sb, 56, 0xef53, 1)
    struct.pack_into("<H", sb, 88, 256)
    sb[104:120] = bytes.fromhex("0123456789abcdef0123456789abcdef")
    sb[120:129] = b"CDM-TEST\0"
    struct.pack_into("<IIIHHH", data, 2048, 3, 4, 5, 4000, 110, 3)
    data[3072:3584] = b"\xff" * 512
    data[4096:4112] = b"\xff" * 16
    def inode(number, mode, size, block=None, target=b""):
        position = 5 * 1024 + (number - 1) * 256
        struct.pack_into("<H", data, position, mode)
        struct.pack_into("<IIII", data, position + 4, size, 1700000000, 1700000000, 1700000000)
        struct.pack_into("<H", data, position + 26, 2 if mode & 0xf000 == 0x4000 else 1)
        struct.pack_into("<I", data, position + 28, 2 if block else 0)
        if block:
            struct.pack_into("<I", data, position + 32, 0x80000)
            struct.pack_into("<HHHHI", data, position + 40, 0xf30a, 1, 4, 0, 0)
            struct.pack_into("<IHHI", data, position + 52, 0, 1, 0, block)
        else:
            data[position + 40:position + 40 + len(target)] = target
    def directory(block, entries):
        position = block * 1024
        used = 0
        for index, (number, name, kind) in enumerate(entries):
            raw = name if isinstance(name, bytes) else name.encode("utf-8")
            length = ((8 + len(raw) + 3) // 4) * 4 if index < len(entries) - 1 else 1024 - used
            struct.pack_into("<IHBB", data, position + used, number, length, len(raw), kind)
            data[position + used + 8:position + used + 8 + len(raw)] = raw
            used += length
    inode(2, 0x41ed, 1024, 40)
    inode(12, 0x41ed, 1024, 41)
    inode(13, 0x41ed, 1024, 42)
    inode(14, 0x81a4, len(SAMPLE), 43)
    inode(15, 0x81a4, 3, 44)
    inode(16, 0x81a4, 3, 45)
    inode(17, 0xa1ff, len(b"../demo"), target=b"../demo")
    directory(40, [(2, ".", 2), (2, "..", 2), (12, "home", 2)])
    directory(41, [(12, ".", 2), (2, "..", 2), (13, "demo", 2)])
    directory(42, [(13, ".", 2), (12, "..", 2), (14, "sample.txt", 1),
                   (15, "中文 空格.txt", 1), (16, ".hidden", 1), (17, "loop", 7)])
    data[43 * 1024:43 * 1024 + len(SAMPLE)] = SAMPLE
    data[44 * 1024:44 * 1024 + 3] = b"abc"
    data[45 * 1024:45 * 1024 + 3] = b"xyz"
    path.write_bytes(data)
    return path
