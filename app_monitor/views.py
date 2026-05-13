from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.db import connection
from django.conf import settings
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from datetime import timedelta
from django.db.models import Sum, Q, Count  # 引入 Q 用于复杂查询
from pathlib import Path
from django.utils.dateparse import parse_date
from django.db.models.functions import ExtractYear
from urllib.parse import quote
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
import json
import os
import re

# DRF 相关引用
from rest_framework import viewsets, permissions, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

# GIS 相关引用
try:
    from django.contrib.gis.geos import Point
    from django.contrib.gis.measure import D
except ImportError:
    Point = None
    D = None

# === 引入模型 ===
# 确保包含 Product, UserProfile
from .models import MapObservationCache, ObservationRecord, WetlandZone, MonitoringRoute, Product, UserProfile, SpeciesInfo, SpeciesImage
from .protection import normalize_protection_level, get_protection_group
from django.contrib.auth.models import User

# === 引入序列化器 ===
from .serializers import (
    ObservationRecordSerializer,
    WetlandZoneSerializer,
    MonitoringRouteSerializer,
    ProductSerializer,
    UserInfoSerializer,
    UserRegisterSerializer,
    SpeciesInfoSerializer,
    SpeciesImageSerializer,
)


# ==========================================
# 0. 用户注册视图 /api/auth/register/
# ==========================================
class RegisterViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['post'])
    def register(self, request):
        serializer = UserRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, _ = Token.objects.get_or_create(user=user)
            return Response({
                'user': UserInfoSerializer(user, context={'request': request}).data,
                'token': token.key,
                'message': '注册成功'
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==========================================
# 1. 监测点位视图 /api/zones/
# ==========================================
class ZoneViewSet(viewsets.ModelViewSet):
    queryset = WetlandZone.objects.all()
    serializer_class = WetlandZoneSerializer


# ==========================================
# 1b. 物种百科视图 /api/species/
# ==========================================
class SpeciesViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SpeciesInfo.objects.all().order_by('name_cn')
    serializer_class = SpeciesInfoSerializer
    permission_classes = [permissions.AllowAny]


# ==========================================
# 2. 监测样线视图 /api/transects/
# ==========================================
class TransectViewSet(viewsets.ModelViewSet):
    queryset = MonitoringRoute.objects.all()
    serializer_class = MonitoringRouteSerializer


# ==========================================
# 3. 观测记录视图 /api/observations/ (核心)
# ==========================================
class ObservationViewSet(viewsets.ModelViewSet):
    """
    核心业务视图：
    1. 游客：只能看已通过(approved)的数据
    2. 登录用户：能看已通过 + 自己上传(pending/rejected)的数据
    3. 管理员：能看所有数据
    4. 上传：自动关联用户，自动加分
    """
    serializer_class = ObservationRecordSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]  # 游客只读，登录可写

    def get_queryset(self):
        # 默认按时间倒序
        queryset = ObservationRecord.objects.all().order_by('-observation_time')

        user = self.request.user

        # A. 管理员/巡护员: 看所有
        if user.is_staff:
            return queryset

        # B. 登录的普通用户: 看 '已通过' | '我自己上传的'
        if user.is_authenticated:
            return queryset.filter(
                Q(status='approved') | Q(uploader=user)
            )

        # C. 游客: 只看 '已通过'
        return queryset.filter(status='approved')

    def perform_create(self, serializer):
        """
        当用户 POST 上传数据时执行
        """
        # 1. 自动关联当前登录用户
        serializer.save(uploader=self.request.user)

        # 2. 积分奖励逻辑 (上传一条 +10分)
        try:
            # 获取或创建用户的积分档案
            profile, created = UserProfile.objects.get_or_create(user=self.request.user)
            profile.score += 10
            profile.save()
            print(f"用户 {self.request.user.username} 上传成功，积分+10，当前: {profile.score}")
        except Exception as e:
            print(f"加分失败: {e}")

    # === GIS 功能: 附近预警 ===
    @action(detail=False, methods=['get'])
    def nearby_alert(self, request):
        if not Point:
            return Response({'error': 'GIS libraries not installed'}, status=501)
        try:
            lat = float(request.query_params.get('lat'))
            lng = float(request.query_params.get('lng'))
            p = Point(lng, lat, srid=4326)

            # 这里的查询也应该只返回已通过的，避免用户看到脏数据
            birds = ObservationRecord.objects.filter(
                location__dwithin=(p, D(m=500)),
                status='approved'
            )
            serializer = self.get_serializer(birds, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    # === GIS 功能: MVT 矢量瓦片 ===
    @action(detail=False, methods=['get'], url_path=r'tiles/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)')
    def tiles(self, request, z, x, y):
        # SQL 查询：只返回 status='approved' 的点位
        sql = """
              WITH mvtgeom AS (SELECT ST_AsMVTGeom(location, ST_TileEnvelope(%s, %s, %s), 4096, 256, true) AS geom,
                                      id, \
                                      status
                               FROM app_monitor_observationrecord
                               WHERE ST_Intersects(location, ST_TileEnvelope(%s, %s, %s))
                                 AND status = 'approved')
              SELECT ST_AsMVT(mvtgeom.*, 'layer_birds') \
              FROM mvtgeom;
              """
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, [z, x, y, z, x, y])
                row = cursor.fetchone()
                tile = row[0] if row else b''
            return HttpResponse(tile if tile else b'', content_type="application/vnd.mapbox-vector-tile")
        except Exception as e:
            return HttpResponse(status=500)


# ==========================================
# 4. 商品/积分商城视图 /api/products/
# ==========================================
def _get_float_param(request, key):
    value = request.GET.get(key)
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_bbox_params(request):
    bbox = request.GET.get('bbox')
    if bbox:
        try:
            west, south, east, north = [float(part) for part in bbox.split(',')[:4]]
            return west, south, east, north
        except (TypeError, ValueError):
            return None

    west = _get_float_param(request, 'west')
    south = _get_float_param(request, 'south')
    east = _get_float_param(request, 'east')
    north = _get_float_param(request, 'north')
    if None in (west, south, east, north):
        return None
    return west, south, east, north


def _filter_cache_by_protection(queryset, protection_filter):
    if not protection_filter or protection_filter == 'all':
        return queryset

    matched_levels = []
    for level in queryset.values_list('species_protection', flat=True).distinct():
        if get_protection_group(level) == protection_filter:
            matched_levels.append(level)

    if not matched_levels:
        return queryset.none()
    return queryset.filter(species_protection__in=matched_levels)


def _cache_row_to_dict(row):
    lng = row['longitude']
    lat = row['latitude']
    return {
        'id': row['record_id'],
        'observation_time': row['observation_time'].isoformat() if row['observation_time'] else None,
        'count': row['count'],
        'status': row['status'],
        'species': row['species_id_cached'],
        'species_id': row['species_id_cached'],
        'species_name': row['species_name'],
        'species_latin': row['species_latin'],
        'species_protection': row['species_protection'],
        'zone': row['zone_id_cached'],
        'zone_id': row['zone_id_cached'],
        'zone_name': row['zone_name'],
        'transect_name': row['transect_name'],
        'x': lng,
        'y': lat,
        'lng': lng,
        'lat': lat,
        'longitude': lng,
        'latitude': lat,
        'image': row['image_url'],
        'description': row['description'],
    }


def _map_cache_stats(queryset):
    total_records = queryset.count()
    species_count = queryset.values('species_id_cached').distinct().count()
    approved_count = total_records

    protected_levels = []
    level_distribution = {
        '国家一级': {'level': '国家一级', 'count': 0, 'records': 0},
        '国家二级': {'level': '国家二级', 'count': 0, 'records': 0},
        '三有动物': {'level': '三有动物', 'count': 0, 'records': 0},
        '无危/其他': {'level': '无危/其他', 'count': 0, 'records': 0},
    }
    for item in queryset.values('species_protection').annotate(total=Sum('count'), records=Count('record_id')):
        group = get_protection_group(item['species_protection'])
        if group not in level_distribution:
            group = '无危/其他'
        level_distribution[group]['count'] += item['total'] or 0
        level_distribution[group]['records'] += item['records'] or 0
        if group in ('国家一级', '国家二级'):
            protected_levels.append(item['species_protection'])

    protected_count = queryset.filter(species_protection__in=protected_levels).count() if protected_levels else 0
    top_species = [
        {
            'name': row['species_name'] or '未知物种',
            'latin': row['species_latin'] or '',
            'level': get_protection_group(row['species_protection']),
            'count': row['total'] or 0,
            'records': row['records'],
        }
        for row in queryset.values('species_id_cached', 'species_name', 'species_latin', 'species_protection')
        .annotate(total=Sum('count'), records=Count('record_id'))
        .order_by('-total')[:10]
    ]
    yearly_trend = [
        {'year': row['year'], 'count': row['records'], 'bird_count': row['total'] or 0}
        for row in queryset.annotate(year=ExtractYear('observation_time'))
        .values('year')
        .annotate(records=Count('record_id'), total=Sum('count'))
        .order_by('year')
    ]

    return {
        'total_records': total_records,
        'species_count': species_count,
        'protected_count': protected_count,
        'approved_count': approved_count,
        'top_species': top_species,
        'protection_distribution': list(level_distribution.values()),
        'yearly_trend': yearly_trend,
    }


@require_GET
def map_observations(request):
    base_queryset = MapObservationCache.objects.filter(status='approved')

    start_date = parse_date(request.GET.get('start') or request.GET.get('start_date') or '')
    end_date = parse_date(request.GET.get('end') or request.GET.get('end_date') or '')
    if start_date:
        base_queryset = base_queryset.filter(observation_time__gte=start_date)
    if end_date:
        base_queryset = base_queryset.filter(observation_time__lte=end_date)

    protection_filter = request.GET.get('protection') or request.GET.get('protection_filter') or 'all'
    base_queryset = _filter_cache_by_protection(base_queryset, protection_filter)

    include_stats = request.GET.get('stats', '1') != '0'
    stats = _map_cache_stats(base_queryset) if include_stats else None

    viewport_queryset = base_queryset
    bbox = _get_bbox_params(request)
    if bbox:
        west, south, east, north = bbox
        viewport_queryset = viewport_queryset.filter(
            longitude__gte=min(west, east),
            longitude__lte=max(west, east),
            latitude__gte=min(south, north),
            latitude__lte=max(south, north),
        )

    rows = (
        viewport_queryset
        .order_by('-observation_time', '-record_id')
        .values(
            'record_id',
            'observation_time',
            'count',
            'status',
            'species_id_cached',
            'species_name',
            'species_latin',
            'species_protection',
            'zone_id_cached',
            'zone_name',
            'transect_name',
            'longitude',
            'latitude',
            'image_url',
            'description',
        )
    )

    data = [_cache_row_to_dict(row) for row in rows.iterator(chunk_size=5000)]
    return JsonResponse({
        'results': data,
        'stats': stats,
        'bbox': bbox,
        'count': len(data),
    }, json_dumps_params={'ensure_ascii': False})


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    # POST /api/products/{id}/redeem/
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def redeem(self, request, pk=None):
        product = self.get_object()
        user = request.user

        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            return Response({"error": "用户档案不存在"}, status=400)

        # 1. 校验库存
        if product.stock <= 0:
            return Response({"error": "商品库存不足"}, status=400)

        # 2. 校验积分
        if profile.score < product.price:
            return Response({"error": f"积分不足，还需要 {product.price - profile.score} 分"}, status=400)

        # 3. 执行交易
        profile.score -= product.price
        profile.save()

        product.stock -= 1
        product.save()

        return Response({
            "message": f"成功兑换: {product.name}",
            "remaining_score": profile.score
        })


# ==========================================
# 4b. 科普文章与图库 API
# ==========================================
_SPECIES_IMG_CACHE = None


def _normalize_species_key(value):
    return re.sub(r"[（）()\[\]【】\s·,，、/\\-]", "", (value or "").strip().lower().replace("黒", "黑"))


def _lookup_species_image(image_map, name_cn):
    if not name_cn:
        return None
    if name_cn in image_map:
        return image_map[name_cn]

    normalized = _normalize_species_key(name_cn)
    for key, url in image_map.items():
        if _normalize_species_key(key) == normalized:
            return url
    return None


def _load_species_image_map():
    """
    复用前端物种百科和图库中的 Wikimedia Commons 直链映射。
    这样图库页、物种百科和科普文章会保持同一套图片来源。
    """
    global _SPECIES_IMG_CACHE
    if _SPECIES_IMG_CACHE is not None:
        return _SPECIES_IMG_CACHE

    image_map = {}
    template_dir = Path(settings.BASE_DIR) / 'app_monitor' / 'templates'
    for template_name in ('species.html', 'species-gallery.html'):
        template_path = template_dir / template_name
        try:
            text = template_path.read_text(encoding='utf-8')
        except OSError:
            continue

        for const_name in ('SPECIES_IMG', 'FALLBACK_IMAGES'):
            pattern = rf"const\s+{const_name}\s*=\s*\{{(.*?)^\s*\}};"
            for match in re.finditer(pattern, text, re.S | re.M):
                image_map.update(re.findall(r"'([^']+)'\s*:\s*'([^']+)'", match.group(1)))

    stonechat_url = "https://commons.wikimedia.org/wiki/Special:FilePath/Stejneger%27s_Stonechat.jpg"
    image_map.setdefault('东亚石䳭', stonechat_url)
    image_map.setdefault('黑喉石䳭（东亚）', stonechat_url)
    image_map.setdefault('黑喉石䳭(东亚)', stonechat_url)

    _SPECIES_IMG_CACHE = image_map
    return image_map


def _commons_search_url(name_cn, latin=''):
    keyword = f"{latin.replace(' ', '_')} bird" if latin else f"{name_cn} bird"
    return f"https://commons.wikimedia.org/w/index.php?search={quote(keyword)}&title=Special:Search&go=Go"


def _wikipedia_search_url(name_cn, latin=''):
    keyword = latin or name_cn
    return f"https://zh.wikipedia.org/wiki/Special:Search?search={quote(keyword)}"


def _paragraphs(text):
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    if not lines:
        return '<p>暂无详细资料，建议结合物种百科与观鸟记录继续补充。</p>'
    return ''.join(f'<p>{escape(line)}</p>' for line in lines)


def _species_observation_count(species):
    return ObservationRecord.objects.filter(species=species, status='approved').count()


def _fixed_articles(request):
    now = timezone.now()
    data = [
        {
            'id': 1,
            'title': '郑州黄河湿地：中部地区重要的候鸟迁徙通道',
            'category': 'habitat',
            'summary': '郑州黄河湿地位于东亚-澳大利西亚候鸟迁飞路线的重要节点，每年春秋两季都有大量候鸟停歇、觅食和补充能量。',
            'content': '<p>郑州黄河湿地处在黄河中下游交接地带，河道、滩涂、库塘和芦苇沼泽共同形成了复杂的湿地生境。</p><h3>迁徙通道价值</h3><p>迁徙鸟类需要稳定的中途停歇地来恢复体力。开阔水面、浅滩和湿地植被能为雁鸭类、鹭类、鹬鸻类等提供食物与隐蔽条件。</p><h3>保护重点</h3><p>减少人为干扰、保持水位稳定、修复退化滩涂，是提升候鸟停歇质量的关键。</p>',
            'cover_image': 'https://upload.wikimedia.org/wikipedia/commons/3/3d/D%C3%BClmen%2C_Rorup%2C_NSG_Roruper_Holz_--_2021_--_8187-91.jpg',
        },
        {
            'id': 2,
            'title': '观鸟入门：如何在湿地识别常见水鸟',
            'category': 'knowledge',
            'summary': '从体型、嘴形、腿长、飞行姿态和取食行为入手，可以快速区分湿地里常见的雁鸭类、鹭类与鹬鸻类。',
            'content': '<p>观鸟时先用肉眼锁定鸟群，再举起望远镜观察细节。湿地鸟类的识别通常可以从外形比例和行为模式入手。</p><h3>几个实用线索</h3><p>雁鸭类多在水面游弋，鹭类常有长腿长颈并在浅水中伏击猎物，鹬鸻类多在滩涂快速奔走取食。</p><h3>记录建议</h3><p>提交记录时写清地点、日期、数量和行为，最好附照片作为凭证。</p>',
            'cover_image': 'https://upload.wikimedia.org/wikipedia/commons/9/9f/Wildlife-photography-in-kerala.jpg',
        },
        {
            'id': 3,
            'title': '湿地的生态服务功能：地球之肾的价值',
            'category': 'habitat',
            'summary': '湿地能调蓄洪水、净化水质、储存碳并维系生物多样性，是城市与河流之间重要的生态缓冲带。',
            'content': '<p>湿地兼具水域和陆地特征，是生产力很高的生态系统。它们像天然海绵一样吸纳、过滤并缓慢释放水分。</p><h3>水质净化</h3><p>湿地植物、微生物和土壤共同作用，可以截留悬浮物并吸收氮、磷等营养盐。</p><h3>生物多样性</h3><p>鸟类、鱼类、两栖类和昆虫共同构成湿地食物网，湿地质量直接影响这些类群的稳定。</p>',
            'cover_image': 'https://upload.wikimedia.org/wikipedia/commons/d/da/Leaf_Litter_-_Guelph%2C_Ontario.jpg',
        },
        {
            'id': 4,
            'title': '保护湿地鸟类的五个日常行动',
            'category': 'news',
            'summary': '保护鸟类不只发生在保护区，也可以从减少干扰、科学记录、垃圾减量和传播保护理念开始。',
            'content': '<p>湿地鸟类面临栖息地退化、污染和人为干扰等压力。公众参与能让保护行动获得更稳定的数据和社会支持。</p><h3>行动建议</h3><p>观鸟时保持距离，不追逐、不投喂；减少一次性塑料；参与湿地清洁和鸟类调查；把规范记录上传到平台，帮助研究者了解种群变化。</p>',
            'cover_image': 'https://upload.wikimedia.org/wikipedia/commons/8/82/LEKKI_CONSERVATION_CENTRE.jpg',
        },
    ]
    for index, item in enumerate(data):
        item.update({
            'author_name': '黄河生态方舟',
            'views': 320 + index * 47,
            'is_published': True,
            'created_at': (now - timedelta(days=index + 1)).isoformat(),
            'updated_at': (now - timedelta(days=index)).isoformat(),
        })
    return data


def _species_articles(request):
    image_map = _load_species_image_map()
    now = timezone.now()
    articles = []
    for index, species in enumerate(SpeciesInfo.objects.all().order_by('name_cn')):
        name = species.name_cn or '未知物种'
        latin = species.name_latin or ''
        order = species.order or '未记录'
        family = species.family or '未记录'
        protection = normalize_protection_level(species.protection_level) or '暂无保护级别'
        distribution = species.distribution_habit or ''
        wiki_url = _wikipedia_search_url(name, latin)
        commons_url = _commons_search_url(name, latin)
        count = _species_observation_count(species)
        species_cover = _lookup_species_image(image_map, name)
        if not species_cover:
            species_cover = SpeciesInfoSerializer(species, context={'request': request}).data.get('cover_image_url')

        content = (
            f'<p><strong>{escape(name)}</strong>{f"（{escape(latin)}）" if latin else ""}'
            '是本平台物种百科收录的湿地鸟类。</p>'
            '<h3>分类信息</h3>'
            f'<p>分类位置：{escape(order)} / {escape(family)}。保护级别：{escape(protection)}。</p>'
            '<h3>本地分布与习性</h3>'
            f'{_paragraphs(distribution)}'
            '<h3>平台观测情况</h3>'
            f'<p>当前平台已通过审核的相关观鸟记录为 {count} 条，可结合首页地图查看空间分布。</p>'
            '<h3>外部资料</h3>'
            f'<p>更多开放资料可参考 <a href="{wiki_url}" target="_blank" rel="noopener">维基百科检索</a> '
            f'和 <a href="{commons_url}" target="_blank" rel="noopener">Wikimedia Commons 图库</a>。</p>'
        )
        summary_source = distribution.strip() or f'{name} 的分类、保护级别、湿地分布和观测记录概览。'
        articles.append({
            'id': 100000 + species.id,
            'title': f'{name}：黄河湿地鸟类科普',
            'category': 'species',
            'summary': summary_source[:120],
            'content': content,
            'cover_image': species_cover,
            'author_name': '维基百科 / 黄河生态方舟',
            'views': max(18, count * 9 + 80 - index),
            'is_published': True,
            'created_at': (now - timedelta(days=8 + index)).isoformat(),
            'updated_at': now.isoformat(),
        })
    return articles


def _article_items(request):
    return _fixed_articles(request) + _species_articles(request)


def _species_image_items(request):
    image_map = _load_species_image_map()
    items = []
    for index, species in enumerate(SpeciesInfo.objects.all().order_by('name_cn')):
        name = species.name_cn or '未知物种'
        image_url = _lookup_species_image(image_map, name)
        if not image_url:
            continue
        latin = species.name_latin or ''
        count = _species_observation_count(species)
        items.append({
            'id': species.id,
            'species': species.id,
            'species_id': species.id,
            'species_name': name,
            'species_latin': latin,
            'url': image_url,
            'full_url': image_url,
            'thumbnail_url': image_url,
            'caption': f'{name}{f"（{latin}）" if latin else ""}的 Wikimedia Commons 开放影像',
            'source': 'wikimedia',
            'source_url': _commons_search_url(name, latin),
            'source_author': 'Wikimedia Commons',
            'views': max(0, count * 6 + 40 - index),
            'is_featured': index < 12 or count > 0,
        })
    return items


class ArticleViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        return Response(_article_items(request))

    def retrieve(self, request, pk=None):
        for article in _article_items(request):
            if str(article['id']) == str(pk):
                return Response(article)
        return Response({"detail": "未找到文章数据"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def view(self, request, pk=None):
        for article in _article_items(request):
            if str(article['id']) == str(pk):
                return Response({'views': article.get('views', 0) + 1})
        return Response({'views': 1})


class SpeciesImageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SpeciesImage.objects.all().order_by('-is_featured', '-views', '-created_at')
    serializer_class = SpeciesImageSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        species_id = self.request.query_params.get('species_id')
        if species_id:
            queryset = queryset.filter(species_id=species_id)
        return queryset

    @action(detail=True, methods=['post'], url_path='set-featured')
    def set_featured(self, request, pk=None):
        image = self.get_object()
        species_id = request.data.get('species_id') or image.species_id
        SpeciesImage.objects.filter(species_id=species_id).exclude(pk=image.pk).update(is_featured=False)
        image.is_featured = True
        image.save(update_fields=['is_featured'])
        species = SpeciesInfo.objects.get(pk=species_id)
        cover_url = SpeciesInfoSerializer(species, context={'request': request}).data.get('cover_image_url')
        return Response({
            'success': True,
            'image_id': image.pk,
            'species_id': species_id,
            'cover_image_url': cover_url,
            'message': '精选封面已更新'
        })

    def retrieve(self, request, pk=None):
        for image in _species_image_items(request):
            if str(image['id']) == str(pk):
                return Response(image)
        return Response({"detail": "未找到图片数据"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def view_image(self, request, pk=None):
        image = self.get_object()
        image.views += 1
        image.save(update_fields=['views'])
        return Response({'views': image.views})


# ==========================================
# 5. 用户档案视图 /api/profiles/
# ==========================================
class UserProfileUpdateScoreSerializer(serializers.Serializer):
    score = serializers.IntegerField(required=True)


class UserProfileViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserInfoSerializer
    permission_classes = [permissions.IsAuthenticated]

    # GET /api/profiles/me/  <-- 前端获取自己信息的接口
    @action(detail=False, methods=['get', 'patch'])
    def me(self, request):
        if request.method == 'PATCH':
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            score = request.data.get('score')
            if score is not None:
                try:
                    profile.score = int(score)
                    profile.save(update_fields=['score'])
                except (TypeError, ValueError):
                    return Response({'score': ['请输入有效积分']}, status=400)
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    # PATCH /api/profiles/me/score/
    @action(detail=False, methods=['patch'], permission_classes=[permissions.IsAuthenticated])
    def score(self, request):
        serializer = UserProfileUpdateScoreSerializer(data=request.data)
        if serializer.is_valid():
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            profile.score = serializer.validated_data['score']
            profile.save(update_fields=['score'])
            return Response({'score': profile.score})
        return Response(serializer.errors, status=400)

    # PUT/PATCH /api/profiles/update_profile/
    @action(detail=False, methods=['put', 'patch'], permission_classes=[permissions.IsAuthenticated])
    def update_profile(self, request):
        email = request.data.get('email')
        if email is not None:
            request.user.email = email
            request.user.save(update_fields=['email'])
        return Response(UserInfoSerializer(request.user, context={'request': request}).data)

    # POST /api/profiles/me/avatar/
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='me/avatar')
    def upload_avatar(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        avatar = request.FILES.get('avatar')
        if not avatar:
            return Response({'avatar': ['请选择头像文件']}, status=400)
        profile.avatar = avatar
        profile.save(update_fields=['avatar'])
        return Response({
            'avatar': request.build_absolute_uri(profile.avatar.url) if profile.avatar else None,
            'message': '头像上传成功'
        })


# ==========================================
# 6. DeepSeek 网页智能体接口 /api/ai/chat/
# ==========================================
AI_SYSTEM_PROMPT = (
    "你是“黄河生态方舟”平台的生态监测智能助手。"
    "你必须基于平台提供的数据库摘要和当前网页上下文回答问题。"
    "如果数据不足，请明确说明“当前平台数据不足以判断”，不要编造不存在的数据。"
    "回答面向普通用户，语言清晰、简洁、专业。"
    "涉及生态治理建议时，只提供辅助性建议，不替代专家结论。"
)


def _safe_sum(value):
    return int(value or 0)


def _clean_ai_text(value, max_length=1200):
    text = str(value or '').strip()
    text = re.sub(r'\s+', ' ', text)
    return text[:max_length]


def _limited_context_dict(value, max_items=20):
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= max_items:
            break
        if isinstance(item, (dict, list, tuple)):
            cleaned[str(key)[:40]] = item
        else:
            cleaned[str(key)[:40]] = _clean_ai_text(item, 300)
    return cleaned


def _date_from_context(page_context, key):
    raw = (page_context or {}).get(key)
    if not raw:
        return None
    try:
        return timezone.datetime.fromisoformat(str(raw).replace('/', '-')).date()
    except ValueError:
        return None


def _detect_zone_from_message(message):
    message = message or ''
    if not message:
        return None
    zones = WetlandZone.objects.only('id', 'name').order_by('-name')
    for zone in zones:
        name = zone.name or ''
        if name and name in message:
            return zone
    return None


def _detect_species_from_message(message):
    message = message or ''
    if not message:
        return None
    species_qs = SpeciesInfo.objects.only(
        'id', 'name_cn', 'name_latin', 'order', 'family', 'protection_level', 'distribution_habit'
    ).order_by('-name_cn')
    for species in species_qs:
        name_cn = species.name_cn or ''
        latin = species.name_latin or ''
        if (name_cn and name_cn in message) or (latin and latin.lower() in message.lower()):
            return species
    return None


def _top_species_rows(queryset, limit=10):
    rows = queryset.values(
        'species__name_cn',
        'species__name_latin',
        'species__protection_level',
    ).annotate(
        total=Sum('count'),
        records=Count('id'),
    ).order_by('-total')[:limit]
    return [
        {
            'name': row['species__name_cn'] or '未知物种',
            'latin': row['species__name_latin'] or '',
            'protection_level': normalize_protection_level(row['species__protection_level']) or '未标注',
            'count': _safe_sum(row['total']),
            'records': row['records'],
        }
        for row in rows
    ]


def _top_zone_rows(queryset, limit=10):
    rows = queryset.values('zone__name').annotate(
        total=Sum('count'),
        records=Count('id'),
    ).order_by('-total')[:limit]
    return [
        {
            'zone': row['zone__name'] or '未知区域',
            'count': _safe_sum(row['total']),
            'records': row['records'],
        }
        for row in rows
    ]


def _protection_rows(queryset):
    rows = queryset.values('species__protection_level').annotate(
        total=Sum('count'),
        records=Count('id'),
    ).order_by('-total')
    buckets = {}
    for row in rows:
        level = normalize_protection_level(row['species__protection_level']) or '无保护/未标注'
        if level not in buckets:
            buckets[level] = {'level': level, 'count': 0, 'records': 0}
        buckets[level]['count'] += _safe_sum(row['total'])
        buckets[level]['records'] += row['records']
    return sorted(buckets.values(), key=lambda item: item['count'], reverse=True)[:8]


def _build_ai_data_context(message, page_context):
    page_context = _limited_context_dict(page_context)
    queryset = ObservationRecord.objects.filter(status='approved').select_related('species', 'zone')

    start_date = _date_from_context(page_context, 'start_date')
    end_date = _date_from_context(page_context, 'end_date')
    if start_date:
        queryset = queryset.filter(observation_time__gte=start_date)
    if end_date:
        queryset = queryset.filter(observation_time__lte=end_date)

    detected_zone = _detect_zone_from_message(message)
    detected_species = _detect_species_from_message(message)

    if detected_zone:
        queryset = queryset.filter(zone=detected_zone)
    if detected_species:
        queryset = queryset.filter(species=detected_species)

    total_records = queryset.count()
    total_birds = _safe_sum(queryset.aggregate(total=Sum('count'))['total'])
    species_count = queryset.values('species').distinct().count()
    zone_count = queryset.values('zone').distinct().count()

    species_detail = None
    if detected_species:
        species_detail = {
            'name_cn': detected_species.name_cn,
            'name_latin': detected_species.name_latin,
            'order': detected_species.order,
            'family': detected_species.family,
            'protection_level': normalize_protection_level(detected_species.protection_level) or '未标注',
            'distribution_habit': _clean_ai_text(detected_species.distribution_habit, 500),
        }

    return {
        'question': _clean_ai_text(message, 500),
        'page_context': page_context,
        'filters': {
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'zone': detected_zone.name if detected_zone else None,
            'species': detected_species.name_cn if detected_species else None,
        },
        'summary': {
            'record_count': total_records,
            'bird_count': total_birds,
            'species_count': species_count,
            'zone_count': zone_count,
        },
        'top_species': _top_species_rows(queryset),
        'top_zones': _top_zone_rows(queryset),
        'protection_distribution': _protection_rows(queryset),
        'species_detail': species_detail,
    }


def _local_ai_answer(data_context):
    summary = data_context.get('summary', {})
    top_species = data_context.get('top_species') or []
    top_zones = data_context.get('top_zones') or []
    filters = data_context.get('filters', {})

    scope = []
    if filters.get('zone'):
        scope.append(filters['zone'])
    if filters.get('species'):
        scope.append(filters['species'])
    if filters.get('start_date') or filters.get('end_date'):
        scope.append(f"{filters.get('start_date') or '起始'} 至 {filters.get('end_date') or '当前'}")
    scope_text = '、'.join(scope) if scope else '当前平台筛选范围'

    lines = [
        f"基于平台数据库，{scope_text}内共有 {summary.get('record_count', 0)} 条观测记录，累计记录鸟类数量 {summary.get('bird_count', 0)} 只，涉及 {summary.get('species_count', 0)} 个物种、{summary.get('zone_count', 0)} 个区域。",
    ]
    if top_species:
        lines.append("数量较高的物种包括：" + "、".join(f"{item['name']}（{item['count']}只）" for item in top_species[:5]) + "。")
    if top_zones:
        lines.append("记录较集中的区域包括：" + "、".join(f"{item['zone']}（{item['count']}只）" for item in top_zones[:5]) + "。")
    lines.append("当前为本地数据摘要回答；配置 DeepSeek API 后可生成更自然的生态解释和研判建议。")
    return "\n".join(lines)


def _load_deepseek_local_env():
    local_env = {}
    env_file = Path(settings.BASE_DIR) / '.env.local'
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip().lstrip('\ufeff')
                local_env[key] = value.strip().strip('"').strip("'")
        except OSError:
            local_env = {}
    return local_env


def _get_deepseek_model(local_env=None):
    local_env = local_env or _load_deepseek_local_env()
    return (
        os.environ.get('DEEPSEEK_MODEL')
        or local_env.get('DEEPSEEK_MODEL')
        or getattr(settings, 'DEEPSEEK_MODEL', 'deepseek-v4-flash')
    )


def _call_deepseek(message, data_context):
    local_env = _load_deepseek_local_env()

    api_key = (
        os.environ.get('DEEPSEEK_API_KEY')
        or local_env.get('DEEPSEEK_API_KEY')
        or getattr(settings, 'DEEPSEEK_API_KEY', '')
    )
    if not api_key:
        return None, 'DEEPSEEK_API_KEY 未配置'

    base_url = (
        os.environ.get('DEEPSEEK_BASE_URL')
        or local_env.get('DEEPSEEK_BASE_URL')
        or getattr(settings, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    )
    model = _get_deepseek_model(local_env)
    endpoint = base_url.rstrip('/')
    if not endpoint.endswith('/chat/completions'):
        endpoint = f'{endpoint}/chat/completions'

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': AI_SYSTEM_PROMPT},
            {
                'role': 'user',
                'content': (
                    f"用户问题：{message}\n\n"
                    f"平台真实数据摘要：\n{json.dumps(data_context, ensure_ascii=False, indent=2)}\n\n"
                    "请基于以上数据回答，避免编造。回答控制在 400 字以内。"
                )
            },
        ],
        'temperature': 0.3,
        'max_tokens': 900,
    }
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urlrequest.Request(
        endpoint,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST',
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        return None, f'DeepSeek HTTP {exc.code}'
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, f'DeepSeek 调用失败：{exc}'

    try:
        return result['choices'][0]['message']['content'].strip(), None
    except (KeyError, IndexError, TypeError):
        return None, 'DeepSeek 返回格式异常'


@csrf_exempt
def ai_chat(request):
    if request.method != 'POST':
        return JsonResponse({'detail': 'Only POST is allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'detail': '请求体不是有效 JSON'}, status=400)

    message = _clean_ai_text(payload.get('message'), 800)
    page_context = payload.get('page_context') or {}
    if not message:
        return JsonResponse({'detail': '请输入问题'}, status=400)

    data_context = _build_ai_data_context(message, page_context)
    answer, error = _call_deepseek(message, data_context)
    model = _get_deepseek_model()
    if not answer:
        answer = _local_ai_answer(data_context)
        model = 'local-data-summary'

    return JsonResponse({
        'answer': answer,
        'model': model,
        'deepseek_error': error,
        'data_used': data_context,
    }, json_dumps_params={'ensure_ascii': False})


# ==========================================
# 7. 普通页面视图 (热点推荐)
# ==========================================
def index_view(request):
    return render(request, 'index.html')


def get_todays_hotspot(request):
    three_days_ago = timezone.now().date() - timedelta(days=3)

    # 只统计 '已通过' (approved) 的记录
    hot_zone_data = ObservationRecord.objects.filter(
        observation_time__gte=three_days_ago,
        status='approved'
    ).values('zone').annotate(total_count=Sum('count')).order_by('-total_count').first()

    recommendation_data = {}

    if hot_zone_data and hot_zone_data['zone']:
        try:
            zone = WetlandZone.objects.get(id=hot_zone_data['zone'])
            # 获取最新且已通过的记录
            latest_record = ObservationRecord.objects.filter(
                zone=zone,
                status='approved'
            ).order_by('-observation_time').first()

            bird_name = "珍稀鸟类"
            if latest_record and latest_record.species:
                bird_name = latest_record.species.name_cn

            tips = getattr(zone, 'observation_tips', "请保持安全距离观赏")

            recommendation_data = {
                "title": f"今日推荐：{zone.name}，近期有{bird_name}集群活动",
                "tips": f"观鸟注意事项：{tips}",
                "location": zone.name
            }
        except WetlandZone.DoesNotExist:
            recommendation_data = _default_hotspot()
    else:
        recommendation_data = _default_hotspot()

    return render(request, 'app_monitor/hotspot.html', {'recommendation': recommendation_data})


def _default_hotspot():
    return {
        "title": "今日推荐：郑州黄河湿地中段",
        "tips": "保持100米以上距离，避免干扰",
        "location": "黄河湿地"
    }
from django.shortcuts import render

def bird_recognition_page(request):
    """水鸟识别页面"""
    return render(request, 'app_monitor/bird_recognition.html')
