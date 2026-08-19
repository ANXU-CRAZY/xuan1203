# -*- coding: utf-8 -*-
"""Repair v orientation and edge ordering in generated SuperMap terrain tiles."""

import os
import struct
import tempfile
import zlib

import numpy as np


TERRAIN_DIR = r"D:\xuan1203-supermap\data\local_terrain"
TILE_VERTS = 65
VERTEX_COUNT = TILE_VERTS * TILE_VERTS
TRIANGLE_COUNT = (TILE_VERTS - 1) * (TILE_VERTS - 1) * 2
INDEX_COUNT = TRIANGLE_COUNT * 3


def zigzag(value):
    return value * 2 if value >= 0 else -value * 2 - 1


def encode_delta(values):
    output = np.empty(len(values), dtype=np.uint16)
    previous = 0
    for index, value in enumerate(values):
        current = int(value)
        output[index] = zigzag(current - previous) & 0xFFFF
        previous = current
    return output.tobytes()


v_rows = np.clip(
    np.round(np.linspace(1, 0, TILE_VERTS) * 32767),
    0,
    32767,
).astype(np.int64)
encoded_v = encode_delta(np.repeat(v_rows, TILE_VERTS))

edges = [
    np.arange((TILE_VERTS - 1) * TILE_VERTS, -1, -TILE_VERTS, dtype=np.uint16),
    np.arange(VERTEX_COUNT - 1, (TILE_VERTS - 1) * TILE_VERTS - 1, -1, dtype=np.uint16),
    np.arange(TILE_VERTS - 1, VERTEX_COUNT, TILE_VERTS, dtype=np.uint16),
    np.arange(0, TILE_VERTS, dtype=np.uint16),
]


def repair_tile(path):
    with open(path, 'rb') as source:
        data = bytearray(zlib.decompress(source.read()))

    if len(data) < 92:
        raise ValueError('tile header is truncated')
    vertex_count = struct.unpack_from('<I', data, 88)[0]
    if vertex_count != VERTEX_COUNT:
        raise ValueError(f'unexpected vertex count {vertex_count}')

    vertex_start = 92
    v_start = vertex_start + vertex_count * 2
    v_end = v_start + vertex_count * 2
    data[v_start:v_end] = encoded_v

    index_count_offset = vertex_start + vertex_count * 6
    triangle_count = struct.unpack_from('<I', data, index_count_offset)[0]
    if triangle_count != TRIANGLE_COUNT:
        raise ValueError(f'unexpected triangle count {triangle_count}')

    edge_offset = index_count_offset + 4 + INDEX_COUNT * 2
    for edge in edges:
        count = struct.unpack_from('<I', data, edge_offset)[0]
        if count != TILE_VERTS:
            raise ValueError(f'unexpected edge count {count}')
        edge_offset += 4
        data[edge_offset:edge_offset + count * 2] = edge.tobytes()
        edge_offset += count * 2

    if edge_offset != len(data):
        raise ValueError(f'unconsumed bytes: {len(data) - edge_offset}')

    compressed = zlib.compress(bytes(data))
    directory = os.path.dirname(path)
    descriptor, temporary_path = tempfile.mkstemp(prefix='.terrain-fix-', dir=directory)
    try:
        with os.fdopen(descriptor, 'wb') as target:
            target.write(compressed)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def main():
    repaired = 0
    for root, _, files in os.walk(TERRAIN_DIR):
        for filename in files:
            if not filename.endswith('.terrainz'):
                continue
            repair_tile(os.path.join(root, filename))
            repaired += 1
    print(f'Repaired terrain tiles: {repaired}')


if __name__ == '__main__':
    main()
