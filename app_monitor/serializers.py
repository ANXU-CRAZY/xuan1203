from rest_framework import serializers
# 引入所有需要的模型
from .models import ObservationRecord, WetlandZone, MonitoringRoute, Product, UserProfile, SpeciesInfo, SpeciesImage
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password


# ==========================================
# 0. 用户注册序列化器
# ==========================================
class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm']

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "两次密码输入不一致"})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        return User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password']
        )


# ==========================================
# 0b. 物种列表序列化器
# ==========================================
class SpeciesImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    source_display = serializers.SerializerMethodField()

    class Meta:
        model = SpeciesImage
        fields = [
            'id', 'species', 'url', 'caption', 'source', 'source_display',
            'source_url', 'source_author', 'views', 'is_featured', 'created_at'
        ]

    def get_url(self, obj):
        if obj.image and str(obj.image) not in ('', 'False', 'None'):
            request = self.context.get('request')
            path = str(obj.image).lstrip('/')
            if request:
                return request.build_absolute_uri('/media/' + path)
            return '/media/' + path
        if obj.image_url:
            return obj.image_url
        return None

    def get_source_display(self, obj):
        source_map = {
            'wikimedia': '维基百科',
            'birdsourcing': 'Birdsourcing',
            'ibc': 'Internet Bird Collection',
            'xeno_canto': 'Xeno-Canto',
            'npc': '中国鸟类图库',
            'manual': '手动上传',
            'other': '其他来源',
        }
        return source_map.get(obj.source, obj.source)


class SpeciesInfoSerializer(serializers.ModelSerializer):
    observation_count = serializers.SerializerMethodField()
    last_observed = serializers.SerializerMethodField()
    iucn_status = serializers.SerializerMethodField()
    article_count = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    gallery_images = SpeciesImageSerializer(source='images', many=True, read_only=True)
    gallery_count = serializers.SerializerMethodField()

    class Meta:
        model = SpeciesInfo
        fields = [
            'id', 'name_cn', 'name_latin', 'order', 'family',
            'protection_level', 'distribution_habit', 'cover_image',
            'cover_image_url', 'gallery_images', 'gallery_count',
            'observation_count', 'last_observed', 'iucn_status', 'article_count'
        ]

    def get_observation_count(self, obj):
        return ObservationRecord.objects.filter(species=obj, status='approved').count()

    def get_last_observed(self, obj):
        latest = ObservationRecord.objects.filter(
            species=obj,
            status='approved'
        ).order_by('-observation_time').first()
        if latest and latest.observation_time:
            return latest.observation_time.strftime('%Y-%m-%d')
        return None

    def get_iucn_status(self, obj):
        level = obj.protection_level or ''
        if '一级' in level or 'Ⅰ' in level:
            return {'code': 'EN', 'label': '濒危', 'color': '#e74c3c', 'desc': '野外濒危物种，数量极为稀少'}
        if '二级' in level or 'Ⅱ' in level:
            return {'code': 'VU', 'label': '易危', 'color': '#f39c12', 'desc': '易受威胁，需保护关注'}
        if '三有' in level:
            return {'code': 'NT', 'label': '近危', 'color': '#3498db', 'desc': '数量下降，需监控'}
        return {'code': 'LC', 'label': '无危', 'color': '#27ae60', 'desc': '种群稳定，无灭绝风险'}

    def get_article_count(self, obj):
        return 1

    def get_cover_image_url(self, obj):
        if obj.cover_image and str(obj.cover_image) not in ('', 'False', 'None'):
            request = self.context.get('request')
            path = str(obj.cover_image).lstrip('/')
            if request:
                return request.build_absolute_uri('/media/' + path)
            return '/media/' + path

        featured = obj.images.filter(is_featured=True).first()
        if featured:
            return self._resolve_image_url(featured)

        first_image = obj.images.order_by('-views', '-created_at').first()
        if first_image:
            return self._resolve_image_url(first_image)

        return None

    def _resolve_image_url(self, img_obj):
        if img_obj.image and str(img_obj.image) not in ('', 'False', 'None'):
            return '/media/' + str(img_obj.image).lstrip('/')
        return img_obj.image_url if img_obj.image_url else None

    def get_gallery_count(self, obj):
        return obj.images.count()


# ==========================================
# 1. 商品序列化器 (用于积分商城)
# ==========================================
class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'


# ==========================================
# 2. 用户信息序列化器 (用于个人中心)
# ==========================================
class UserInfoSerializer(serializers.ModelSerializer):
    # 从关联的 UserProfile 表中读取积分和头像
    score = serializers.IntegerField(source='profile.score', read_only=True)
    avatar = serializers.ImageField(source='profile.avatar', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'score', 'avatar']


# ==========================================
# 3. 监测样线 (保留原逻辑)
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
# 4. 监测点位 (保留原逻辑)
# ==========================================
class WetlandZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = WetlandZone
        fields = '__all__'


# ==========================================
# 5. 观测记录 (核心：兼容修复版)
# ==========================================
class ObservationRecordSerializer(serializers.ModelSerializer):
    # --- A. 必须恢复的旧字段 (为了让前端地图不报错) ---
    # 前端找的是 x 和 y，而不是 lat 和 lng
    x = serializers.SerializerMethodField()
    y = serializers.SerializerMethodField()

    # 前端找的是 reporter_name
    reporter_name = serializers.SerializerMethodField()

    # --- B. 新功能的字段 (后台管理用) ---
    uploader_name = serializers.ReadOnlyField(source='uploader.username')
    species_name = serializers.ReadOnlyField(source='species.name_cn')
    species_id = serializers.ReadOnlyField(source='species.id')
    species_protection = serializers.ReadOnlyField(source='species.protection_level')
    zone_name = serializers.ReadOnlyField(source='zone.name')
    transect_name = serializers.SerializerMethodField()

    # --- C. 备用新字段 (建议前端以后慢慢迁移到这两个字段) ---
    lat = serializers.SerializerMethodField()
    lng = serializers.SerializerMethodField()

    class Meta:
        model = ObservationRecord
        fields = [
            'id',
            'image',
            'description',
            'observation_time',
            'count',
            'status',  # 新增：审核状态
            'species', 'zone',  # ID 字段

            # === 显示字段 ===
            'species_name',
            'species_id',
            'species_protection',
            'zone_name',
            'transect_name',

            # === 坐标字段 (新旧共存) ===
            'x', 'y',  # 🚑 旧前端救命字段
            'lat', 'lng',  # ✨ 新前端推荐字段

            # === 人员字段 (新旧共存) ===
            'reporter_name',  # 🚑 旧前端救命字段
            'uploader_name'  # ✨ 新后台字段
        ]
        read_only_fields = ['status', 'uploader', 'observation_time']

    # ---------------------------------------------------
    # 逻辑实现：无论数据怎么存，都转换成前端能看懂的样子
    # ---------------------------------------------------

    def get_x(self, obj):
        # 逻辑：优先取 GIS 坐标点的 X，没有则取关联区域的经度
        if hasattr(obj, 'location') and obj.location:
            return obj.location.x
        if obj.zone:
            return obj.zone.longitude
        return None

    def get_y(self, obj):
        # 逻辑：优先取 GIS 坐标点的 Y，没有则取关联区域的纬度
        if hasattr(obj, 'location') and obj.location:
            return obj.location.y
        if obj.zone:
            return obj.zone.latitude
        return None

    # 为了方便以后迁移，lat/lng 直接复用 x/y 的逻辑
    def get_lng(self, obj):
        return self.get_x(obj)

    def get_lat(self, obj):
        return self.get_y(obj)

    def get_transect_name(self, obj):
        if not obj.zone:
            return None

        routes = self.context.get('_route_names')
        if routes is None:
            routes = list(MonitoringRoute.objects.values_list('name', flat=True))
            self.context['_route_names'] = routes

        zone_name = obj.zone.name or ''
        for route_name in routes:
            if zone_name and zone_name in route_name:
                return route_name
        return None

    def get_reporter_name(self, obj):
        # 逻辑：这行代码同时兼容了新数据(uploader)和旧数据(reporter)
        # 1. 优先显示“上传者”(新功能)
        if obj.uploader:
            return obj.uploader.username
        # 2. 如果没有上传者，尝试显示“上报人”(旧数据)
        if obj.reporter:
            return obj.reporter.username
        # 3. 如果都没有
        return "匿名用户"
