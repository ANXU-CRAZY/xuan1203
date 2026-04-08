from django.shortcuts import render
from django.http import HttpResponse
from django.db import connection
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Q  # 引入 Q 用于复杂查询

# DRF 相关引用
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

# GIS 相关引用
try:
    from django.contrib.gis.geos import Point
    from django.contrib.gis.measure import D
except ImportError:
    Point = None
    D = None

# === 引入模型 ===
# 确保包含 Product, UserProfile
from .models import ObservationRecord, WetlandZone, MonitoringRoute, Product, UserProfile
from django.contrib.auth.models import User

# === 引入序列化器 ===
from .serializers import (
    ObservationRecordSerializer,
    WetlandZoneSerializer,
    MonitoringRouteSerializer,
    ProductSerializer,
    UserInfoSerializer
)


# ==========================================
# 1. 监测点位视图 /api/zones/
# ==========================================
class ZoneViewSet(viewsets.ModelViewSet):
    queryset = WetlandZone.objects.all()
    serializer_class = WetlandZoneSerializer


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
# 5. 用户档案视图 /api/profiles/
# ==========================================
class UserProfileViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserInfoSerializer
    permission_classes = [permissions.IsAuthenticated]

    # GET /api/profiles/me/  <-- 前端获取自己信息的接口
    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


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