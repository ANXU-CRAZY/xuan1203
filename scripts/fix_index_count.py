# -*- coding: utf-8 -*-
"""Fix the index count field in existing terrain tiles.

The SDK's d_e decoder expects ie = triangle_count (len/3),
but the build script wrote ie = total_index_count.
This script patches each tile: reads ie, divides by 3, rewrites.
"""
import os
import struct
import zlib

TERRAIN_DIR = r"D:\xuan1203-supermap\data\local_terrain"
fixed = 0
skipped = 0
errors = 0

for root, dirs, files in os.walk(TERRAIN_DIR):
    for fname in files:
        if not fname.endswith('.terrainz'):
            continue
        fpath = os.path.join(root, fname)
        try:
            with open(fpath, 'rb') as f:
                raw = f.read()
            data = bytearray(zlib.decompress(raw))

            # Header: center(24) + minH(4) + maxH(4) + BS(32) + HOP(24) + vertexCount(4) = 92
            if len(data) < 92:
                skipped += 1
                continue
            off = 88
            nvert = struct.unpack_from('<I', data, off)[0]
            off = 92  # after header

            # Vertices: nvert * 3 uint16 = nvert * 6 bytes
            off += nvert * 6

            # Align to 2 bytes
            if off % 2 != 0:
                off += 1

            # Index count field (should be triangle count = total/3)
            if off + 4 > len(data):
                skipped += 1
                continue
            ie = struct.unpack_from('<I', data, off)[0]

            # Check if already fixed (triangle count < 65536 for our tiles)
            # Total indices for 65x65 = 24576, triangle count = 8192
            if ie == 24576:
                # Patch to triangle count
                struct.pack_into('<I', data, off, 8192)
                # Recompress
                compressed = zlib.compress(bytes(data))
                with open(fpath, 'wb') as f:
                    f.write(compressed)
                fixed += 1
            elif ie == 8192:
                skipped += 1  # already fixed
            else:
                # Unknown ie value, log it
                print(f"  SKIP {fpath}: ie={ie} (expected 24576 or 8192)")
                skipped += 1
        except Exception as e:
            print(f"  ERROR {fpath}: {e}")
            errors += 1

print(f"\nFixed: {fixed}, Already OK: {skipped}, Errors: {errors}")
