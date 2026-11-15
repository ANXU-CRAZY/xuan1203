import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings
from .workbench_access import may_compute
from .workbench_processing import whitebox_artifact
from .workbench_sidecar import proxy


@override_settings(GEOSTUDIO_REMOTE_COMPUTE=True, ALLOWED_HOSTS=['localhost', 'example.com'])
class GeoStudioAccessTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory(HTTP_HOST='example.com', REMOTE_ADDR='198.51.100.1')
        self.user = SimpleNamespace(is_authenticated=True, is_active=True, pk=1)

    def test_remote_requires_active_login_even_with_loopback_host(self):
        request = self.factory.get('/', HTTP_HOST='localhost', REMOTE_ADDR='127.0.0.1')
        request.user = SimpleNamespace(is_authenticated=False, is_active=False)
        self.assertFalse(may_compute(request))
        request.user = self.user
        self.assertTrue(may_compute(request))

    def test_raw_sidecar_execution_is_never_exposed(self):
        request = self.factory.post('/sidecar/whitebox/run', data='{}', content_type='application/json')
        request.user = self.user
        request._dont_enforce_csrf_checks = True
        with self.assertRaises(Http404):
            proxy(request, 'whitebox/run')

    def test_artifacts_are_only_visible_to_their_owner(self):
        with tempfile.TemporaryDirectory() as temp, override_settings(BASE_DIR=Path(temp)):
            folder = Path(temp) / 'var/geolibre/jobs' / ('a' * 32)
            folder.mkdir(parents=True)
            output = folder / 'output-0.json'
            output.write_text('{}', encoding='utf-8')
            (folder / 'job.json').write_text(json.dumps({'owner': '2', 'artifacts': [{'path': str(output), 'kind': 'file_out'}]}), encoding='utf-8')
            request = self.factory.get('/')
            request.user = self.user
            with self.assertRaises(Http404):
                whitebox_artifact(request, 'a' * 32, 0)

    @patch('app_monitor.workbench_sidecar.ensure_running')
    def test_job_poll_requires_ownership(self, ensure):
        with tempfile.TemporaryDirectory() as temp, override_settings(BASE_DIR=Path(temp)):
            directory = Path(temp) / 'var/geolibre/job-index'
            directory.mkdir(parents=True)
            job = '16803507-41c2-4e36-b216-9605a11dc848'
            (directory / (job + '.json')).write_text(json.dumps({'owner': '2'}), encoding='utf-8')
            request = self.factory.get('/')
            request.user = self.user
            with self.assertRaises(Http404):
                proxy(request, 'whitebox/jobs/' + job)
            ensure.assert_not_called()

    @override_settings(ROOT_URLCONF='config.geostudio_urls')
    def test_online_page_exposes_expected_navigation_and_login(self):
        response = self.client.get('/', HTTP_HOST='example.com')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '方舟视界')
        self.assertContains(response, 'See Beyond. Understand More.')
        self.assertContains(response, 'https://arklab-geoai.org.cn/platform/')
        self.assertContains(response, 'https://arklab-geoai.org.cn/geostudio/')
        self.assertContains(response, 'https://arklab-geoai.org.cn/platform/huiyan/choose/')
        self.assertContains(response, '在线工作区')
        self.assertEqual(self.client.get('/account/', HTTP_HOST='example.com').status_code, 200)
