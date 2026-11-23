import json
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase

from .models import ObservationRecord, SpeciesInfo, WetlandZone
from .river_survey import SAMPLE, projected_river, summarize


URL = '/workbench/analysis/river-survey/'


class SurveyTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST='127.0.0.1')
        project = json.loads(SAMPLE.read_text(encoding='utf-8'))
        river = next(l for l in project['layers'] if l['id'] == 'sample-river')
        self.params = dict(source='sample', month='2026-10', radius=2000,
                           coordinates=river['geojson']['features'][0]['geometry']['coordinates'])

    def survey(self, **changes):
        return self.client.post(URL, {**self.params, **changes}, content_type='application/json')

    def test_sample_snapshot(self):
        reaches = self.survey().json()['reaches']
        self.assertEqual(len(reaches), 12)
        self.assertEqual(sum(r['records'] for r in reaches), 13)
        self.assertEqual(max(r['individuals'] for r in reaches), 67)
        self.assertEqual(max(r['species'] for r in reaches), 2)
        self.assertEqual(reaches[-1]['records'], 0)

    def test_month_and_species_filter(self):
        for params in ({'bird': '未知物种'}, {'month': '2026-09'}):
            self.assertFalse(any(r['records'] for r in self.survey(**params).json()['reaches']))

    def test_invalid_parameters(self):
        for params in ({'radius': -1}, {'source': 'private'}, {'coordinates': [[0, 0]]},
                       {'month': '2026-18'}, {'coordinates': [[113, 35], [113, 35]]}):
            self.assertEqual(self.survey(**params).status_code, 400)

    def test_boundary_overlap_and_missing_species(self):
        line, forward, reverse = projected_river([[113, 35], [113.2, 35]])
        point = line.interpolate(5000)
        point.transform(reverse)
        rows = [(point.x, point.y, '2026-10-01', n, species) for n, species in [(3, 1), (2, 1), (4, None)]]
        rows.append((113.1, 35.2, '2026-10-02', 100, 2))
        reaches = summarize(line, forward, reverse, rows, 2000)
        observed = [r for r in reaches if r['records']]
        self.assertEqual(len(observed), 1)
        self.assertEqual([observed[0][k] for k in ('records', 'individuals', 'species', 'days', 'missing_species')],
                         [3, 9, 1, 1, 1])

    def test_remote_access_and_csrf(self):
        self.assertEqual(self.client.post(URL, self.params, content_type='application/json',
                         REMOTE_ADDR='192.0.2.1').status_code, 403)
        client = Client(enforce_csrf_checks=True, HTTP_HOST='127.0.0.1')
        self.assertEqual(client.post(URL, self.params, content_type='application/json').status_code, 403)

    @patch('app_monitor.river_survey._request_deepseek')
    def test_constrained_language_parameters(self, model):
        model.return_value = ('{"month":"2026-10","metric":"species","radius_km":3,"bird":"白鹭","shell":"unused"}', None)
        response = self.client.post('/workbench/agent/river-intent/', {'message': '我想比较河边鸟的种类'},
                                    content_type='application/json')
        self.assertEqual(response.json(), dict(month='2026-10',metric='species',radius_km=3,bird='白鹭',landscape=False))


class ApprovedSurveyTests(TestCase):
    def test_only_approved_dated_and_locatable_records_count(self):
        bird = SpeciesInfo.objects.create(name_cn='测试物种')
        zone = WetlandZone.objects.create(name='测试监测点', longitude=113.02, latitude=35)
        for status, day, lat in [('approved','2026-10-01',35), ('pending','2026-10-01',35),
                                 ('approved','2026-09-30',35), ('approved','2026-10-01',36)]:
            ObservationRecord.objects.create(species=bird, zone=zone, count=4, observation_time=day, status=status,
                                             longitude=113.02, latitude=lat)
        response = Client(HTTP_HOST='127.0.0.1').post(URL, dict(source='approved', month='2026-10',
            radius=2000, coordinates=[[113,35], [113.2,35]]), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        reaches = response.json()['reaches']
        self.assertEqual(sum(r['records'] for r in reaches), 1)
        self.assertEqual(sum(r['individuals'] for r in reaches), 4)
