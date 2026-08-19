"""Prepare browser-ready derivatives from the verified B79 ecological outputs.

The source GeoTIFFs remain untouched under F:.  This script creates transparent
PNG overlays and a web-Mercator core-area GeoJSON for the Django static folder.
"""

from pathlib import Path
import json
import math
import shutil

import numpy as np
from PIL import Image
import shapefile


SOURCE_ROOT = Path(r"F:\易智瑞\B79_超图新增数据包")
OUTPUT_ROOT = Path(r"D:\xuan1203-supermap\app_monitor\static\app_monitor\eco")
RESULTS = SOURCE_ROOT / "04_InVEST与融合参考结果"
CORE = SOURCE_ROOT / "03_PCA自然断点核心区"
NODATA = np.float32(-3.4028234663852886e38)
WEB_MERCATOR_RADIUS = 6378137.0


def web_mercator_to_wgs84(x, y):
    longitude = math.degrees(x / WEB_MERCATOR_RADIUS)
    latitude = math.degrees(2 * math.atan(math.exp(y / WEB_MERCATOR_RADIUS)) - math.pi / 2)
    return longitude, latitude


def world_bounds(tfw_path, width, height):
    values = [float(value.strip()) for value in tfw_path.read_text(encoding="ascii").splitlines()]
    x_size, _, _, y_size, center_x, center_y = values
    min_x = center_x - x_size / 2
    max_y = center_y - y_size / 2
    max_x = min_x + width * x_size
    min_y = max_y + height * y_size
    west, south = web_mercator_to_wgs84(min_x, min_y)
    east, north = web_mercator_to_wgs84(max_x, max_y)
    return [west, south, east, north]


def normalize(values, valid):
    low, high = np.percentile(values[valid], [2, 98])
    if high <= low:
        high = low + 1
    return np.clip((values - low) / (high - low), 0, 1)


def colorize(values, palette):
    valid = np.isfinite(values) & (values > NODATA / 10)
    normalized = normalize(values, valid)
    stops = np.asarray(palette, dtype=np.float32)
    positions = np.linspace(0, 1, len(stops))
    output = np.zeros((*values.shape, 4), dtype=np.uint8)
    for channel in range(3):
        output[..., channel] = np.interp(normalized, positions, stops[:, channel]).astype(np.uint8)
    output[..., 3] = np.where(valid, 182, 0).astype(np.uint8)
    return output


def export_raster(name, palette):
    source = RESULTS / f"{name}.tif"
    with Image.open(source) as image:
        values = np.asarray(image, dtype=np.float32)
        world_file = source.with_suffix(".tfw")
        # Habitat quality shares the aligned B79 reference grid but stores its
        # georeference internally rather than beside the TIFF.
        if not world_file.exists():
            world_file = RESULTS / "redline_score_spring.tfw"
        bounds = world_bounds(world_file, image.width, image.height)
    rgba = colorize(values, palette)
    Image.fromarray(rgba, mode="RGBA").save(OUTPUT_ROOT / f"{name}.png", optimize=True)
    return {"name": name, "url": f"/static/app_monitor/eco/{name}.png", "bounds": bounds}


def export_core_geojson():
    reader = shapefile.Reader(str(CORE / "pca_high_suitability_high_aggregation_core.shp"))
    fields = [field[0] for field in reader.fields[1:]]
    features = []
    for shape_record in reader.iterShapeRecords():
        shape = shape_record.shape
        record = dict(zip(fields, shape_record.record))
        parts = list(shape.parts) + [len(shape.points)]
        rings = []
        for index in range(len(parts) - 1):
            ring = [list(web_mercator_to_wgs84(x, y)) for x, y in shape.points[parts[index]:parts[index + 1]]]
            if ring:
                rings.append(ring)
        if rings:
            features.append({
                "type": "Feature",
                "properties": {"source": "B79 PCA natural-breaks core area", **record},
                "geometry": {"type": "Polygon", "coordinates": rings},
            })
    payload = {"type": "FeatureCollection", "features": features}
    (OUTPUT_ROOT / "pca_core_area.geojson").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return len(features)


def copy_reference_inputs():
    for filename in (
        "quality_c_ref.tif",
        "redline_score_spring.tif", "redline_score_summer.tif",
        "redline_score_autumn.tif", "redline_score_winter.tif",
        "gizscore_spring.tif", "gizscore_summer.tif",
        "gizscore_autumn.tif", "gizscore_winter.tif",
    ):
        source = RESULTS / filename
        destination = OUTPUT_ROOT / "source" / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main():
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    palettes = {
        # InVEST Habitat Quality is displayed with the high-value end in
        # blue/green and the low-value end in yellow/orange/red.
        "quality_c_ref": [(239, 76, 47), (255, 232, 94), (187, 215, 121), (108, 184, 168), (59, 163, 205)],
        "redline_score_spring": [(45, 38, 88), (66, 123, 184), (98, 190, 165), (245, 205, 83), (208, 54, 57)],
        "redline_score_summer": [(45, 38, 88), (66, 123, 184), (98, 190, 165), (245, 205, 83), (208, 54, 57)],
        "redline_score_autumn": [(45, 38, 88), (66, 123, 184), (98, 190, 165), (245, 205, 83), (208, 54, 57)],
        "redline_score_winter": [(45, 38, 88), (66, 123, 184), (98, 190, 165), (245, 205, 83), (208, 54, 57)],
    }
    catalog = {name: export_raster(name, palette) for name, palette in palettes.items()}
    catalog["core_feature_count"] = export_core_geojson()
    catalog["core_area_km2"] = 103.1
    (OUTPUT_ROOT / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    copy_reference_inputs()
    print(json.dumps(catalog, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
