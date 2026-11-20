"""Create a small, valid 1200x1600 PNG strictly for hosting diagnostics.

This file is NEVER submitted to Ozon.
"""
from pathlib import Path
import struct
import zlib

W, H = 1200, 1600
output = Path("photocards/pilot-host-check.png")
output.parent.mkdir(parents=True, exist_ok=True)

def chunk(tag, data):
    crc = zlib.crc32(tag + data) & 0xffffffff
    return struct.pack(">I",len(data)) + tag + data + struct.pack(">I", crc)

row = b"\x00" + b"\xf5\xf2\xea" * W
pixels = row * H
png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(pixels, 9))
       + chunk(b"IEND", b""))
output.write_bytes(png)
print(f"Created {output} ({len(png)} bytes; TEST IMAGE ONLY)")
