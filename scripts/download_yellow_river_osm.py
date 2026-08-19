"""Download Yellow River main-channel ways for the three-city study area."""

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import Request, urlopen


out = Path(r"D:\xuan1203-supermap\work\YellowRiverEcology3D\YellowRiver_MainChannel.geojson")
query = '[out:json][timeout:90];way["waterway"="river"]["name"="\\u9ec4\\u6cb3"](34.2,112.5,35.9,115.1);out geom;'
endpoints = (
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
payload = None
for endpoint in endpoints:
    request = Request(
        endpoint,
        data=urlencode({"data": query}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "User-Agent": "YellowRiverEcology/1.0"},
    )
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.load(response)
        print("DOWNLOADED_FROM", endpoint)
        break
    except (URLError, TimeoutError, OSError) as exc:
        print("ENDPOINT_FAILED", endpoint, exc)

if payload is None:
    raise RuntimeError("All Overpass endpoints timed out or failed")

features = []
for element in payload.get("elements", []):
    geometry = element.get("geometry") or []
    if len(geometry) < 2:
        continue
    features.append({
        "type": "Feature",
        "properties": {"osm_id": element.get("id"), "name": (element.get("tags") or {}).get("name", "黄河"), "source": "OpenStreetMap Overpass"},
        "geometry": {"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in geometry]},
    })

out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
print(out)
print("features", len(features))
