import io
import json
import zipfile
from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase
from docx import Document
from docx.oxml.ns import qn

from .models import ObservationRecord, SpeciesInfo, WetlandZone
from .monitoring_report import collect_report_data, report_period, write_assessment


def sample_data():
    species = [{'name': '白鹤', 'level': '国家一级', 'birds': 20, 'records': 3},
               {'name': '喜鹊', 'level': '三有动物', 'birds': 3, 'records': 2}]
    return {
        'current': {'records': 5, 'birds': 23, 'species': 2, 'sites': 1},
        'previous': {'records': 0, 'birds': 0, 'species': 0, 'sites': 0},
        'series': [0, 23], 'previous_series': [0, 0], 'site_series': [0, 1],
        'protection': {'国家一级': 20, '国家二级': 0, '三有动物': 3, '其他': 0},
        'protection_species': {'国家一级': 1, '国家二级': 0, '三有动物': 1, '其他': 0},
        'top_species': species, 'species_inventory': species,
    }


class MonitoringReportTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.period = report_period('monthly', 2024, 2, date(2024, 3, 1))

    def test_calendar_and_partial_comparison(self):
        self.assertEqual(self.period['end'], date(2024, 2, 29))
        self.assertEqual(self.period['previous_end'], date(2023, 2, 28))
        partial = report_period('annual', 2024, None, date(2024, 2, 29))
        self.assertTrue(partial['partial'])
        self.assertEqual(partial['previous_end'], date(2023, 2, 28))
        for kind, year, month in [('annual', True, 1), ('annual', 2025, None),
                                  ('monthly', 2024, 12), ('monthly', 2024, True),
                                  ('bad', 2024, None)]:
            with self.assertRaises(ValueError):
                report_period(kind, year, month, date(2024, 3, 1))

    def test_empty_and_invalid_model_content(self):
        data = sample_data()
        with patch('app_monitor.monitoring_report._request_deepseek', return_value=('{"results":"999"}', None)) as provider:
            text, source = write_assessment(self.period, data)
            self.assertEqual(source, '平台数据摘要')
            self.assertIn('上年同期没有', text['comparison'][0])
            self.assertTrue(provider.call_args.kwargs['json_mode'])
        data['current']['records'] = 0
        with patch('app_monitor.monitoring_report._request_deepseek') as provider:
            text, source = write_assessment(self.period, data)
            provider.assert_not_called()
            self.assertIn('没有已审核', text['results'][0])

    def test_valid_model_sections_cached(self):
        paragraph = ('本期记录可用于识别需要复核的时间段和物种。开展跨期比较时，'
                     '应先核对调查覆盖和审核进度是否一致，并将实际观察投入与数据共同归档。'
                     '对于记录集中的时段，应核查群体计数方式和重复上报情况，以明确当前统计能够支持的解释范围。')
        draft = {key: [paragraph, paragraph] for key in ('results', 'comparison', 'recommendations')}
        wrapped = '```json\n' + json.dumps(draft) + '\n```'
        with patch('app_monitor.monitoring_report._request_deepseek', return_value=(wrapped, None)) as provider:
            self.assertEqual(write_assessment(self.period, sample_data()), (draft, 'DeepSeek 辅助研判'))
            self.assertEqual(write_assessment(self.period, sample_data()), (draft, 'DeepSeek 辅助研判'))
            self.assertEqual(provider.call_count, 1)

    def test_bounded_extra_model_paragraphs_are_retained(self):
        paragraph = ('本期记录可用于识别需要复核的时间段和物种。开展跨期比较时，'
                     '应先核对调查覆盖和审核进度是否一致，并将实际观察投入与数据共同归档。'
                     '对于记录集中的时段，应核查群体计数方式和重复上报情况，以明确当前统计能够支持的解释范围。')
        draft = {key: [paragraph] * (6 if key == 'results' else 2)
                 for key in ('results', 'comparison', 'recommendations')}
        with patch('app_monitor.monitoring_report._request_deepseek', return_value=(json.dumps(draft), None)):
            self.assertEqual(write_assessment(self.period, sample_data()), (draft, 'DeepSeek 辅助研判'))

    def test_complete_sections_survive_a_truncated_reply(self):
        paragraph = ('本期记录可用于识别需要复核的时间段和物种。开展跨期比较时，'
                     '应先核对调查覆盖和审核进度是否一致，并将实际观察投入与数据共同归档。'
                     '对于记录集中的时段，应核查群体计数方式和重复上报情况，以明确当前统计能够支持的解释范围。')
        text = '{"results":' + json.dumps([paragraph, paragraph]) + ',"comparison": ["未完成'
        with patch('app_monitor.monitoring_report._request_deepseek', return_value=(text, None)):
            draft, source = write_assessment(self.period, sample_data())
        self.assertEqual(source, 'DeepSeek 辅助研判与平台数据摘要')
        self.assertEqual(draft['results'], [paragraph, paragraph])
        self.assertIn('上年同期没有', draft['comparison'][0])

    def test_download_is_docx_and_rejects_invalid_period(self):
        client = Client()
        self.assertEqual(client.get('/api/ai/monitoring-report/').status_code, 405)
        self.assertEqual(client.post('/api/ai/monitoring-report/', data='[]', content_type='application/json').status_code, 400)
        with patch('app_monitor.monitoring_report.collect_report_data', return_value=sample_data()), patch(
            'app_monitor.monitoring_report._request_deepseek', return_value=(None, 'offline'),
        ):
            response = client.post('/api/ai/monitoring-report/', data=json.dumps({
                'kind': 'monthly', 'year': 2024, 'month': 2,
            }), content_type='application/json')
            self.assertEqual(response.status_code, 200)
            content = b''.join(response.streaming_content)
        with zipfile.ZipFile(io.BytesIO(content)) as package:
            xml = package.read('word/document.xml').decode()
            self.assertIn('2024年2月鸟类监测月度报告', xml)
            self.assertIn('白鹤', xml)
            self.assertIn('基期为零', xml)
            self.assertIn('国家一级和二级合计记录 1 种、20 只次', xml)
            self.assertEqual(len([name for name in package.namelist() if name.startswith('word/media/')]), 7)
            self.assertIn('仿宋_GB2312', package.read('word/styles.xml').decode())
            self.assertIn('黑体', package.read('word/styles.xml').decode())
            self.assertNotIn('D9D9D9', xml)
        document = Document(io.BytesIO(content))
        paragraphs = document.paragraphs
        self.assertIn('本期数据概况见表1。本报告由黄河生态方舟平台小舟智能体生成，供监测工作参考和人工复核。',
                      [paragraph.text for paragraph in paragraphs])
        title_styles = {'Title', 'Heading 1', 'Heading 2', 'Caption'}
        self.assertTrue(title_styles.issubset({paragraph.style.name for paragraph in paragraphs}))
        for paragraph in paragraphs:
            if paragraph.style.name in title_styles:
                for run in paragraph.runs:
                    self.assertEqual(str(run.font.color.rgb), '000000', paragraph.text)
        body_style = document.styles['Report Body']
        self.assertEqual(body_style.font.size.pt, 12)
        self.assertEqual(body_style.paragraph_format.line_spacing, 1.25)
        self.assertEqual(body_style.element.pPr.ind.get(qn('w:firstLineChars')), '200')
        self.assertEqual(len([p for p in paragraphs if p.style.name == 'Caption' and p.text.startswith('图')]), 5)
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_download_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/ai/monitoring-report/', data='{}',
                                     content_type='application/json').status_code, 403)


class ReportAggregationTests(TestCase):
    def test_approved_records_and_previous_period_are_separate(self):
        species = SpeciesInfo.objects.create(name_cn='报告测试白鹤', protection_level='国家一级')
        zone = WetlandZone.objects.create(name='报告测试点位', longitude=113.123456, latitude=34.123456)
        for day, count, status in [('2024-02-02', 7, 'approved'), ('2024-02-29', 3, 'approved'),
                                   ('2023-02-28', 2, 'approved'), ('2024-03-01', 5, 'approved'),
                                   ('2024-02-02', 900, 'pending')]:
            ObservationRecord.objects.create(species=species, zone=zone, observation_time=day,
                                             count=count, status=status)
        period = report_period('monthly', 2024, 2, date(2024, 3, 1))
        data = collect_report_data(period)
        self.assertEqual(data['current'], dict(records=2, birds=10, species=1, sites=1))
        self.assertEqual(data['previous'], dict(records=1, birds=2, species=1, sites=1))
        self.assertEqual(len(data['series']), 29)
        self.assertEqual(data['series'][1], 7)
        self.assertEqual(data['series'][-1], 3)
        self.assertEqual(data['site_series'], [int(day in (2, 29)) for day in range(1, 30)])
        self.assertEqual(data['protection']['国家一级'], 10)
        self.assertEqual(data['protection_species']['国家一级'], 1)
        self.assertNotIn('报告测试点位', json.dumps(data, ensure_ascii=False))
        self.assertNotIn('113.123456', json.dumps(data))
