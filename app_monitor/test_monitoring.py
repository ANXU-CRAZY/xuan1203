"""Spatial contract tests; run on an isolated PostGIS test database."""
import csv
import io

from django.contrib.gis.geos import LineString, MultiLineString, Point
from django.test import TestCase

from .models import MonitoringRoute, ObservationRecord, SpeciesInfo, WetlandZone
from .monitoring import csv_cell


class MonitoringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zone = WetlandZone.objects.create(name='测试湿地', longitude=114, latitude=35)
        cls.first = SpeciesInfo.objects.create(name_cn='测试一级鸟', protection_level='国家一级')
        cls.second = SpeciesInfo.objects.create(name_cn='测试二级鸟', protection_level='国家二级')
        records = [ObservationRecord(species=cls.first, zone=cls.zone, observation_time='2020-12-31',
                   count=3, status='approved', location=Point(114, 35, srid=4326)) for _ in range(5002)]
        ObservationRecord.objects.bulk_create(records)
        cls.other = ObservationRecord.objects.create(species=cls.second, zone=cls.zone, observation_time='2021-01-01', count=7,
                    status='approved', longitude=114, latitude=35, description=' =HYPERLINK("危险"),逗号\n换行')
        cls.pending = ObservationRecord.objects.create(species=cls.first, zone=cls.zone, observation_time='2020-12-31', count=99999,
                    status='pending', longitude=114, latitude=35)
        MonitoringRoute.objects.create(name='穿越缓冲的样线', path_geom=MultiLineString(LineString((113.99,35),(114.01,35)),srid=4326))
        MonitoringRoute.objects.create(name='空样线')

    def get(self, path='/api/map-observations/', **params):
        response = self.client.get(path, params)
        self.assertEqual(response.status_code, 200, response.content[:300] if not response.streaming else '')
        return response.json()

    def test_cluster_conservation_and_complete_statistics(self):
        result = self.get(west=113, south=34, east=115, north=36, zoom=10)
        self.assertEqual(result['mode'], 'clusters')
        self.assertEqual(result['results'], [])
        self.assertEqual(sum(c['cluster_size'] for c in result['clusters']), 5003)
        self.assertEqual(sum(c['count'] for c in result['clusters']), 15013)
        self.assertEqual(result['stats']['species_count'], 2)
        self.assertEqual(result['stats']['total_records'], 5003)

    def test_detail_pages_are_bounded_without_gaps(self):
        params = dict(west=113, south=34, east=115, north=36, zoom=15)
        first = self.get(**params)
        self.assertEqual(len(first['results']), 5000)
        self.assertTrue(first['truncated'])
        second = self.get(**params, after=first['next_after'])
        self.assertEqual(len(second['results']), 3)
        self.assertFalse(second['has_more'])
        self.assertFalse(set(r['id'] for r in first['results']) & set(r['id'] for r in second['results']))
        self.assertEqual(second['stats']['total_records'], 5003)
        self.assertEqual(sum(c['cluster_size'] for c in second['clusters']), 5003)

    def test_preview_is_bounded_filtered_and_not_a_complete_statistic(self):
        preview = self.get(stage='preview', zoom=10)
        self.assertEqual(preview['stage'], 'preview')
        self.assertEqual(len(preview['results']), 300)
        self.assertIsNone(preview['stats'])
        self.assertNotIn('viewport', preview)
        filtered = self.get(stage='preview', protection='国家二级', start='2021-01-01')
        self.assertEqual([row['id'] for row in filtered['results']], [self.other.pk])
        self.assertEqual(self.get(stage='preview', bbox='0,0,1,1')['results'], [])
        complete = self.get(zoom=10)
        self.assertEqual(sum(c['cluster_size'] for c in complete['clusters']), 5003)

    def test_regional_overview_retains_each_distinct_coordinate(self):
        for lng in (114.002, 114.004):
            ObservationRecord.objects.create(species=self.first, zone=self.zone,
                observation_time='2020-12-31', status='approved', location=Point(lng,35,srid=4326))
        for extent in ((113,34,115,36), (100,20,130,50)):
            west,south,east,north=extent
            payload=self.get(west=west,south=south,east=east,north=north,zoom=8.25)
            self.assertEqual({(c['lng'],c['lat']) for c in payload['clusters']},
                             {(114,35),(114.002,35),(114.004,35)})
            self.assertEqual(sum(c['cluster_size'] for c in payload['clusters']),5005)
            self.assertEqual(sum(c['count'] for c in payload['clusters']),15015)

    def test_far_overview_aggregation_conserves_records(self):
        payload=self.get(west=100,south=20,east=130,north=50,zoom=5)
        self.assertEqual(sum(c['cluster_size'] for c in payload['clusters']),5003)
        self.assertEqual(sum(c['count'] for c in payload['clusters']),15013)

    def test_filters_precede_cluster_and_pagination(self):
        result = self.get(zoom=15, protection='国家二级', start='2021-01-01', end='2021-01-01', page_size=1)
        self.assertEqual([r['id'] for r in result['results']], [self.other.pk])
        self.assertEqual(result['viewport']['bird_count'], 7)
        self.assertFalse(result['has_more'])
        self.assertEqual(sum(c['cluster_size'] for c in result['clusters']), 1)

    def test_statistics_do_not_follow_viewport_or_page_limit(self):
        result = self.get(west=110,south=30,east=111,north=31,zoom=15,page_size=1)
        self.assertEqual(result['viewport']['total_records'], 0)
        self.assertEqual(result['stats']['total_records'], 5003)

    def test_years_ignore_selected_date_but_respect_protection_and_status(self):
        self.assertEqual(self.get('/api/monitoring/years/', start='2099-01-01')['years'], [2020,2021])
        self.assertEqual(self.get('/api/monitoring/years/', protection='国家二级')['years'], [2021])
        self.assertEqual(self.get('/api/monitoring/years/', protection='三有动物')['years'], [])

    def test_buffer_complete_totals_routes_and_page_limit(self):
        result = self.get('/api/monitoring/buffer/',lng=114,lat=35)
        self.assertEqual(result['summary']['matched_records'],5003)
        self.assertEqual(result['summary']['bird_count'],15013)
        self.assertEqual(result['summary']['species_count'],2)
        self.assertEqual(result['summary']['matched_routes'],1)
        self.assertEqual(len(result['results']),5000)
        self.assertTrue(result['has_more'])
        self.assertEqual(result['buffer']['geometry']['type'],'Polygon')

    def test_buffer_filters_before_limit(self):
        result = self.get('/api/monitoring/buffer/',lng=114,lat=35,protection='国家二级',start='2021-01-01',end='2021-01-01',page_size=1)
        self.assertEqual(result['summary']['bird_count'],7)
        self.assertEqual(result['summary']['total_records'],1)
        self.assertFalse(result['has_more'])

    def test_geography_distance_is_in_metres_at_high_latitude(self):
        for lng in (30.008,30.011):
            ObservationRecord.objects.create(species=self.first,zone=self.zone,observation_time='2020-01-01',status='approved',location=Point(lng,60,srid=4326))
        result = self.get('/api/monitoring/buffer/',lng=30,lat=60,radius=500)
        self.assertEqual(result['summary']['matched_records'],1)
        self.assertAlmostEqual(result['results'][0]['lng'],30.008)

    def test_coordinate_fallback(self):
        ObservationRecord.objects.create(species=self.first,zone=self.zone,observation_time='2020-01-01',status='approved')
        ObservationRecord.objects.bulk_create([ObservationRecord(species=self.first,zone=self.zone,observation_time='2020-01-01',status='approved',longitude=114,latitude=35)])
        result=self.get('/api/monitoring/buffer/',lng=114,lat=35)
        self.assertEqual(result['summary']['matched_records'],5005)

    def test_csv_exports_full_scope_with_bom_and_safe_cells(self):
        response=self.client.get('/api/monitoring/buffer.csv',dict(lng=114,lat=35,page_size=1))
        self.assertEqual(response.status_code,200)
        content=b''.join(response.streaming_content).decode('utf-8-sig')
        rows=list(csv.reader(io.StringIO(content)))
        self.assertEqual(len(rows),5004)
        self.assertEqual(rows[0][6],'鸟类数量（只）')
        self.assertEqual(rows[-1][9], '\' =HYPERLINK("危险"),逗号\n换行')
        self.assertEqual(rows[-1][10],'缓冲范围内全部已审核且符合筛选的记录')

    def test_formula_prefixes(self):
        for value in ('=1+1','+cmd','-cmd','@SUM(A1)',' \t=1','\tvalue','\rvalue','\nvalue','\x00=cmd','\v=1'):
            self.assertTrue(csv_cell(value).startswith("'"),value)
        self.assertEqual(csv_cell('正常中文,换行\n内容'),'正常中文,换行\n内容')
        self.assertEqual(csv_cell(-114.5), '-114.5')

    def test_detail_hides_unapproved_and_uses_complete_chart_counts(self):
        self.assertEqual(self.client.get(f'/api/monitoring/records/{self.pending.pk}/').status_code,404)
        result=self.get(f'/api/monitoring/records/{self.other.pk}/')
        self.assertEqual(result['stats']['total_records'],5003)
        self.assertEqual(result['species_zones'][0]['records'],1)
        self.assertEqual(self.client.get(f'/api/monitoring/records/{self.other.pk}/',{'protection':'国家一级'}).status_code,404)

    def test_invalid_and_nonfinite_parameters(self):
        for params in ({'zoom':'nan'},{'page_size':5001,'zoom':15},{'after':-1,'zoom':15},
                       {'start':'2020-02-30'},{'start':'2022-01-01','end':'2020-01-01'},
                       {'bbox':'nan,0,1,1'},{'bbox':'0,1,0,2'},{'protection':'无效'}):
            self.assertEqual(self.client.get('/api/map-observations/',params).status_code,400,params)
        for params in ({'lng':114,'lat':35,'radius':49},{'lng':114,'lat':35,'radius':10001},
                       {'lng':'inf','lat':35},{'lng':114,'lat':'nan'},{}):
            self.assertEqual(self.client.get('/api/monitoring/buffer/',params).status_code,400,params)

    def test_empty_buffer_and_filtered_csv(self):
        result=self.get('/api/monitoring/buffer/',lng=0,lat=0,radius=50)
        self.assertEqual(result['summary']['bird_count'],0)
        self.assertEqual(result['results'],[])
        response=self.client.get('/api/monitoring/buffer.csv',dict(lng=114,lat=35,protection='国家二级'))
        self.assertEqual(len(list(csv.reader(io.StringIO(b''.join(response.streaming_content).decode('utf-8-sig'))))),2)
