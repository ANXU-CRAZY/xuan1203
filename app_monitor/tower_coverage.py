"""Estimated infrastructure coverage; independent of bird observation records."""
import json
import math
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, GeometryCollection, Polygon
from django.http import JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

RADIUS_METRES = 2500
EARTH_RADIUS = 6371000


def coverage_ring(lng, lat, steps=180):
    latitude, longitude = map(math.radians, (lat, lng))
    angle = RADIUS_METRES / EARTH_RADIUS
    ring = []
    for index in range(steps):
        bearing = 2 * math.pi * index / steps
        north = math.asin(math.sin(latitude) * math.cos(angle) +
                          math.cos(latitude) * math.sin(angle) * math.cos(bearing))
        east = longitude + math.atan2(math.sin(bearing) * math.sin(angle) * math.cos(latitude),
                                      math.cos(angle) - math.sin(latitude) * math.sin(north))
        ring.append((math.degrees(east), math.degrees(north)))
    return [*ring, ring[0]]


def union(geometries):
    return GeometryCollection(*geometries, srid=4326).unary_union


@lru_cache(maxsize=1)
def build_coverage(tower_path, boundary_path, tower_stamp, boundary_stamp):
    towers = json.loads(Path(tower_path).read_text(encoding='utf-8'))['features']
    boundaries = json.loads(Path(boundary_path).read_text(encoding='utf-8'))['features']
    region = union([GEOSGeometry(json.dumps(feature['geometry']), srid=4326).make_valid()
                    for feature in boundaries])
    existing = [feature for feature in towers if feature['properties']['kind'] == 'existing']
    footprint = union([Polygon(coverage_ring(*feature['geometry']['coordinates']), srid=4326)
                       for feature in existing])
    covered = region.intersection(footprint)
    uncovered = region.difference(footprint)
    area = lambda geometry: round(geometry.transform(32649, clone=True).area / 1e6, 3)
    return {
        'type': 'FeatureCollection',
        'features': [] if uncovered.empty else [{
            'type': 'Feature', 'geometry': json.loads(uncovered.geojson),
            'properties': {'name': '未覆盖区域', 'basis': '保护区范围内，按现有监测塔估算'},
        }],
        'metadata': {'radius_metres': RADIUS_METRES, 'basis': 'existing', 'estimated': True,
                     'existing_towers': len(existing), 'region_km2': area(region),
                     'covered_km2': area(covered), 'uncovered_km2': area(uncovered)},
    }


@require_GET
@cache_control(public=True, max_age=300)
def uncovered(request):
    folder = settings.BASE_DIR / 'app_monitor/static/app_monitor/geo'
    towers, boundary = folder / 'monitoring_towers.geojson', folder / 'protected_areas.geojson'
    return JsonResponse(build_coverage(str(towers), str(boundary), towers.stat().st_mtime_ns,
                                       boundary.stat().st_mtime_ns))
