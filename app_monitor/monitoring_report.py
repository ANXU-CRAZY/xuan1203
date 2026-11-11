"""Period selection, approved-record aggregates and report download."""
import calendar
import json
import logging
import re
from datetime import date
from hashlib import sha256
from pathlib import Path

from django.core.cache import cache
from django.db.models import Count, Sum
from django.db.models.functions import ExtractDay, ExtractMonth
from django.http import FileResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ObservationRecord
from .protection import get_protection_group
from .views import _get_deepseek_model, _request_deepseek

ASSETS = Path(__file__).with_name('report_assets')
LEVELS = ('国家一级', '国家二级', '三有动物', '其他')
SECTIONS = ('results', 'comparison', 'recommendations')
logger = logging.getLogger(__name__)


def report_period(kind, year, month, today):
    if type(year) is not int or not 1900 <= year <= today.year:
        raise ValueError('请选择有效年份。')
    if kind == 'annual':
        start, end = date(year, 1, 1), date(year, 12, 31)
        title = f'{year}年鸟类监测年度报告'
    elif kind == 'monthly' and type(month) is int and 1 <= month <= 12:
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        title = f'{year}年{month}月鸟类监测月度报告'
    else:
        raise ValueError('请选择年度报告，或为月度报告选择有效月份。')
    if start > today:
        raise ValueError('不能生成未来时段的监测报告。')
    previous_year = year - 1
    previous_start = start.replace(year=previous_year)
    cutoff = min(end, today)
    comparison_end = cutoff.replace(
        year=previous_year,
        day=(calendar.monthrange(previous_year, cutoff.month)[1] if cutoff == end
             else min(cutoff.day, calendar.monthrange(previous_year, cutoff.month)[1])),
    )
    return {
        'kind': kind, 'title': title, 'start': start, 'end': cutoff,
        'previous_start': previous_start, 'previous_end': comparison_end,
        'partial': cutoff < end,
    }


def approved(start, end):
    return ObservationRecord.objects.filter(
        status='approved', observation_time__range=(start, end),
    ).order_by()


def collect_report_data(period):
    current = approved(period['start'], period['end'])
    previous = approved(period['previous_start'], period['previous_end'])
    totals = dict(records=Count('pk'), birds=Sum('count', default=0),
                  species=Count('species_id', distinct=True), sites=Count('zone_id', distinct=True))
    group = ExtractMonth if period['kind'] == 'annual' else ExtractDay

    def series(query, end, **metrics):
        buckets = {
            row['bucket']: row for row in query.annotate(bucket=group('observation_time'))
            .values('bucket').annotate(**metrics)
        }
        length = end.month if group is ExtractMonth else end.day
        return {
            name: [buckets.get(i, {}).get(name, 0) for i in range(1, length + 1)]
            for name in metrics
        }

    current_series = series(current, period['end'], birds=Sum('count'), sites=Count('zone_id', distinct=True))
    previous_series = series(previous, period['previous_end'], birds=Sum('count'))

    protection = dict.fromkeys(LEVELS, 0)
    for level, birds in current.values_list('species__protection_level').annotate(birds=Sum('count')):
        category = get_protection_group(level)
        protection[category if category in protection else '其他'] += birds
    species_inventory = list(
        current.values('species__name_cn', 'species__protection_level')
        .annotate(birds=Sum('count'), records=Count('pk'))
        .order_by('-birds', 'species__name_cn')
    )
    result = {
        'current': current.aggregate(**totals),
        'previous': previous.aggregate(**totals),
        'series': current_series['birds'],
        'previous_series': previous_series['birds'],
        'site_series': current_series['sites'],
        'protection': protection,
        'species_inventory': [{
            'name': row['species__name_cn'],
            'level': get_protection_group(row['species__protection_level']),
            'birds': row['birds'], 'records': row['records'],
        } for row in species_inventory],
    }
    result['top_species'] = result['species_inventory'][:8]
    result['protection_species'] = dict.fromkeys(LEVELS, 0)
    for species in result['species_inventory']:
        level = species['level']
        result['protection_species'][level if level in LEVELS else '其他'] += 1
    return result


def parse_editor_sections(content):
    """Keep complete, usable sections if a gateway truncates the response."""
    if not content:
        return {}
    opening, closing = content.find('{'), content.rfind('}')
    decoder = json.JSONDecoder(strict=False)
    try:
        draft = decoder.decode(content[opening:closing + 1])
    except ValueError:
        draft = {}
        for section in SECTIONS:
            field = re.search(rf'"{section}"\s*:\s*', content)
            if field:
                try:
                    draft[section], _ = decoder.raw_decode(content, field.end())
                except ValueError:
                    continue
    if not isinstance(draft, dict):
        return {}

    accepted = {}
    for section in SECTIONS:
        paragraphs = draft.get(section)
        if not isinstance(paragraphs, list):
            continue
        cleaned = [' '.join(text.split()) for text in paragraphs if isinstance(text, str)
                   and 70 <= len(text.strip()) <= 350 and not any(char.isdigit() for char in text)]
        cleaned = cleaned[:6]
        if len(cleaned) >= 2 and sum(len(text) for text in cleaned) <= 1600:
            accepted[section] = cleaned
    return accepted


def write_assessment(period, data):
    current, previous = data['current'], data['previous']
    if not current['records']:
        return {
            'results': ['本期没有已审核观测记录，现有数据不足以开展物种组成和数量结构分析。应先核对统计时段与审核状态，再确认现场调查资料是否完成入库。报告中的零值仅表示当前查询未命中记录，不作为鸟类未出现或区域生境退化的证据。'],
            'comparison': ['本期缺少可比较的观测资料，不能依据空白记录与上年同期数量之间的差值评价鸟类活动变化。建议在补齐可核实资料后，按相同时间范围和审核标准重新生成报告，并同步保留调查工作量信息。'],
            'recommendations': ['优先核对调查任务执行情况、上报完整性与审核进度，明确本期空白出现在哪个环节。对能够核实的现场资料补充规范记录，保留物种鉴定依据与重复记录处理说明，待资料完整后再开展比较分析。'],
        }, '平台数据摘要'
    peak = max(range(len(data['series'])), key=data['series'].__getitem__) + 1
    unit = '月' if period['kind'] == 'annual' else '日'
    fallback = {
        'results': [f"累计观测只次最高的物种为{data['top_species'][0]['name']}，按{unit}汇总的最高值出现在第{peak}{unit}。"
                    '时序集中与物种排序描述了已入库资料的分布，为后续选择需要复核的时间段和观测记录提供依据。'
                    '对记录较多的物种，应结合原始鉴定资料、群体计数方式及重复上报情况逐项核查，避免将资料集中等同于稳定的种群优势。',
                    '保护等级构成应与物种清单结合使用。少量重点保护物种记录也值得保留鉴定材料和审核轨迹，'
                    '而较多的其他类记录可用于了解平台观测覆盖。两类信息分别服务于重点记录复核与常规资料积累，'
                    '不宜仅按数量排序决定全部监测工作。'],
        'comparison': [(
            '同比反映已审核记录的变化。调查频次、覆盖范围和审核进度都会影响记录数量，不能据此判断种群增减。'
            if previous['records'] else '上年同期没有已审核记录，暂不能计算有效的同比变化。'
        ) + '比较前应检查两期是否覆盖相同点位、是否包含相同类型的调查以及数据审核是否同步完成。'
            '若这些条件存在差异，应先列明差异，再讨论能够支持的记录变化，避免把观测投入变化解释为生态过程。',
            '当前统计属于描述性汇总，尚未控制调查工作量、个体重复观测与检测概率。'
            '因此，报告可支持识别资料中的重点时段和核查对象，关于迁徙节律、生境利用和长期变化的判断仍需更连续且可比的调查资料。'],
        'recommendations': [
            '对重点保护物种和数量异常集中的记录建立复核清单，核对观测日期、鉴定依据及群体计数方式。'
            '复核发现的问题应回到原始记录处理，保留更正原因和审核轨迹，避免只修改汇总表而失去追溯依据。',
            '后续调查应同步记录观察时长、天气、可视范围、样线覆盖及主要干扰情况。'
            '优先维持固定点位和固定时间窗口的连续观测，再根据本期资料空缺补充调查。每次阶段汇总后，'
            '比较资料完整性和审核覆盖，并将需要进一步确认的问题转化为下一期可执行的调查任务。',
        ],
    }
    # Send aggregate statistics only. Exclude free text and individual records.
    context = {
        'period_type': period['kind'], 'partial': period['partial'],
        **{key: value for key, value in data.items() if key != 'species_inventory'},
    }
    serialized = json.dumps(context, ensure_ascii=False, sort_keys=True)
    prompt = (ASSETS / 'deepseek_editor.md').read_text(encoding='utf-8')
    key = 'monitoring-editor:v2:' + sha256((prompt + _get_deepseek_model() + serialized).encode()).hexdigest()
    cached = cache.get(key)
    if cached:
        return cached
    if not cache.add('monitoring-editor-request', True, timeout=15):
        return fallback, '平台数据摘要'
    content, error = _request_deepseek([
        {'role': 'system', 'content': prompt},
        {'role': 'user', 'content': serialized},
    ], max_tokens=3200, timeout=22, json_mode=True)
    draft = parse_editor_sections(content)
    if not draft:
        logger.info('Monitoring report used local assessment (%s)', 'provider unavailable' if error else 'invalid draft')
        return fallback, '平台数据摘要'
    source = 'DeepSeek 辅助研判' if len(draft) == len(SECTIONS) else 'DeepSeek 辅助研判与平台数据摘要'
    result = ({**fallback, **draft}, source)
    cache.set(key, result, timeout=3600)
    return result


@require_POST
def download(request):
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise ValueError('请选择报告时段。')
        period = report_period(payload.get('kind'), payload.get('year'), payload.get('month'), timezone.localdate())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'detail': '请求不是有效的 JSON。'}, status=400)
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)

    from .monitoring_report_docx import build_docx

    data = collect_report_data(period)
    assessment, source = write_assessment(period, data)
    response = FileResponse(
        build_docx(period, data, assessment, source, generated_on=timezone.localdate()),
        as_attachment=True, filename=period['title'] + '.docx',
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    response['Cache-Control'] = 'private, no-store'
    return response
