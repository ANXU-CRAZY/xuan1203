"""Small, credential-free bridge to a local SuperMap iServer instance."""

import os
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
