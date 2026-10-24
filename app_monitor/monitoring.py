"""Public 2D monitoring queries against the original, authoritative models.

All spatial/statistical filters precede aggregation and pagination.  The map
cache is deliberately not an authority for approval or protection changes.
"""
import csv
import json
import math
import re
from functools import wraps

from django.contrib.gis.db.models import PointField
from django.contrib.gis.db.models.functions import IsEmpty, IsValid
from django.contrib.gis.geos import Point
from django.db import connection
from django.db.models import Avg, Case, Count, F, FloatField, Func, Min, Q, Sum, Value, When
from django.db.models.functions import Cast, Coalesce, ExtractYear, Floor
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET

from .models import MonitoringRoute, ObservationRecord, SpeciesInfo
from .protection import get_protection_group

LEVELS = ('国家一级', '国家二级', '三有动物', '无危/其他')
# 地图首屏/高缩放明细采用 1 万条分段加载，恢复原版的快速首批点位体验。
# 缓冲分析仍使用较小的通用分页上限，避免分析面板一次占用过多内存。
PAGE_LIMIT = 5000
MAP_PAGE_LIMIT = 10000
MAP_PREVIEW_LIMIT = 10000


def endpoint(func):
    @require_GET
    @wraps(func)
    def view(request, *args, **kwargs):
        try:
            return func(request, *args, **kwargs)
        except ValueError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)
    return view


def number(request, name, default=None, lower=None, upper=None):
    try:
        value = float(request.GET.get(name, default))
    except (ValueError, TypeError):
        raise ValueError(f'{name} 必须是有效数字')
    if not math.isfinite(value) or (lower is not None and value < lower) or (upper is not None and value > upper):
        raise ValueError(f'{name} 超出允许范围（{lower}—{upper}）')
    return value


def integer(request, name, default, lower, upper):
    value = number(request, name, default, lower, upper)
    if value != int(value):
        raise ValueError(f'{name} 必须是整数')
    return int(value)


def bbox(request):
    if request.GET.get('bbox'):
        parts = request.GET['bbox'].split(',')
        if len(parts) != 4:
            raise ValueError('地图范围需要四个坐标')
        try:
            west, south, east, north = map(float, parts)
        except ValueError:
            raise ValueError('地图范围必须是有效数字')
    elif any(key in request.GET for key in ('west', 'south', 'east', 'north')):
        west, south, east, north = [number(request, key) for key in ('west', 'south', 'east', 'north')]
    else:
        return None
    if not all(math.isfinite(v) for v in (west, south, east, north)) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError('地图范围超出有效经纬度或顺序错误')
    return west, south, east, north


def _coordinate_point(prefix=''):
    return Case(When(
        Q(**{prefix + 'longitude__gte': -180, prefix + 'longitude__lte': 180,
             prefix + 'latitude__gte': -90, prefix + 'latitude__lte': 90}),
        then=Func(F(prefix + 'longitude'), F(prefix + 'latitude'),
                  template='ST_SetSRID(ST_MakePoint(%(expressions)s), 4326)',
                  output_field=PointField(srid=4326))), output_field=PointField(srid=4326))


def observations(request, *, dates=True):
    """Same coordinate precedence as the original dashboard; approved only."""
    qs = ObservationRecord.objects.filter(status='approved').order_by().annotate(
        geom=Coalesce('location', _coordinate_point(), 'zone__location', _coordinate_point('zone__'),
                      output_field=PointField(srid=4326)))
    qs = qs.annotate(lng=Func('geom', function='ST_X', output_field=FloatField()),
                     lat=Func('geom', function='ST_Y', output_field=FloatField()))
    qs = qs.filter(lng__gte=-180, lng__lte=180, lat__gte=-90, lat__lte=90)
    protection = request.GET.get('protection') or request.GET.get('protection_filter') or 'all'
    if protection not in ('all', *LEVELS):
        raise ValueError('保护等级筛选无效')
    if protection != 'all':
        ids = [pk for pk, level in SpeciesInfo.objects.values_list('pk', 'protection_level')
               if get_protection_group(level) == protection]
        qs = qs.filter(species_id__in=ids)
    if dates:
        parsed = []
        for name, alias in (('start', 'start_date'), ('end', 'end_date')):
            raw = request.GET.get(name) or request.GET.get(alias) or ''
            try:
                date = parse_date(raw) if raw else None
            except ValueError:
                date = None
            if raw and date is None:
                raise ValueError('日期格式应为 年-月-日')
            parsed.append(date)
        start, end = parsed
        if start and end and start > end:
            raise ValueError('开始日期不能晚于结束日期')
        if start:
            qs = qs.filter(observation_time__gte=start)
        if end:
            qs = qs.filter(observation_time__lte=end)
    return qs


def within(qs, bounds):
    if bounds:
        west, south, east, north = bounds
        qs = qs.filter(lng__gte=west, lng__lte=east, lat__gte=south, lat__lte=north)
    return qs


def totals(qs):
    result = qs.aggregate(total_records=Count('pk'), bird_count=Coalesce(Sum('count'), 0),
                          species_count=Count('species_id', distinct=True))
    result['matched_records'] = result['total_records']
    return result


def statistics(qs):
    result = totals(qs)
    distribution = {level: {'level': level, 'count': 0, 'records': 0} for level in LEVELS}
    for row in qs.values('species__protection_level').annotate(birds=Sum('count'), records=Count('pk')):
        item = distribution[get_protection_group(row['species__protection_level'])]
        item['count'] += row['birds'] or 0
        item['records'] += row['records']
    result.update(
        approved_count=result['total_records'],
        protected_count=sum(distribution[level]['records'] for level in LEVELS[:2]),
        protection_distribution=list(distribution.values()),
        top_species=[{'name': row['species__name_cn'], 'latin': row['species__name_latin'],
                      'level': get_protection_group(row['species__protection_level']),
                      'count': row['birds'] or 0, 'records': row['records']}
                     for row in qs.values('species_id', 'species__name_cn', 'species__name_latin',
                                          'species__protection_level').annotate(birds=Sum('count'), records=Count('pk'))
                     .order_by('-birds', 'species_id')[:10]],
        yearly_trend=[{'year': row['year'], 'count': row['records'], 'bird_count': row['birds'] or 0}
                      for row in qs.annotate(year=ExtractYear('observation_time')).values('year')
                      .annotate(records=Count('pk'), birds=Sum('count')).order_by('year')])
    return result


FIELDS = ('id', 'observation_time', 'count', 'status', 'species_id', 'species__name_cn',
          'species__name_latin', 'species__protection_level', 'zone_id', 'zone__name',
          'lng', 'lat', 'image', 'description', 'map_cache__transect_name')


def record(row):
    image = str(row['image'] or '')
    return {'id': row['id'], 'observation_time': row['observation_time'].isoformat(),
            'count': row['count'], 'status': row['status'], 'species': row['species_id'],
            'species_id': row['species_id'], 'species_name': row['species__name_cn'],
            'species_latin': row['species__name_latin'], 'species_protection': row['species__protection_level'],
            'zone': row['zone_id'], 'zone_name': row['zone__name'], 'transect_name': row['map_cache__transect_name'] or '',
            'lng': row['lng'], 'lat': row['lat'], 'longitude': row['lng'], 'latitude': row['lat'],
            'image': '/media/' + image.lstrip('/') if image else '', 'description': row['description'] or ''}


def page(qs, request, *, limit=PAGE_LIMIT):
    size = integer(request, 'page_size', limit, 1, limit)
    after = integer(request, 'after', 0, 0, 9223372036854775807)
    rows = list(qs.filter(pk__gt=after).order_by('pk').values(*FIELDS)[:size + 1])
    more = len(rows) > size
    rows = rows[:size]
    return {'results': [record(row) for row in rows], 'has_more': more, 'truncated': more,
            'next_after': rows[-1]['id'] if more else None, 'page_size': size}


def clusters(qs, bounds, zoom):
    # At regional scales retain every distinct observation coordinate. Repeated
    # records at the SAME coordinate share a symbol, without moving that site.
    # Only the far overview combines nearby sites in four-screen-pixel cells.
    # The grid must never grow with viewport width: that erased local detail.
    grid = 360 * 4 / (256 * 2 ** zoom) if zoom <= 7 else None
    cells = (dict(gx=Floor(F('lng') / grid), gy=Floor(F('lat') / grid))
             if grid else dict(gx=F('lng'), gy=F('lat')))
    rows = qs.annotate(**cells).values(
        'gx', 'gy', 'species__protection_level').annotate(
        lng_mean=Avg('lng'), lat_mean=Avg('lat'), records=Count('pk'), birds=Sum('count'), record_id=Min('pk'))
    grouped = {}
    for row in rows:
        level = get_protection_group(row['species__protection_level'])
        key = (row['gx'], row['gy'], level)
        item = grouped.setdefault(key, {'cluster_size': 0, 'count': 0, 'lng': 0, 'lat': 0,
                                       'species_protection': level, 'record_id': row['record_id'],
                                       'bounds': ([row['gx'] * grid, row['gy'] * grid,
                                                   (row['gx'] + 1) * grid, (row['gy'] + 1) * grid]
                                                  if grid else [row['gx'], row['gy'], row['gx'], row['gy']])})
        item['lng'] += row['lng_mean'] * row['records']
        item['lat'] += row['lat_mean'] * row['records']
        item['cluster_size'] += row['records']
        item['count'] += row['birds'] or 0
    for item in grouped.values():
        if grid:
            item['lng'] /= item['cluster_size']
            item['lat'] /= item['cluster_size']
        else:
            item['lng'], item['lat'] = item['bounds'][:2]
    return list(grouped.values())


@endpoint
def map_observations(request):
    base = observations(request)
    bounds = bbox(request)
    qs = within(base, bounds)
    zoom = number(request, 'zoom', 10, 0, 22)
    if request.GET.get('stage') == 'preview':
        # A bounded, cheap first paint. Never label this sample as a full total;
        # the following normal request supplies all locations and statistics.
        rows = list(qs.order_by('-observation_time', '-pk').values(*FIELDS)[:MAP_PREVIEW_LIMIT])
        return JsonResponse({'stage': 'preview', 'mode': 'points',
                             'results': [record(row) for row in rows], 'stats': None,
                             'clusters': [], 'recent': [], 'count': len(rows)},
                            json_dumps_params={'ensure_ascii': False})
    mode = 'points' if zoom >= 14 else 'clusters'
    payload = page(qs, request, limit=MAP_PAGE_LIMIT) if mode == 'points' else {
        'results': [], 'has_more': False, 'truncated': False, 'next_after': None, 'page_size': PAGE_LIMIT}
    payload.update(mode=mode, bbox=bounds, viewport=totals(qs), clusters=clusters(qs, bounds, zoom),
                   stats=statistics(base) if request.GET.get('stats', '1') != '0' else None,
                   recent=[record(row) for row in qs.order_by('-observation_time', '-pk').values(*FIELDS)[:20]])
    payload['count'] = len(payload['results'])
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@endpoint
def years(request):
    qs = observations(request, dates=False)
    return JsonResponse({'years': list(qs.annotate(year=ExtractYear('observation_time')).values_list(
        'year', flat=True).distinct().order_by('year'))})


@endpoint
def heatmap(request):
    bounds = bbox(request)
    qs = within(observations(request), bounds)
    return JsonResponse({'points': clusters(qs, bounds, 10), 'summary': totals(qs)})


def buffer_query(request):
    lng = number(request, 'lng', lower=-180, upper=180)
    lat = number(request, 'lat', lower=-90, upper=90)
    radius = number(request, 'radius', 500, 50, 10000)
    center = Point(lng, lat, srid=4326)
    # geography uses spheroidal metres, including at high latitudes.
    qs = observations(request)
    from django.contrib.gis.db.models import PointField as GISPointField
    from django.contrib.gis.measure import D
    qs = qs.annotate(geog=Cast('geom', GISPointField(srid=4326, geography=True)))
    qs = qs.filter(geog__dwithin=(center, D(m=radius)))
    return qs, lng, lat, radius


@endpoint
def buffer_analysis(request):
    qs, lng, lat, radius = buffer_query(request)
    payload = page(qs, request)
    summary = totals(qs)
    with connection.cursor() as cursor:
        cursor.execute('SELECT ST_AsGeoJSON(ST_Buffer(ST_SetSRID(ST_Point(%s,%s),4326)::geography,%s)::geometry)',
                       [lng, lat, radius])
        geometry = json.loads(cursor.fetchone()[0])
    routes = MonitoringRoute.objects.exclude(path_geom=None).annotate(valid=IsValid('path_geom'), empty=IsEmpty('path_geom')).filter(valid=True, empty=False)
    from django.contrib.gis.db.models import MultiLineStringField
    from django.contrib.gis.measure import D
    routes = routes.annotate(geog=Cast('path_geom', MultiLineStringField(srid=4326, geography=True))).filter(
        geog__dwithin=(Point(lng, lat, srid=4326), D(m=radius)))
    route_total = routes.count()
    features = [{'type': 'Feature', 'geometry': json.loads(r.path_geom.geojson),
                 'properties': {'id': r.pk, 'name': r.name}} for r in routes.order_by('pk')[:100]]
    summary['matched_routes'] = route_total
    payload.update(summary=summary, buffer={'type': 'Feature', 'geometry': geometry,
                   'properties': {'lng': lng, 'lat': lat, 'radius_m': radius}},
                   routes={'type': 'FeatureCollection', 'features': features},
                   routes_truncated=route_total > len(features),
                   scope={'start': request.GET.get('start') or request.GET.get('start_date', ''),
                          'end': request.GET.get('end') or request.GET.get('end_date', ''),
                          'protection': request.GET.get('protection') or request.GET.get('protection_filter', 'all'), 'approved_only': True})
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


def csv_cell(value):
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value if value is not None else '')
    # Spreadsheet software can treat whitespace/control-prefixed cells as
    # formulas too. csv.writer separately handles commas, quotes and newlines.
    if re.sub(r'^[\s\x00-\x1f\ufeff]*', '', text).startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        text = "'" + text
    return text


class _Echo:
    def write(self, text):
        return text


@endpoint
def buffer_csv(request):
    qs, lng, lat, radius = buffer_query(request)
    # Export ALL matching records, never the visible point page.  Iterate in
    # chunks so a broad buffer does not allocate the full dataset in memory.
    def stream():
        writer = csv.writer(_Echo())
        yield '\ufeff'
        yield writer.writerow(['记录编号', '物种中文名', '物种拉丁名', '保护等级', '监测点位', '观测日期', '鸟类数量（只）',
                               '经度', '纬度', '描述', '导出范围', '中心经度', '中心纬度', '半径（米）', '开始日期', '结束日期', '保护等级筛选'])
        scope = ['缓冲范围内全部已审核且符合筛选的记录', lng, lat, radius,
                 request.GET.get('start') or request.GET.get('start_date', ''),
                 request.GET.get('end') or request.GET.get('end_date', ''),
                 request.GET.get('protection') or request.GET.get('protection_filter', 'all')]
        if scope[-1] == 'all':
            scope[-1] = '全部'
        for row in qs.order_by('pk').values(*FIELDS).iterator(chunk_size=1000):
            values = [row['id'], row['species__name_cn'], row['species__name_latin'],
                      get_protection_group(row['species__protection_level']), row['zone__name'],
                      row['observation_time'], row['count'], row['lng'], row['lat'], row['description'], *scope]
            yield writer.writerow([csv_cell(value) for value in values])
    response = StreamingHttpResponse(stream(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="monitoring-buffer-all-records.csv"'
    return response


@endpoint
def detail(request, record_id):
    qs = observations(request)
    row = qs.filter(pk=record_id).values(*FIELDS).first()
    if not row:
        return JsonResponse({'detail': '记录不存在或不在当前已审核筛选范围内'}, status=404)
    # Full detail charts use complete filtered data, not the paginated viewport.
    zones = list(qs.filter(species_id=row['species_id']).values('zone__name').annotate(records=Count('pk')).order_by('zone__name'))
    return JsonResponse({'result': record(row), 'stats': statistics(qs), 'species_zones': zones})
