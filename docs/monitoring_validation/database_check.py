"""Read-only verification against independent SQL on the ORIGINAL database."""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.db import connection
from django.test import Client

assert connection.settings_dict['NAME'] == 'Yellow River'
client = Client(HTTP_HOST='localhost')
checks = []
for lng, lat, radius in [(113.58632,34.76886,500), (112.85377264,34.81704478,500), (113.58632,34.76886,10000)]:
    start = time.perf_counter()
    response = client.get('/api/monitoring/buffer/', {'lng':lng,'lat':lat,'radius':radius})
    assert response.status_code == 200
    payload = response.json()
    with connection.cursor() as cur:
        cur.execute('''SELECT count(*),coalesce(sum(r.count),0),count(distinct r.species_id)
            FROM app_monitor_observationrecord r JOIN app_monitor_wetlandzone z ON z.id=r.zone_id
            WHERE r.status='approved' AND ST_DWithin(COALESCE(r.location,
            CASE WHEN r.longitude BETWEEN -180 AND 180 AND r.latitude BETWEEN -90 AND 90
            THEN ST_SetSRID(ST_MakePoint(r.longitude,r.latitude),4326) END,
            z.location,ST_SetSRID(ST_MakePoint(z.longitude,z.latitude),4326))::geography,
            ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s)''', [lng,lat,radius])
        expected = cur.fetchone()
    summary = payload['summary']
    actual = (summary['total_records'],summary['bird_count'],summary['species_count'])
    assert actual == expected, (actual,expected)
    checks.append({'center':[lng,lat], 'radius':radius, 'api':actual, 'database':expected,
                   'matched_routes':summary['matched_routes'], 'detail_count':len(payload['results']),
                   'truncated':payload['truncated'], 'seconds':round(time.perf_counter()-start,3)})
Path(__file__).with_name('database-results.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2), encoding='utf-8')
print(json.dumps(checks,ensure_ascii=True,indent=2))
