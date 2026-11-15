import json
import tempfile
from unittest.mock import patch
from pathlib import Path

from django.test import SimpleTestCase, override_settings


class WorkbenchFrontendTests(SimpleTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        (root / 'assets').mkdir()
        (root / 'index.html').write_text('<html><head></head><body><script src="./assets/map.js"></script></body></html>', encoding='utf-8')
        (root / 'assets/map.js').write_text('console.log("map")', encoding='utf-8')
        (root / '.private').write_text('private', encoding='utf-8')
        self.settings = override_settings(GEOLIBRE_WEB_ROOT=root)
        self.settings.enable()
        self.addCleanup(self.settings.disable)

    def test_page_and_platform_entry_render_without_database_queries(self):
        response = self.client.get('/workbench/')
        self.assertContains(response, 'id="wb-map"')
        self.assertContains(response, '示例工程使用模拟数据')
        self.assertNotContains(response, 'class="wb-project-bar"')
        header = response.content.decode().split('</header>')[0]
        self.assertIn('id="wb-import"', header)
        self.assertIn('id="wb-save"', header)
        self.assertContains(response, 'data-engine-url="/workbench/geolibre/"')
        self.assertContains(self.client.get('/'), 'href="/workbench/"')

    def test_only_engine_allows_same_origin_embedding(self):
        response = self.client.get('/workbench/geolibre/')
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
        self.assertContains(response, 'workbench/engine.css')
        self.assertContains(response, 'src="./assets/map.js"')
        self.assertNotEqual(self.client.get('/workbench/').get('X-Frame-Options'), 'SAMEORIGIN')

    def test_runtime_policy_allows_only_the_exact_request_origin(self):
        response = self.client.get('/workbench/geolibre/deployment.json', secure=True)
        policy = json.loads(response.content)
        self.assertEqual(policy['sharing']['embedOrigins'], ['https://testserver'])
        self.assertTrue(policy['ai']['enabled'])
        self.assertIn('processing:run', policy['capabilities'])
        self.assertIn('processing:sidecar', policy['capabilities'])
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_assets_keep_browser_module_content_type(self):
        response = self.client.get('/workbench/geolibre/assets/map.js')
        self.assertEqual(response['Content-Type'], 'application/javascript')
        self.assertEqual(b''.join(response.streaming_content), b'console.log("map")')

    def test_private_and_traversal_paths_are_not_served(self):
        for suffix in ('.private', '../.private', '%2e%2e/.private', 'assets%5c..%5c.private', 'not-found.js'):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.client.get('/workbench/geolibre/' + suffix).status_code, 404)

    def test_missing_build_returns_an_honest_unavailable_status(self):
        with override_settings(GEOLIBRE_WEB_ROOT=Path(self.folder.name) / 'missing'):
            self.assertEqual(self.client.get('/workbench/geolibre/').status_code, 503)

    def test_only_safe_requests_are_accepted(self):
        self.assertEqual(self.client.post('/workbench/').status_code, 405)
        self.assertEqual(self.client.post('/workbench/geolibre/deployment.json').status_code, 405)

    def test_provider_styles_and_annotations_use_only_configured_keys(self):
        with patch('app_monitor.workbench.provider_config', return_value={'tianditu_key': 'test-tdt', 'amap_key': 'test-amap'}):
            for kind, names in [('vector', {'vec','cva'}), ('imagery', {'img','cia'}), ('blank', set())]:
                response = self.client.get('/workbench/geolibre/basemap.json', {'kind': kind})
                style = json.loads(response.content)
                self.assertEqual(set(style['sources']), names)
                self.assertNotIn('cartocdn', response.content.decode())
            style = self.client.get('/workbench/geolibre/basemap.json', {'labels': '0'}).json()
            self.assertEqual(set(style['sources']), {'vec'})
            amap = self.client.get('/workbench/geolibre/basemap.json', {'kind': 'amap'}).json()
            self.assertEqual(set(amap['sources']['amap']), {'type', 'url', 'coordinates'})
            self.assertIn('restapi.amap.com/v3/staticmap?', amap['sources']['amap']['url'])
            self.assertEqual(amap['metadata']['arkAttribution'], '© 高德地图')

    def test_invalid_provider_parameters_return_400(self):
        self.assertEqual(self.client.get('/workbench/geolibre/basemap.json?lng=nan').status_code, 400)
        self.assertEqual(self.client.get('/workbench/geolibre/basemap.json?width=999999').status_code, 400)

    def test_gcj_conversion_roundtrips_without_modifying_source_coordinates(self):
        from .workbench_basemaps import gcj_to_wgs, wgs_to_gcj
        for point in [(113.58,34.96),(116.4,39.9),(121.4,31.2),(0,0)]:
            converted = wgs_to_gcj(*point)
            restored = gcj_to_wgs(*converted)
            self.assertAlmostEqual(restored[0], point[0], places=7)
            self.assertAlmostEqual(restored[1], point[1], places=7)
