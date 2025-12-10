from rest_framework import serializers
# 引入所有需要的模型 (确保 models.py 里已经有了 Product 和 UserProfile)
from .models import ObservationRecord, WetlandZone, MonitoringRoute, Product, UserProfile
from django.contrib.auth.models import User


# ==========================================
# 1. 新增：商品序列化器 (用于积分商城)
# ==========================================
class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'  # 返回 id, name, price, image, description, stock


# ==========================================
# 2. 新增：用户信息序列化器 (用于个人中心)
# ==========================================
class UserInfoSerializer(serializers.ModelSerializer):
    # 从关联的 UserProfile 表中读取积分和头像
    score = serializers.IntegerField(source='profile.score', read_only=True)
    avatar = serializers.ImageField(source='profile.avatar', read_only=True)

    class Meta:
        model = User
        # 前端获取 /api/profiles/me/ 时会得到这些字段
        fields = ['id', 'username', 'email', 'score', 'avatar']


# ==========================================
# 3. 监测样线 (保留你原来的逻辑)
# ==========================================
class MonitoringRouteSerializer(serializers.ModelSerializer):
    path = serializers.SerializerMethodField()

    class Meta:
        model = MonitoringRoute
        fields = ['id', 'name', 'description', 'path']

    def get_path(self, obj):
        # 将 MultiLineString 转换为 Leaflet 坐标数组 [[lat, lng], ...]
        if obj.path_geom:
            lines = []
            for line in obj.path_geom:
                # 调换坐标顺序: 数据库(x,y) -> Leaflet(y,x)
                lines.append([[pt[1], pt[0]] for pt in line.coords])
            return lines
        return []


# ==========================================
# 4. 监测点位 (保留你原来的逻辑)
# ==========================================
class WetlandZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = WetlandZone
        fields = '__all__'


# ==========================================
# 5. 观测记录 (核心升级)
# ==========================================
class ObservationRecordSerializer(serializers.ModelSerializer):
    # --- 1. 字段显示优化 (ReadOnly) ---

    # 获取上传者的名字 (对应 model 里的 uploader 字段)
    uploader_name = serializers.CharField(source='uploader.username', read_only=True)

    # 获取物种中文名
    species_name = serializers.ReadOnlyField(source='species.name_cn')
    species_protection = serializers.ReadOnlyField(source='species.protection_level')

    # 获取关联区域名字 (如果有)
    zone_name = serializers.ReadOnlyField(source='zone.name')

    # --- 2. 坐标处理 ---
    # 优先使用记录自带的 Point 坐标，如果没有，再尝试去拿 Zone 的坐标
    # 这样既支持固定点位监测，也支持用户随意上传的新点位
    lat = serializers.SerializerMethodField()
    lng = serializers.SerializerMethodField()

    class Meta:
        model = ObservationRecord
        fields = [
            'id',
            'image',
            'description',  # 描述
            'observation_time',
            'count',
            'status',  # 新增：审核状态 (pending/approved)
            'species',  # 上传时填 ID
            'species_name',  # 显示时看名字
            'species_protection',
            'uploader',  # 关联的用户 ID
            'uploader_name',  # 显示的用户名
            'zone',
            'zone_name',
            'lat', 'lng'  # 统一返回 lat/lng 方便前端 Leaflet 使用
        ]
        # 设置只读字段，防止用户篡改审核状态
        read_only_fields = ['status', 'uploader', 'observation_time']

    def get_lat(self, obj):
        # 如果这条记录自己有坐标 (GIS PointField)，优先用自己的
        if hasattr(obj, 'location') and obj.location:
            return obj.location.y
        # 如果没有，尝试用关联区域的坐标
        if obj.zone:
            return obj.zone.latitude
        return None

    def get_lng(self, obj):
        if hasattr(obj, 'location') and obj.location:
            return obj.location.x
        if obj.zone:
            return obj.zone.longitude
        return None