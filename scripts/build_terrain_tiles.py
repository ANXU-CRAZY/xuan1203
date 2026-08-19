# -*- coding: utf-8 -*-
"""Generate Cesium quantized-mesh terrain tiles (zip-packed .terrainz)
from the Copernicus GLO30 DEM GeoTIFFs, served locally to the SuperMap3D SDK
via SuperMapTerrainProvider(isSct=True), bypassing iServer entirely.

Geographic tiling (Level0=180deg, 2x1 at L0):
  x = (lng + 180) / 180 * 2^L        (0 at -180)
  y = (lat + 90)  / 180 * 2^L        (0 at south pole, matches SDK flipped row)
Tile size at level L: 180 / 2^L degrees.
"""
import os
import struct
import zlib
import math
import numpy as np
import tifffile

SRC_DIR = r"F:\supermap\02-Data\YellowRiverEcology_DEM_GLO30"
OUT_DIR = r"D:\xuan1203-supermap\data\local_terrain"
LON0, LON1 = 112.5, 115.1
LAT0, LAT1 = 34.2, 35.9
MAX_LEVEL = 10

TILE_VERTS = 65  # 65x65 grid per tile
E2 = 6.69437999014e-3
A = 6378137.0


def ecef(lon_deg, lat_deg, h):
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    n = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
    x = (n + h) * math.cos(lat) * math.cos(lon)
    y = (n + h) * math.cos(lat) * math.sin(lon)
    z = (n * (1 - E2) + h) * math.sin(lat)
    return x, y, z


def load_sources():
    """Return list of (DEM array 3601x3601 float64, lon0, lat0)."""
    sources = []
    for lat in (34, 35):
        for lon in (112, 113, 114, 115):
            name = f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif"
            path = os.path.join(SRC_DIR, name)
            if not os.path.exists(path):
                continue
            data = tifffile.imread(path, key=0)
            sources.append((np.asarray(data, dtype=np.float64), float(lon), float(lat)))
            print("loaded", name)
    return sources


def sample_dem(sources, lons, lats):
    """Bilinear sample DEM heights (float32) at lons/lats (meshgrid arrays)."""
    h = np.full(lons.shape, np.nan, dtype=np.float64)
    for data, slon, slat in sources:
        # source tile covers [slon, slon+1] x [slat, slat+1], 3601x3601 px
        lon_ok = (lons >= slon - 1e-9) & (lons < slon + 1 + 1e-9)
        lat_ok = (lats >= slat - 1e-9) & (lats < slat + 1 + 1e-9)
        mask = lon_ok & lat_ok
        if not mask.any():
            continue
        # fractional pixel coordinates
        fx = (lons - slon) * 3600.0
        fy = (1 - (lats - slat)) * 3600.0  # row 0 = north
        x0 = np.floor(fx).astype(np.int64)
        y0 = np.floor(fy).astype(np.int64)
        x0 = np.clip(x0, 0, 3599)
        y0 = np.clip(y0, 0, 3599)
        x1 = np.clip(x0 + 1, 0, 3599)
        y1 = np.clip(y0 + 1, 0, 3599)
        tx = fx - x0
        ty = fy - y0
        # read the 4 needed rows per column-set: read full columns window rows
        # (COG zarr supports window reads)
        cols = np.unique(np.concatenate([x0, x1]))
        rows = np.unique(np.concatenate([y0, y1]))
        data = data[rows.min():rows.max() + 1, cols.min():cols.max() + 1]
        row_idx0 = y0 - rows.min()
        row_idx1 = y1 - rows.min()
        col_idx0 = x0 - cols.min()
        col_idx1 = x1 - cols.min()
        v00 = data[row_idx0, col_idx0]
        v01 = data[row_idx0, col_idx1]
        v10 = data[row_idx1, col_idx0]
        v11 = data[row_idx1, col_idx1]
        val = (v00 * (1 - tx) * (1 - ty) + v01 * tx * (1 - ty)
               + v10 * (1 - tx) * ty + v11 * tx * ty)
        val[val < -10000] = np.nan
        h[mask] = val[mask]
        del data
    return h


def zz(x):
    """zigzag encode a signed value into an unsigned int (fits uint16)."""
    return x * 2 if x >= 0 else -x * 2 - 1


def encode_tile(heights, lon0, lat1, tile_w):
    """Encode a 65x65 height grid into the SuperMap quantized-mesh variant
    consumed by the SDK's createQuantizedMeshTerrainData:
    - header: center, minH/maxH, sphere, HOP, vertexCount
    - vertices: u,v,h zigzag-delta encoded (uint16)
    - pad to 2 bytes, indexCount, indices ue-Ae encoded (uint16)
    - edge sections: count + raw uint16 values (west, south, east, north)
    """
    h = np.asarray(heights, dtype=np.float64)
    good = np.isfinite(h)
    if good.any():
        hmin = float(h[good].min())
        hmax = float(h[good].max())
    else:
        hmin = hmax = 0.0
    if hmax - hmin < 1.0:
        hmax = hmin + 1.0
    h = np.where(good, h, hmin)

    u = np.clip(np.round(np.linspace(0, 1, TILE_VERTS) * 32767), 0, 32767).astype(np.int64)
    # Quantized-mesh uses v=0 at the south edge and v=32767 at the north edge.
    # Our source rows run north->south, so v must decrease as the row increases.
    v = np.clip(np.round(np.linspace(1, 0, TILE_VERTS) * 32767), 0, 32767).astype(np.int64)
    hq = np.clip(np.round((h - hmin) / (hmax - hmin) * 32767), 0, 32767).astype(np.int64)

    verts_u = np.tile(u, TILE_VERTS)
    verts_v = np.repeat(v, TILE_VERTS)
    verts_h = hq.reshape(-1)

    # indices: winding matches the SDK's own flat-tile pattern
    idx = []
    for r in range(TILE_VERTS - 1):
        for c in range(TILE_VERTS - 1):
            a = r * TILE_VERTS + c
            d = (r + 1) * TILE_VERTS + c
            b = (r + 1) * TILE_VERTS + c + 1
            e = r * TILE_VERTS + c + 1
            idx += [a, b, e, d, b, a]
    indices = np.array(idx, dtype=np.int64)

    # Quantized-mesh edge order is significant because the renderer builds
    # skirts from these sequences: west S->N, south E->W, east N->S,
    # north W->E.
    edges = [
        np.arange((TILE_VERTS - 1) * TILE_VERTS, -1, -TILE_VERTS, dtype=np.int64),
        np.arange(TILE_VERTS * TILE_VERTS - 1, (TILE_VERTS - 1) * TILE_VERTS - 1, -1, dtype=np.int64),
        np.arange(TILE_VERTS - 1, TILE_VERTS * TILE_VERTS, TILE_VERTS, dtype=np.int64),
        np.arange(0, TILE_VERTS, dtype=np.int64),
    ]

    clon = lon0 + tile_w / 2
    clat = lat1 - tile_w / 2
    cx, cy, cz = ecef(clon, clat, (hmin + hmax) / 2)
    hw = tile_w * math.cos(math.radians(clat)) * math.pi / 180 * A
    radius = math.hypot(hw, hw) + (hmax - hmin)
    hop = ecef(clon, clat, hmax)

    buf = bytearray()
    buf += struct.pack('<ddd', cx, cy, cz)
    buf += struct.pack('<ff', hmin, hmax)
    buf += struct.pack('<ddd', cx, cy, cz)
    buf += struct.pack('<d', radius)
    buf += struct.pack('<ddd', *hop)
    n_vert = TILE_VERTS * TILE_VERTS
    buf += struct.pack('<I', n_vert)

    def zigzag_delta_encode(values):
        out = np.empty(len(values), dtype=np.uint16)
        prev = 0
        for i, val in enumerate(values):
            d = int(val) - prev
            out[i] = zz(d) & 0xFFFF
            prev = int(val)
        return out

    # vertices: 平面布局(先全部 u,再全部 v,再全部 h),SDK 按三段 subarray 读取
    vu = zigzag_delta_encode(verts_u)
    vv = zigzag_delta_encode(verts_v)
    vh = zigzag_delta_encode(verts_h)
    vbuf = np.concatenate([vu, vv, vh])
    buf += vbuf.tobytes()

    # indices: ue-Ae encoding
    # SDK's d_e decoder reads ie as TRIANGLE count, then multiplies by 3
    # to get total index count: se = createTypedArray(O, buf, C, ie*3)
    ie_tri = len(indices) // 3
    buf += struct.pack('<I', ie_tri)
    ienc = np.empty(len(indices), dtype=np.uint16)
    ue = 0
    for i, orig in enumerate(indices):
        a = (ue - int(orig)) & 0xFFFF
        ienc[i] = a
        if a == 0:
            ue += 1
    buf += ienc.tobytes()

    # edge sections: count + raw values
    for edge in edges:
        buf += struct.pack('<I', len(edge))
        buf += edge.astype(np.uint16).tobytes()

    return bytes(buf)


def main():
    sources = load_sources()
    print("sources:", len(sources))
    for s in sources:
        print(" ", s[0])

    total = 0
    for level in range(MAX_LEVEL + 1):
        n = 2 ** level
        tile_w = 180.0 / n
        # south-based row: y = (lat+90)/180*n ; x = (lng+180)/180*n
        x0 = max(0, int((LON0 + 180) / 180 * n))
        x1 = min(2 * n - 1, int((LON1 + 180) / 180 * n))
        y0 = max(0, int((LAT0 + 90) / 180 * n))
        y1 = min(n - 1, int((LAT1 + 90) / 180 * n))
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                lon0 = x * tile_w - 180
                lat0 = y * tile_w - 90
                lons = lon0 + np.linspace(0, tile_w, TILE_VERTS)
                lats = lat0 + tile_w - np.linspace(0, tile_w, TILE_VERTS)  # north->south
                lg, lt = np.meshgrid(lons, lats)
                h = sample_dem(sources, lg, lt)
                if not np.isfinite(h).any():
                    continue
                tile = encode_tile(h, lon0, lat0 + tile_w, tile_w)
                zdir = os.path.join(OUT_DIR, str(level), str(x))
                os.makedirs(zdir, exist_ok=True)
                zpath = os.path.join(zdir, f"{y}.terrainz")
                # SDK 的 UnZipTerrainData worker 使用 zlib inflate,必须输出 zlib 流
                with open(zpath, 'wb') as fh:
                    fh.write(zlib.compress(tile))
                total += 1
                if total % 25 == 0:
                    print(f"level {level}: {total} tiles...")
    print("DONE, total tiles:", total)


if __name__ == '__main__':
    main()
