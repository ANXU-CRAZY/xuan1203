"""Transport/ownership regressions; these do not load SAM, ONNX, or a database."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core import signing
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve
from django.urls import get_script_prefix, set_script_prefix

from app_monitor import land_segmentation as land


class LandSegmentationTests(SimpleTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(HUIYAN_LAND_STATE_DIR=Path(self.directory.name))
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.client.get('/huiyan/land/')
        self.owner = signing.loads(self.client.cookies[land.COOKIE].value, salt=land.SALT)

    def own_workspace(self, initialized=True):
        land._write_lease({'owner': self.owner, 'initialized': initialized, 'expires': land.time.time() + 120})

    def test_task_routes_remain_separate(self):
        self.assertEqual(resolve('/huiyan/').func.__module__, 'app_monitor.huiyan')
        self.assertEqual(resolve('/huiyan/land/').func.__module__, 'app_monitor.land_segmentation')
        response = self.client.get('/huiyan/choose/')
        self.assertContains(response, '识别地物')
        self.assertContains(response, 'href="/huiyan/"')
        self.assertContains(response, 'href="/huiyan/land/"')

    @override_settings(ROOT_URLCONF='config.huiyan_urls')
    def test_pages_also_render_in_bounded_inference_worker(self):
        self.assertEqual(self.client.get('/huiyan/land/').status_code, 200)
        self.assertEqual(self.client.get('/huiyan/choose/').status_code, 200)

    @patch.object(land, 'upstream')
    def test_html_rewrites_all_native_transport_roots_with_csrf(self, upstream):
        html = b'''<html><head></head><body><img src="/logo.png"><script>
        fetch('/upload');api('/api/'+act);img.src='/overlay?hl=1';
        const map='https://example.com/api/';</script></body></html>'''
        upstream.side_effect = [(200, {}, b'{"has_image":false,"objects":[],"model":"tiny","device":"cpu"}'),
                                (200, {'Content-Type': 'text/html; charset=utf-8'}, html)]
        response = self.client.get('/huiyan/land/workbench/')
        self.assertContains(response, 'src="/huiyan/land/workbench/logo.png"')
        self.assertContains(response, "fetch('/huiyan/land/workbench/upload')")
        self.assertContains(response, "api('/huiyan/land/workbench/api/'+act)")
        self.assertContains(response, 'https://example.com/api/')
        self.assertContains(response, 'X-CSRFToken')
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
        self.assertIn('no-store', response['Cache-Control'])

    @patch.object(land, 'upstream')
    def test_another_browser_cannot_read_or_replace_image(self, upstream):
        self.own_workspace()
        other = Client()
        other.get('/huiyan/land/')
        for method, path in [('get', 'api/status'), ('get', 'image'), ('post', 'upload'), ('get', 'example?name=truck.jpg')]:
            response = getattr(other, method)('/huiyan/land/workbench/' + path)
            self.assertEqual(response.status_code, 423)
        upstream.assert_not_called()

    @patch.object(land, 'upstream')
    def test_new_session_does_not_observe_stale_image_or_history(self, upstream):
        upstream.return_value = (200, {}, json.dumps({'has_image': True, 'objects': [{'name': 'private'}],
            'image_name': 'private.jpg', 'history': ['private.jpg'], 'gps': [1, 2], 'model': 'tiny', 'device': 'cpu'}).encode())
        response = self.client.get('/huiyan/land/workbench/api/status')
        self.assertFalse(response.json()['has_image'])
        self.assertEqual(response.json()['objects'], [])
        self.assertEqual(response.json()['history'], [])
        self.assertNotIn('private', response.content.decode())
        upstream.reset_mock()
        self.assertEqual(self.client.get('/huiyan/land/workbench/image').status_code, 409)
        upstream.assert_not_called()

    @patch.object(land, 'upstream', return_value=(200, {'Content-Type': 'application/json'}, b'{"ok":true}'))
    def test_first_upload_resets_previous_owner_counters(self, upstream):
        response = self.client.post('/huiyan/land/workbench/upload', b'image', content_type='image/png')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([call.args[0] for call in upstream.call_args_list],
                         ['api/clear_objects', 'api/stats_reset', 'api/history_clear', 'upload'])
        self.assertTrue(land._read_lease()['initialized'])

    @patch.object(land, 'upstream')
    def test_action_and_path_traversal_are_rejected(self, upstream):
        self.own_workspace()
        for path, body in [('api/predict', {'action': 'save_config'}),
                           ('api/switch_model', {'model': '../../other'}),
                           ('api/batch', {'items': [{'name': '../secret.jpg'}], 'format': 'overlay'}),
                           ('api/batch', {'items': [None], 'format': 'overlay'}),
                           ('api/video', {'name': 'C:\\secret.mp4'})]:
            self.assertEqual(self.client.post('/huiyan/land/workbench/' + path, body, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get('/huiyan/land/workbench/example?name=../../secret.jpg').status_code, 400)
        self.assertEqual(self.client.get('/huiyan/land/workbench/../secret').status_code, 404)
        self.assertEqual(self.client.post('/huiyan/land/workbench/api/predict', b'bad', content_type='application/json').status_code, 400)
        upstream.assert_not_called()

    @patch.object(land, 'upstream')
    def test_configuration_does_not_expose_or_modify_host_settings(self, upstream):
        response = self.client.post('/huiyan/land/workbench/api/config', {'action': 'get_config'}, content_type='application/json')
        self.assertEqual(response.json(), {'ok': True, 'config': {}})
        upstream.assert_not_called()

    @patch.object(land, 'upstream')
    def test_proxy_requires_csrf(self, upstream):
        client = Client(enforce_csrf_checks=True)
        client.get('/huiyan/land/')
        response = client.post('/huiyan/land/workbench/upload', b'image', content_type='image/png')
        self.assertEqual(response.status_code, 403)
        upstream.assert_not_called()

    @patch.object(land, 'upstream', side_effect=ConnectionRefusedError)
    @override_settings(HUIYAN_LAND_AUTOSTART=False)
    def test_unavailable_service_has_retry_page(self, upstream):
        response = self.client.get('/huiyan/land/workbench/')
        self.assertContains(response, '重新连接', status_code=503)

    def test_release_only_releases_own_workspace(self):
        self.own_workspace()
        other = Client()
        other.get('/huiyan/land/')
        other.post('/huiyan/land/release/')
        self.assertEqual(land._read_lease()['owner'], self.owner)
        self.client.post('/huiyan/land/release/')
        self.assertEqual(land._read_lease(), {})

    @patch.object(land, 'upstream', return_value=(200, {'Content-Type': 'image/png'}, b'image'))
    def test_browser_exit_releases_workspace_but_same_browser_can_resume(self, upstream):
        self.own_workspace()
        self.client.post('/huiyan/land/release/', {'preserve': '1'})
        self.assertIsNone(land._read_lease().get('owner'))
        response = self.client.get('/huiyan/land/workbench/image')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(land._read_lease()['initialized'])

    @patch.object(land, 'upstream', return_value=(200, {}, b'{"has_image":true,"objects":[],"model":"tiny","device":"cpu"}'))
    def test_another_browser_after_exit_cannot_resume_the_old_image(self, upstream):
        self.own_workspace()
        self.client.post('/huiyan/land/release/', {'preserve': '1'})
        other = Client()
        other.get('/huiyan/land/')
        response = other.get('/huiyan/land/workbench/api/status')
        self.assertFalse(response.json()['has_image'])
        self.assertEqual(other.get('/huiyan/land/workbench/image').status_code, 409)

    def test_outer_explanatory_bar_is_removed(self):
        response = self.client.get('/huiyan/land/')
        self.assertNotContains(response, '<header')
        self.assertContains(response, 'land-workbench')

    @override_settings(TDT_KEY='test-browser-map-key')
    def test_location_uses_host_tianditu_map_before_native_initialization(self):
        html = '''<head></head><section class="panel"><div id="gpsState"></div>
        <div class="body"><div class="gpsmap"><canvas id="gpsMapCanvas"></canvas></div>
        <div class="hint">old grid</div></div></section>
        <section id="stats">native statistics</section><script>
        // ---------- 初始化 ----------
        updModelTier();</script>'''
        adapted = land._workbench_html(html.encode(), RequestFactory().get('/huiyan/land/workbench/'))
        self.assertNotIn('<canvas id="gpsMapCanvas">', adapted)
        self.assertIn('id="landGeoMap"', adapted)
        self.assertIn('id="landGeoSearch"', adapted)
        self.assertIn('id="gpsState"', adapted)
        self.assertIn('<section id="stats">native statistics</section>', adapted)
        self.assertIn('test-browser-map-key', adapted)
        self.assertIn('window.LAND_MAP_CONFIG={tdtKey:cfg.tdtKey}', adapted)
        self.assertIn('leaflet/leaflet.js', adapted)
        self.assertLess(adapted.index('window.installLandMap();'), adapted.index('updModelTier();'))

    @override_settings(HUIYAN_LAND_SERVICE_URL='http://remote.example:8013')
    def test_upstream_is_loopback_only(self):
        with self.assertRaises(land.ServiceError):
            land.service_address()

    def test_mounted_workbench_urls_do_not_double_prefix(self):
        previous = get_script_prefix()
        try:
            set_script_prefix('/platform/')
            html = land._workbench_html(b'<head></head><script>fetch("/api/status")</script>', self.client.request().wsgi_request)
            from config.path_mount import rewrite_text
            html = rewrite_text(html, html=True)
            self.assertIn('fetch("/platform/huiyan/land/workbench/api/status")', html)
            self.assertNotIn('/platform/platform/', html)
        finally:
            set_script_prefix(previous)

    @patch.object(land, 'upstream')
    def test_csv_uses_object_longitude_and_latitude_in_the_right_columns(self, upstream):
        upstream.return_value = (200, {}, json.dumps({'objects': [{'id': 1, 'lat': 34.75, 'lon': 113.66}]}).encode())
        original = json.dumps({'csv': '\ufeff编号,名称,经度,纬度\r\n1,test,34.75,113.66\r\n', 'filename': 'test.csv'}).encode()
        output = json.loads(land._csv_with_coordinates(original))
        self.assertIn('1,test,113.66,34.75', output['csv'])
        self.assertTrue(output['csv'].startswith('\ufeff'))
        self.assertEqual(output['filename'], 'test.csv')

    def test_workspace_lock_serializes_separate_processes(self):
        script = '''import sys
from pathlib import Path
from django.conf import settings
settings.configure(BASE_DIR=Path(sys.argv[1]),HUIYAN_LAND_STATE_DIR=Path(sys.argv[1]))
from app_monitor.land_segmentation import workspace_lock,ServiceError
try:
    with workspace_lock(timeout=.2): pass
except ServiceError: sys.exit(23)
sys.exit(0)
'''
        with land.workspace_lock():
            result = subprocess.run([sys.executable, '-c', script, self.directory.name], cwd=Path(__file__).resolve().parents[1],
                                    capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 23, result.stderr.decode(errors='replace'))
