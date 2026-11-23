import io
import json
from unittest.mock import patch

from django.test import Client, SimpleTestCase
from .gis_methods import direct_plan, guidance


class MethodRoutingTests(SimpleTestCase):
    def setUp(self):
        self.layers = [{'name': '黄河走势（示意）', 'geometry': ['LineString']},
                       {'name': '观测点', 'geometry': ['Point'], 'numericFields': ['水温', 'FID']},
                       {'name': '保护区', 'geometry': ['Polygon']},
                       {'name': '核心区', 'geometry': ['Polygon']}]
        self.client = Client(HTTP_HOST='127.0.0.1')

    def plan(self, message):
        return self.client.post('/workbench/agent/plan/', {'message': message, 'layers': self.layers},
                                content_type='application/json').json()

    def test_metric_plan_and_dependencies(self):
        self.assertEqual(self.plan('给黄河走势做2公里缓冲区，再筛出区内的观测点并统计条数')['steps'],
                         [dict(tool='buffer', layer='L1', meters=2000),
                          dict(tool='points_within', layer='L2', area='R1'), dict(tool='count', layer='R2')])

    @patch('app_monitor.workbench_agent._request_deepseek')
    def test_direct_plans_are_available_to_native_without_model_call(self, model):
        def query(message):
            return self.client.post('/workbench/agent/plan/', {
                'message': message, 'layers': self.layers, 'directOnly': True
            }, content_type='application/json').json()

        self.assertEqual(query('沿着黄河走势两侧画出２公里范围')['steps'],
                         [dict(tool='buffer', layer='L1', meters=2000)])
        self.assertEqual(query('只保留落在保护区里面的观测点')['steps'],
                         [dict(tool='points_within', layer='L2', area='L3')])
        self.assertEqual(query('用核密度找出点位密集的地方'), {'steps': [], 'useNative': True})
        model.assert_not_called()

    def test_direction_and_aliases(self):
        for message, tool in [('从保护区中扣除核心区', 'difference'), ('求保护区与核心区的公共部分', 'intersection'),
                              ('用核心区裁剪保护区', 'clip')]:
            self.assertEqual(self.plan(message)['steps'], [dict(tool=tool, layer='L3', area='L4')])
        self.assertEqual(self.plan('筛出保护区内的观测点')['steps'],
                         [dict(tool='points_within', layer='L2', area='L3')])

    def test_reject_incompatible_inputs_and_ambiguous_alias(self):
        self.assertFalse(self.plan('用保护区裁剪观测点')['steps'])
        self.layers.append(dict(name='黄河走势（实测）', geometry=['LineString']))
        self.assertIn('多个图层', self.plan('给黄河走势做500米缓冲区')['message'])

    def test_does_not_discard_qualifiers(self):
        self.assertIsNone(direct_plan('从保护区中扣除核心区后按年份分别汇总', [
            dict(name='核心区', ref='L1'), dict(name='保护区', ref='L2')]))

    @patch('app_monitor.workbench_agent._request_deepseek')
    def test_unavailable_method_cannot_be_replaced_by_another(self, model):
        result = self.plan('对观测点进行克里金插值')
        self.assertEqual(result['steps'], [])
        self.assertIn('原生地图', result['message'])
        model.assert_not_called()

    def test_native_method_discovery_depends_on_actual_tools(self):
        tools = {'list_algorithms', 'run_algorithm', 'list_whitebox_tools', 'run_whitebox_tool'}
        for query, correct, wrong in [('分析显著热点', 'getis-ord-gi', 'kernel-density'),
                                      ('分析局部莫兰指数', 'local-morans-i', 'global-morans-i'),
                                      ('用高程算坡度', 'list_whitebox_tools', 'list_algorithms')]:
            prompt = guidance(query, native=True, tools=tools)
            self.assertIn(correct, prompt)
            self.assertNotIn(wrong, prompt)
        self.assertNotIn('run_algorithm', guidance('地图核密度', native=True, tools=set()))

    @patch('app_monitor.workbench_agent._load_deepseek_local_env', return_value={'DEEPSEEK_API_KEY': 'test'})
    @patch('app_monitor.workbench_agent.urlrequest.urlopen')
    def test_native_proxy_routes_latest_task_using_advertised_tools(self, upstream, _env):
        stream = io.BytesIO(b'OK')
        stream.headers = {'Content-Type': 'text/event-stream'}
        upstream.return_value = stream
        payload = {'messages': [{'role': 'user', 'content': '按核密度制图'},
                                {'role': 'user', 'content': [{'type': 'text', 'text': '用 DEM 求坡度'}]}],
                   'tools': [{'type': 'function', 'function': {'name': n}}
                             for n in ('list_whitebox_tools', 'run_whitebox_tool')]}
        response = self.client.post('/ai/v1/chat/completions', payload, content_type='application/json')
        self.assertEqual(b''.join(response.streaming_content), b'OK')
        sent = json.loads(upstream.call_args.args[0].data)
        self.assertIn('slope from elevation DEM', sent['messages'][0]['content'])
        self.assertNotIn('kernel-density', sent['messages'][0]['content'])

    @patch('app_monitor.workbench_agent._request_deepseek')
    def test_bad_model_field_rejected(self, model):
        model.return_value = ('{"steps":[{"tool":"idw","layer":"L2","field":"FID"}]}', None)
        self.assertFalse(self.plan('对观测点进行插值')['steps'])
        self.assertIn('反距离权重', model.call_args.args[0][0]['content'])

    @patch('app_monitor.workbench_agent._request_deepseek')
    def test_interpolation_requires_explicit_field_if_ambiguous(self, model):
        self.layers[1]['numericFields'].append('水位')
        model.return_value = ('{"steps":[{"tool":"idw","layer":"L2","field":"水温"}]}', None)
        result = self.plan('对观测点进行插值')
        self.assertEqual(result['steps'], [])
        self.assertIn('水温、水位', result['message'])
