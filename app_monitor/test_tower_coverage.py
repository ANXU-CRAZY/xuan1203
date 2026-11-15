import json
import math
import tempfile
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, Point
from django.test import SimpleTestCase

from .tower_coverage import EARTH_RADIUS, build_coverage, coverage_ring


class TowerCoverageTests(SimpleTestCase):
    def test_ring_is_closed_and_uses_metres_at_different_latitudes(self):
        for latitude in (0, 34.8, 60):
            ring = coverage_ring(113, latitude)
            self.assertEqual(ring[0], ring[-1])
            for lng, lat in ring[:-1]:
                a, b = map(math.radians, (latitude, lat))
                h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lng-113)/2)**2
                self.assertAlmostEqual(2*EARTH_RADIUS*math.asin(math.sqrt(h)), 2500, places=5)

    def fixture(self, folder, duplicates=False):
        tower = {'type': 'Feature', 'properties': {'kind': 'existing'},
                 'geometry': {'type': 'Point', 'coordinates': [113, 35]}}
        planned = {'type': 'Feature', 'properties': {'kind': 'planned'},
                   'geometry': {'type': 'Point', 'coordinates': [113.1, 35]}}
        towers = Path(folder) / 'towers.json'
        boundary = Path(folder) / 'boundary.json'
        towers.write_text(json.dumps({'features': [tower, planned] + ([tower] if duplicates else [])}))
        boundary.write_text(json.dumps({'features': [{'geometry': {'type': 'Polygon', 'coordinates': [
            [[112.95, 34.95], [113.15, 34.95], [113.15, 35.05], [112.95, 35.05], [112.95, 34.95]]
        ]}}]}))
        return build_coverage(str(towers), str(boundary), towers.stat().st_mtime_ns, boundary.stat().st_mtime_ns)

    def test_uncovered_is_inside_boundary_and_excludes_only_existing_towers(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.fixture(folder)
        uncovered = GEOSGeometry(json.dumps(result['features'][0]['geometry']), srid=4326)
        self.assertTrue(uncovered.valid)
        self.assertFalse(uncovered.covers(Point(113, 35)))
        self.assertTrue(uncovered.covers(Point(113.1, 35)))
        self.assertFalse(uncovered.covers(Point(113.2, 35)))
        metadata = result['metadata']
        self.assertAlmostEqual(metadata['region_km2'], metadata['covered_km2'] + metadata['uncovered_km2'], places=2)

    def test_duplicate_overlapping_towers_do_not_double_count_coverage(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            one, two = self.fixture(first), self.fixture(second, duplicates=True)
        self.assertEqual(one['metadata']['covered_km2'], two['metadata']['covered_km2'])
        self.assertEqual(one['metadata']['uncovered_km2'], two['metadata']['uncovered_km2'])

    def test_endpoint_uses_real_region_and_is_read_only(self):
        response = self.client.get('/api/monitoring/tower-coverage/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['metadata']['radius_metres'], 2500)
        self.assertEqual(response.json()['metadata']['basis'], 'existing')
        self.assertGreater(response.json()['metadata']['region_km2'], 0)
        self.assertIn('max-age=300', response['Cache-Control'])
        self.assertEqual(self.client.post('/api/monitoring/tower-coverage/').status_code, 405)
