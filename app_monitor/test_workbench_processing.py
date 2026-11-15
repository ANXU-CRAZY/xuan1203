import json
import io
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings


class WorkbenchProcessingTests(SimpleTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings_override = override_settings(BASE_DIR=Path(self.folder.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.client = Client(REMOTE_ADDR='127.0.0.1', HTTP_HOST='127.0.0.1:8012')

    def manifest(self):
        return {'tool_id': 'slope', 'parameters': {'units': 'degrees'},
                'inputs': [{'name': 'input', 'file': 'input0', 'kind': 'raster_in'}],
                'output_kinds': [{'name': 'output', 'kind': 'raster_out'}]}

    def call_backend(self, path, payload=None):
        if path == 'whitebox/tools/slope':
            return {'id': 'slope', 'available': True, 'params': [{'name': 'input'}, {'name': 'output'}]}
        self.assertEqual(path, 'whitebox/run')
        self.assertTrue(Path(payload['parameters']['input']).is_file())
        self.assertTrue(payload['parameters']['output'].endswith('.tif'))
        return {'id': '16803507-41c2-4e36-b216-9605a11dc848', 'status': 'pending'}

    @patch('app_monitor.workbench_processing.ensure_running', return_value=True)
    def test_upload_is_stored_and_sent_to_packaged_tool(self, _start):
        with patch('app_monitor.workbench_processing._call', side_effect=self.call_backend):
            response = self.client.post('/workbench/analysis/whitebox/', {
                'manifest': json.dumps(self.manifest()),
                'input0': SimpleUploadedFile('dem.tif', b'II*\x00synthetic'),
            })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['job']['status'], 'pending')
        self.assertEqual(data['artifacts'][0]['kind'], 'raster_out')
        self.assertTrue((Path(self.folder.name) / 'var/geolibre/jobs' / data['directory'] / 'job.json').is_file())

    @patch('app_monitor.workbench_processing.ensure_running', return_value=True)
    def test_external_paths_are_rejected(self, start):
        manifest = self.manifest()
        manifest['parameters']['input'] = 'C:\\private\\file.tif'
        response = self.client.post('/workbench/analysis/whitebox/', {'manifest': json.dumps(manifest)})
        self.assertEqual(response.status_code, 400)
        start.assert_not_called()

    def test_remote_request_and_unknown_artifacts_are_denied(self):
        response = self.client.post('/workbench/analysis/whitebox/', {'manifest': '{}'}, REMOTE_ADDR='192.0.2.1')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get('/workbench/analysis/artifact/' + '0' * 32 + '/0/').status_code, 404)

    def test_csrf_required_for_analysis(self):
        client = Client(enforce_csrf_checks=True, REMOTE_ADDR='127.0.0.1', HTTP_HOST='127.0.0.1:8012')
        self.assertEqual(client.post('/workbench/analysis/whitebox/', {'manifest': '{}'}).status_code, 403)

    @patch('app_monitor.workbench_agent._load_deepseek_local_env', return_value={'DEEPSEEK_API_KEY': 'test-only-key'})
    @patch('app_monitor.workbench_agent.urlrequest.urlopen')
    @patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-only-key'})
    def test_native_assistant_proxy_keeps_server_key_private(self, open_url, _env):
        upstream = io.BytesIO(b'data: [DONE]\n\n')
        upstream.headers = {'Content-Type': 'text/event-stream'}
        open_url.return_value = upstream
        response = self.client.post('/ai/v1/chat/completions',
            data=json.dumps({'model': 'client-supplied', 'messages': [{'role': 'user', 'content': 'test'}], 'stream': True}),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'test-only-key', b''.join(response.streaming_content))
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-only-key')
        self.assertNotEqual(json.loads(request.data)['model'], 'client-supplied')

    def test_native_assistant_proxy_requires_local_client_and_csrf(self):
        self.assertEqual(self.client.post('/ai/v1/chat/completions', data='{}',
            content_type='application/json', REMOTE_ADDR='192.0.2.1').status_code, 403)
        client = Client(enforce_csrf_checks=True, REMOTE_ADDR='127.0.0.1', HTTP_HOST='127.0.0.1:8012')
        self.assertEqual(client.post('/ai/v1/chat/completions', data='{}', content_type='application/json').status_code, 403)
