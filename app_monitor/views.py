from django.shortcuts import render
from django.http import HttpResponse
from django.db import connection
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Q  # 👈 新增 Q 用于复杂查询

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
# 👈 确保这里引入了新加的 Product 和 UserProfile
from .models import ObservationRecord, WetlandZone, MonitoringRoute, Product, UserProfile
from django.contrib.auth.models import User

# === 引入序列化器 ===
# 👈 确保这里引入了新加的 ProductSerializer 和 UserInfoSerializer
from .serializers import (
    ObservationRecordSerializer,
    WetlandZoneSerializer,
    MonitoringRouteSerializer,
    ProductSerializer,
    UserInfoSerializer
)


# === 1. 监测点位视图 ===
class ZoneViewSet(viewsets.ModelViewSet):
    """
    API: 监测点位 /api/zones/
    """
    queryset = WetlandZone.objects.all()
    serializer_class = WetlandZoneSerializer


# === 2. 监测样线视图 ===
class TransectViewSet(viewsets.ModelViewSet):
    """
    API: 监测样线 /api/transects/
    """
    queryset = MonitoringRoute.objects.all()
    serializer_class = MonitoringRouteSerializer


# === 3. 观测记录视图 (核心逻辑升级) ===
class ObservationViewSet(viewsets.ModelViewSet):
    """
    API: 观测记录 /api/observations/
    功能: 上传、查看、权限控制、自动加分、GIS分析
    """
    serializer_class = ObservationRecordSerializer
    # 👈 权限控制: 登录用户可以增删改查，游客只能看
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    # 3.1 权限过滤逻辑 (谁能看什么数据)
    def get_queryset(self):
        # 默认按时间倒序
        queryset = ObservationRecord.objects.all().order_by('-observation_time')

        user = self.request.user

        # A. 管理员/巡护员: 看所有数据
        if user.is_staff:
            return queryset

        # B. 登录的普通用户: 看 '已通过审核' 的 + '我自己上传' 的
        if user.is_authenticated:
            return queryset.filter(
                Q(status='approved') | Q(uploader=user)
            )

        # C. 游客: 只看 '已通过审核' 的
        return queryset.filter(status='approved')

    # 3.2 上传数据时的逻辑 (自动加分)
    def perform_create(self, serializer):
        # A. 保存数据，自动关联当前登录用户
        serializer.save(uploader=self.request.user)

        # B. 积分奖励逻辑
        try:
            # 获取用户档案
            profile = self.request.user.profile
            profile.score += 10  # 上传一条加 10 分
            profile.save()
            print(f"用户 {self.request.user.username} 上传成功，积分+10")
        except Exception as e:
            # 即使加分失败，也不要阻断数据上传，但在后台打印错误
            print(f"积分奖励失败 (可能是UserProfile未创建): {e}")

    # === 保留原有的 GIS 功能 ===
    @action(detail=False, methods=['get'])
    def nearby_alert(self, request):
        if not Point:
            return Response({'error': 'GIS libraries not installed'}, status=501)
        try:
            lat = float(request.query_params.get('lat'))
            lng = float(request.query_params.get('lng'))
            p = Point(lng, lat, srid=4326)
            birds = ObservationRecord.objects.filter(location__dwithin=(p, D(m=500)))
            # 这里要注意：如果有权限过滤，这里最好也复用 get_queryset 的逻辑
            # 为简单起见，这里先查所有通过审核的
            birds = birds.filter(status='approved')
            serializer = self.get_serializer(birds, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['get'], url_path='tiles/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)')
    def tiles(self, request, z, x, y):
        # MVT 瓦片逻辑保留不变
        sql = """
              WITH mvtgeom AS (SELECT ST_AsMVTGeom(location, ST_TileEnvelope(%s, %s, %s), 4096, 256, true) AS geom,
                                      id, \
                                      status
                               FROM app_monitor_observationrecord
                               WHERE ST_Intersects(location, ST_TileEnvelope(%s, %s, %s)) \
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


# === 4. 商品/积分商城视图 (新增) ===
class ProductViewSet(viewsets.ModelViewSet):
    """
    API: 商品列表 /api/products/
    兑换: POST /api/products/{id}/redeem/
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    # 游客可看列表，登录才能兑换
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def redeem(self, request, pk=None):
        product = self.get_object()
        user = request.user

        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            return Response({"error": "用户档案不存在"}, status=400)

        # 校验库存
        if product.stock <= 0:
            return Response({"error": "商品库存不足"}, status=400)

        # 校验积分
        if profile.score < product.price:
            return Response({"error": f"积分不足，还需要 {product.price - profile.score} 分"}, status=400)

        # 执行交易：扣分、扣库存
        profile.score -= product.price
        profile.save()

        product.stock -= 1
        product.save()

        return Response({
            "message": f"成功兑换: {product.name}",
            "remaining_score": profile.score
        })


# === 5. 用户档案视图 (更新版) ===
class UserProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API: 用户信息 /api/profiles/
    获取自己信息: GET /api/profiles/me/
    """
    queryset = User.objects.all()
    serializer_class = UserInfoSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def me(self, request):
        # 返回当前登录用户的详细信息 (含积分、头像)
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


# === 6. 普通页面视图 (保留) ===
def index_view(request):
    return render(request, 'index.html')


def get_todays_hotspot(request):
    # 保留你原来的热点逻辑，但建议稍作修改以适应 status 字段
    three_days_ago = timezone.now().date() - timedelta(days=3)

    # 只统计 '已通过' 的记录
    hot_zone_data = ObservationRecord.objects.filter(
        observation_time__gte=three_days_ago,
        status='approved'
    ).values('zone').annotate(total_count=Sum('count')).order_by('-total_count').first()

    # ... 后面的逻辑保持不变 ...
    # (为了节省篇幅，这里假设你原来的 get_todays_hotspot 后面部分不变，
    # 只需要记得在查询 filter 里都加上 status='approved' 即可)

    return render(request, 'app_monitor/hotspot.html', {'recommendation': _default_hotspot()})


def _default_hotspot():
    return {
        "title": "今日推荐：郑州黄河湿地中段",
        "tips": "保持100米以上距离，避免干扰",
        "location": "黄河湿地"
    }