"""Small, credential-free bridge to a local SuperMap iServer instance."""

import os
import json
import time
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.db import connection


def _setting(name, default=''):
    return getattr(settings, name, os.getenv(name, default))


def supermap_config():
    base_url = _setting('SUPERMAP_ISERVER_URL', 'http://127.0.0.1:8090/iserver').rstrip('/')
    return {
        'base_url': base_url,
        'catalog_url': f'{base_url}/services',
        'map_service_url': _setting('SUPERMAP_MAP_SERVICE_URL', '').strip(),
        'iclient_leaflet_url': _setting(
            'SUPERMAP_ICLIENT_LEAFLET_URL',
            f'{base_url}/iClient/forJavaScript/dist/leaflet/iclient-leaflet.min.js',
        ).strip(),
    }


def probe_iserver(config):
    started_at = time.monotonic()
    request = urlrequest.Request(
        config['catalog_url'],
        headers={'Accept': 'text/html,application/json', 'User-Agent': 'YellowRiver-SuperMap-Bridge/1.0'},
    )
    try:
        with urlrequest.urlopen(request, timeout=8) as response:
            response.read(512)
            return {
                'available': 200 <= response.status < 400,
                'http_status': response.status,
                'latency_ms': round((time.monotonic() - started_at) * 1000),
                'error': None,
            }
    except HTTPError as error:
        return {
            'available': False,
            'http_status': error.code,
            'latency_ms': round((time.monotonic() - started_at) * 1000),
            'error': f'HTTP {error.code}',
        }
    except (URLError, OSError) as error:
        return {
            'available': False,
            'http_status': None,
            'latency_ms': round((time.monotonic() - started_at) * 1000),
            'error': str(error.reason if isinstance(error, URLError) else error),
        }


def spatial_view_status():
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*), COALESCE(MIN(ST_SRID(geom)), 0) FROM supermap_observation_points'
            )
            record_count, srid = cursor.fetchone()
        return {'ready': True, 'record_count': record_count, 'srid': srid}
    except Exception:
        return {'ready': False, 'record_count': 0, 'srid': None}


def supermap_status_payload():
    config = supermap_config()
    return {
        'provider': 'SuperMap iServer',
        'server': probe_iserver(config),
        'spatial_view': spatial_view_status(),
        'catalog_url': config['catalog_url'],
        'map_service_url': config['map_service_url'],
        'iclient_leaflet_url': config['iclient_leaflet_url'],
        'map_service_configured': bool(config['map_service_url']),
    }


def supermap_buffer_geometry(lng, lat, radius_m):
    """Create a WGS84 buffer through iServer's geometry analyst endpoint."""
    config = supermap_config()
    endpoint = (
        f"{config['base_url']}/services/spatialAnalysis-YellowRiverSuperMap/"
        "restjsr/spatialanalyst/geometry/buffer"
        "?returnContent=true&asynchronousReturn=false"
    )
    payload = {
        'sourceGeometry': {
            'type': 'POINT',
            'points': [{'x': lng, 'y': lat}],
            'prjCoordSys': {'epsgCode': 4326},
        },
        'analystParameter': {
            'leftDistance': {'value': radius_m},
            'rightDistance': {'value': radius_m},
            'radiusUnit': 'METER',
            'endType': 'ROUND',
            'semicircleLineSegment': 16,
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = urlrequest.Request(
        endpoint,
        data=body,
        headers={
            'Accept': 'application/json',
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'YellowRiver-SuperMap-Bridge/1.0',
        },
        method='POST',
    )
    try:
        with urlrequest.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f'iServer 缓冲分析失败: {error}') from error

    geometry = result.get('resultGeometry') if isinstance(result, dict) else None
    if not geometry or not geometry.get('points'):
        raise RuntimeError(result.get('message') or 'iServer 未返回缓冲几何')
    points = geometry['points']
    parts = geometry.get('parts') or [len(points)]
    rings = []
    offset = 0
    for length in parts:
        ring = [[point['x'], point['y']] for point in points[offset:offset + length]]
        offset += length
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        if ring:
            rings.append(ring)
    if not rings:
        raise RuntimeError('iServer 返回了空缓冲几何')
    return {'type': 'Polygon', 'coordinates': rings}
