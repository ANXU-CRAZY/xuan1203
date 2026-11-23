"""Monthly bird observations grouped by chainage along a project river line."""
import calendar
import json
import math
from datetime import date
from pathlib import Path

from django.contrib.gis.gdal import CoordTransform, SpatialReference
from django.contrib.gis.geos import LineString, Point
from django.db import DatabaseError
from django.http import JsonResponse
from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .monitoring import observations, within
from .workbench_access import may_compute, owner_id
from .views import _request_deepseek


SAMPLE = Path(__file__).parent / 'static/app_monitor/workbench/yellow-river.geolibre.json'
SEGMENT = 5000
MAX_ROWS = 30000


@require_POST
@csrf_protect
def interpret(request):
    if not may_compute(request):
        return JsonResponse({'detail': '请登录后使用河段分析。'}, status=403)
    try:
        if request.content_type != 'application/json' or len(request.body) > 8000:
            raise ValueError
        message = json.loads(request.body)['message']
        if not isinstance(message, str) or not 1 <= len(message) <= 800:
            raise ValueError
    except (ValueError, TypeError, KeyError):
        return JsonResponse({'detail': '请输入调查需求。'}, status=400)
    key = 'river-survey:interpret:' + owner_id(request)
    cache.add(key, 0, 60)
    if cache.incr(key) > 12:
        return JsonResponse({'detail': '请稍后再试，或直接选择分析条件。'}, status=429)
    system = (
        '从用户原话提取河段水鸟调查参数，只输出 JSON。今天为' + timezone.localdate().isoformat() +
        '。只填写用户明确指定的字段，其余省略。metric 为 individuals(累计只数)、species(物种去重)、'
        'records(记录条数)；“哪里鸟多”有歧义，省略metric。month 为YYYY-MM；radius_km 为沿岸距离，'
        '单位公里；bird 为指定的物种中文名；landscape 为是否要求出图。支持单个公历月份、单种或全部鸟、'
        '沿河道每5公里排名、100米至20公里范围。其他要求如同比、跨月、不同分段长度、栖息地预测、'
        '删除数据，必须在 limitation 字段说明，并让用户选择调整，不能忽略。不要编造参数或结果。'
    )
    output, error = _request_deepseek([{'role': 'system', 'content': system},
                                      {'role': 'user', 'content': message}], max_tokens=320, timeout=15, json_mode=True)
    try:
        fields = json.loads(output) if not error else None
        if not isinstance(fields, dict):
            raise ValueError
        result = {}
        if fields.get('metric') in ('individuals', 'species', 'records'):
            result['metric'] = fields['metric']
        if fields.get('month'):
            date.fromisoformat(fields['month'] + '-01')
            result['month'] = fields['month']
        km = fields.get('radius_km')
        if km is not None:
            if type(km) not in (int, float) or not 0.1 <= km <= 20:
                result['limitation'] = '沿岸距离支持 0.1 至 20 公里，请调整。'
            else:
                result['radius_km'] = km
        for field in ('bird', 'limitation'):
            if isinstance(fields.get(field), str) and fields[field]:
                result[field] = fields[field][:160]
        result['landscape'] = fields.get('landscape') is True
        return JsonResponse(result)
    except (ValueError, TypeError):
        return JsonResponse({'detail': '语言解析暂时不可用，请核对下方调查条件。'}, status=503)


def projected_river(coords):
    if not isinstance(coords, list) or not 2 <= len(coords) <= 2000:
        raise ValueError('请选择一条包含 2 至 2000 个顶点的连续河道中心线。')
    for pair in coords:
        if (not isinstance(pair, list) or len(pair) < 2 or
                any(type(v) not in (float, int) for v in pair[:2]) or
                not (94 <= pair[0] <= 121 and 30 <= pair[1] <= 43)):
            raise ValueError('河道坐标应为黄河研究区的 WGS84 经纬度。')
    line = LineString([p[:2] for p in coords], srid=4326)
    west, _, east, _ = line.extent
    zone = int(((west + east) / 2 + 180) // 6) + 1
    projected = SpatialReference(32600 + zone)
    forward = CoordTransform(SpatialReference(4326), projected)
    line.transform(forward)
    if not 1 <= line.length <= 500000 or east - west > 6:
        raise ValueError('请选择长度在 1 米至 500 公里之间的区域河段。')
    return line, forward, CoordTransform(projected, SpatialReference(4326))


def split_line(line):
    """Preserve the bends and split at exact metric distances."""
    coords = line.coords
    parts, part = [], [coords[0]]
    travelled = 0.0
    for a, b in zip(coords, coords[1:]):
        length = math.dist(a, b)
        if length == 0:
            continue
        end = travelled + length
        boundary = (len(parts) + 1) * SEGMENT
        while boundary < end:
            fraction = (boundary - travelled) / length
            cut = tuple(x + fraction * (y - x) for x, y in zip(a, b))
            if cut != part[-1]:
                part.append(cut)
            parts.append(part)
            part = [cut]
            boundary += SEGMENT
        part.append(b)
        travelled = end
    if len(part) > 1:
        parts.append(part)
    return parts


def summarize(line, forward, reverse, rows, radius):
    parts = split_line(line)
    stats = [dict(records=0, individuals=0, missing_species=0, species=set(), days=set()) for _ in parts]
    for index, (x, y, day, number, species) in enumerate(rows):
        if index >= MAX_ROWS:
            raise ValueError('候选记录超过三万条，请缩小河道范围。')
        point = Point(x, y, srid=4326)
        point.transform(forward)
        if line.distance(point) > radius:
            continue
        # Intervals are left-closed, with the terminal endpoint in the last reach.
        item = stats[min(int(line.project(point) // SEGMENT), len(stats) - 1)]
        item['records'] += 1
        item['individuals'] += number
        item['days'].add(day)
        if species is None:
            item['missing_species'] += 1
        else:
            item['species'].add(species)
    result = []
    for i, (coords, item) in enumerate(zip(parts, stats)):
        reach = LineString(coords, srid=line.srid)
        reach.transform(reverse)
        result.append(dict(name=f'河段 {i + 1}', start_km=i * SEGMENT / 1000,
                           end_km=round(min((i + 1) * SEGMENT, line.length) / 1000, 2),
                           geometry=json.loads(reach.geojson),
                           **{k: len(v) if isinstance(v, set) else v for k, v in item.items()}))
    return result


@require_POST
@csrf_protect
def analyze(request):
    if not may_compute(request):
        return JsonResponse({'detail': '请登录后使用河段分析。'}, status=403)
    try:
        if request.content_type != 'application/json' or len(request.body) > 160000:
            raise ValueError('河段请求格式不正确或过大。')
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('请输入河段分析参数。')
        start = date.fromisoformat(str(data.get('month', '')) + '-01')
        end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
        radius = data.get('radius')
        bird = data.get('bird', '')
        if not isinstance(bird, str) or len(bird) > 100:
            raise ValueError('物种名称过长。')
        if type(radius) not in (int, float) or not 100 <= radius <= 20000:
            raise ValueError('沿岸距离须在 100 米至 20 公里之间。')
        line, forward, reverse = projected_river(data.get('coordinates'))
        if data.get('source') == 'sample':
            layers = json.loads(SAMPLE.read_text(encoding='utf-8'))['layers']
            points = next(layer for layer in layers if layer['id'] == 'sample-points')
            rows = []
            for feature in points['geojson']['features']:
                props = feature['properties']
                day = date.fromisoformat(props['观测日期'])
                if start <= day <= end and (not bird or bird == props['物种']):
                    rows.append((*feature['geometry']['coordinates'], day, props['数量（模拟）'], props['物种']))
            source = '模拟观测记录'
        elif data.get('source') == 'approved':
            # Apply the dashboard's approval and coordinate fallback rules before aggregation.
            envelope = line.buffer(radius + 1000)
            envelope.transform(reverse)
            qs = within(observations(request, dates=False), envelope.extent).filter(observation_time__range=(start, end))
            if bird:
                qs = qs.filter(species__name_cn=bird)
            rows = qs.values_list('lng', 'lat', 'observation_time', 'count', 'species_id')[:MAX_ROWS + 1].iterator()
            source = '平台已审核观测（缺少实测位置时采用监测点位）'
        else:
            raise ValueError('请选择观测数据来源。')
        result = summarize(line, forward, reverse, rows, radius)
    except (ValueError, TypeError, OverflowError) as error:
        return JsonResponse({'detail': str(error)}, status=400)
    except DatabaseError:
        return JsonResponse({'detail': '观测数据库暂时不可用，请稍后再试。'}, status=503)
    return JsonResponse(dict(reaches=result, source=source, month=start.strftime('%Y-%m'),
                             radius=radius, epsg=line.srid))
