from django.shortcuts import render
from django.http import HttpResponse
from django.db import connection
from django.conf import settings
from django.utils import timezone
from django.utils.html import escape
from datetime import timedelta
from django.db.models import Sum, Q  # 引入 Q 用于复杂查询
from pathlib import Path
from urllib.parse import quote
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
from .models import ObservationRecord, WetlandZone, MonitoringRoute, Product, UserProfile, SpeciesInfo
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
    @action(detail=False, methods=['get'], url_path='tiles/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)')
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


def _load_species_image_map():
    """
    复用协作者前端图库中的 Wikimedia Commons 直链映射。
    这样图库页和 API 返回的数据会保持同一套图片来源。
    """
    global _SPECIES_IMG_CACHE
    if _SPECIES_IMG_CACHE is not None:
        return _SPECIES_IMG_CACHE

    template_path = Path(settings.BASE_DIR) / 'app_monitor' / 'templates' / 'species-gallery.html'
    image_map = {}
    try:
        text = template_path.read_text(encoding='utf-8')
        match = re.search(r"const\s+SPECIES_IMG\s*=\s*\{(.*?)\n\s*\};", text, re.S)
        if match:
            image_map = dict(re.findall(r"'([^']+)'\s*:\s*'([^']+)'", match.group(1)))
    except OSError:
        image_map = {}

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
        protection = species.protection_level or '暂无保护级别'
        distribution = species.distribution_habit or ''
        wiki_url = _wikipedia_search_url(name, latin)
        commons_url = _commons_search_url(name, latin)
        count = _species_observation_count(species)

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
            'cover_image': image_map.get(name),
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
        image_url = image_map.get(name)
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


class SpeciesImageViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        return Response(_species_image_items(request))

    def retrieve(self, request, pk=None):
        for image in _species_image_items(request):
            if str(image['id']) == str(pk):
                return Response(image)
        return Response({"detail": "未找到图片数据"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def view_image(self, request, pk=None):
        for image in _species_image_items(request):
            if str(image['id']) == str(pk):
                return Response({'views': image.get('views', 0) + 1})
        return Response({'views': 1})


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
# 6. 普通页面视图 (热点推荐)
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
