"""Prepare fixed scene labels; administrative boundaries remain a web overlay."""

import json
from pathlib import Path

WORK_DIR = Path(r"D:\xuan1203-supermap\work\YellowRiverEcology3D")
LABELS_FILE = WORK_DIR / "Ecology_Annotations_ascii.geojson"


def write_labels():
    # Keep source JSON ASCII so strict desktop importers cannot misread Chinese text.
    items = (
        ("Yellow River", "river", 113.7200, 34.9150),
        ("Taihang Mountains", "mountain", 113.1900, 35.4200),
        ("Songshan", "mountain", 112.9500, 34.4800),
        # Zhengzhou Mangshan lies in Huiji District on the south bank of the Yellow River.
        ("Mangshan", "mountain", 113.5700, 34.9550),
        ("Zhengzhou", "city", 113.6250, 34.7460),
        ("Jiaozuo", "city", 113.2420, 35.2150),
        ("Xinxiang", "city", 113.9260, 35.3030),
    )
    features = [
        {
            "type": "Feature",
            "properties": {"name": name, "label": name, "category": category},
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        }
        for name, category, longitude, latitude in items
    ]
    LABELS_FILE.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=True),
        encoding="ascii",
    )
    print("LABELS", LABELS_FILE)


if __name__ == "__main__":
    write_labels()
