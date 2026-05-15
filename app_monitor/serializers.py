from rest_framework import serializers
# 引入所有需要的模型
from .models import ObservationRecord, WetlandZone, MonitoringRoute, Product, UserProfile, SpeciesInfo, SpeciesImage
from .protection import get_protection_group, normalize_protection_level
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
    protection_level = serializers.SerializerMethodField()
    observation_count = serializers.SerializerMethodField()
    last_observed = serializers.SerializerMethodField()
    iucn_status = serializers.SerializerMethodField()
    article_count = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    gallery_images = SpeciesImageSerializer(source='images', many=True, read_only=True)
    gallery_count = serializers.SerializerMethodField()
    description = serializers.CharField(source='distribution_habit', read_only=True)

    class Meta:
        model = SpeciesInfo
        fields = [
            'id', 'name_cn', 'name_latin', 'order', 'family',
            'protection_level', 'distribution_habit', 'description', 'cover_image',
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

    def get_protection_level(self, obj):
        return normalize_protection_level(obj.protection_level)

    def get_iucn_status(self, obj):
        group = get_protection_group(obj.protection_level)
        if group == '国家一级':
            return {'code': 'EN', 'label': '濒危', 'color': '#e74c3c', 'desc': '国家一级重点保护，需重点关注'}
        if group == '国家二级':
            return {'code': 'VU', 'label': '易危', 'color': '#f39c12', 'desc': '国家二级重点保护，需持续监测'}
        if group == '三有动物':
            return {'code': 'NT', 'label': '近危', 'color': '#3498db', 'desc': '国家三有保护动物，需规范记录'}
        return {'code': 'LC', 'label': '无危', 'color': '#27ae60', 'desc': '暂无重点保护等级'}

    def get_article_count(self, obj):
        return 1

    def get_cover_image_url(self, obj):
        # 1. 优先使用数据库中的 cover_image 字段
        if obj.cover_image and str(obj.cover_image) not in ('', 'False', 'None'):
            request = self.context.get('request')
            path = str(obj.cover_image).lstrip('/')
            if request:
                return request.build_absolute_uri('/media/' + path)
            return '/media/' + path

        # 2. 查找精选图片
        featured = obj.images.filter(is_featured=True).first()
        if featured:
            return self._resolve_image_url(featured)

        # 3. 查找第一张图片
        first_image = obj.images.order_by('-views', '-created_at').first()
        if first_image:
            return self._resolve_image_url(first_image)

        # 4. Fallback: 从前端模板的 SPECIES_IMG 映射中查找
        from .views import _load_species_image_map, _lookup_species_image
        image_map = _load_species_image_map()
        fallback_url = _lookup_species_image(image_map, obj.name_cn)
        if fallback_url:
            return fallback_url

        # 5. 最终兜底：用拉丁名生成 Wikimedia Commons Special:FilePath URL
        # 这样即使没有任何图片，也能尝试从Wikimedia获取
        if obj.name_latin:
            from urllib.parse import quote
            latin_clean = obj.name_latin.replace(' ', '_')
            return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(latin_clean)}.jpg"

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
    species_protection = serializers.SerializerMethodField()
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
        # 优先取观测记录自身坐标；没有时再回退到关联点位坐标。
        if obj.location:
            return obj.location.x
        if obj.longitude is not None:
            return obj.longitude
        if obj.zone:
            return obj.zone.longitude
        return None

    def get_y(self, obj):
        # 优先取观测记录自身坐标；没有时再回退到关联点位坐标。
        if obj.location:
            return obj.location.y
        if obj.latitude is not None:
            return obj.latitude
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

    def get_species_protection(self, obj):
        if obj.species:
            return normalize_protection_level(obj.species.protection_level)
        return ''

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
