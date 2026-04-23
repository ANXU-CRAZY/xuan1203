from django.contrib import admin
from leaflet.admin import LeafletGeoAdmin
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget
# 👇 引入所有用到的模型 (记得加 Product)
from .models import SpeciesInfo, WetlandZone, MonitoringRoute, UserProfile, ObservationRecord, AIDetectionResult, \
    Product, SpeciesImage
from datetime import datetime

# ====================
# 0. 全局后台配置
# ====================
admin.site.site_header = '湿地监测管理后台'
admin.site.site_title = '湿地监测系统'
admin.site.index_title = '系统管理'


# ====================
# 1. 资源映射配置 (Import/Export)
# ====================

# (1) 观测记录导入配置
class ObservationRecordResource(resources.ModelResource):
    # 定义 Excel 列名与数据库外键的对应
    species = fields.Field(column_name='中文名', attribute='species', widget=ForeignKeyWidget(SpeciesInfo, 'name_cn'))
    zone = fields.Field(column_name='loc', attribute='zone', widget=ForeignKeyWidget(WetlandZone, 'name'))

    # 映射简单字段
    observation_time = fields.Field(attribute='observation_time', column_name='date')
    count = fields.Field(attribute='count', column_name='abundance')

    class Meta:
        model = ObservationRecord
        # 使用这三个字段组合来判断唯一性，防止重复导入
        import_id_fields = ('species', 'zone', 'observation_time')
        fields = ('species', 'zone', 'observation_time', 'count')
        exclude = ('id',)

    def before_import_row(self, row, **kwargs):
        """
        导入前的预处理逻辑：
        1. 格式化日期
        2. 自动创建不存在的物种
        3. 自动创建不存在的点位
        """
        # --- A. 处理日期格式 ---
        date_str = str(row.get('date', '')).strip()
        if '/' in date_str:
            try:
                dt = datetime.strptime(date_str, '%Y/%m/%d')
                row['date'] = dt.strftime('%Y-%m-%d')
            except ValueError:
                pass

        # --- B. 自动保存物种信息 ---
        name_cn = str(row.get('中文名', '')).strip()
        row['中文名'] = name_cn

        if name_cn:
            species_defaults = {
                'name_latin': str(row.get('species', '')).strip(),
                'order': str(row.get('目', '')).strip(),
                'family': str(row.get('科', '')).strip(),
                'protection_level': str(row.get('保护级别', '')).strip()
            }
            if species_defaults['protection_level'] in ['nan', 'NaN', 'None']:
                species_defaults['protection_level'] = ''

            SpeciesInfo.objects.update_or_create(
                name_cn=name_cn,
                defaults=species_defaults
            )

        # --- C. 自动保存点位信息 ---
        loc_name = str(row.get('loc', '')).strip()
        row['loc'] = loc_name

        if loc_name:
            try:
                x_val = float(row.get('x'))
                y_val = float(row.get('y'))
            except (ValueError, TypeError):
                x_val, y_val = None, None

            zone_defaults = {}
            if x_val is not None and y_val is not None:
                zone_defaults['longitude'] = x_val
                zone_defaults['latitude'] = y_val

            WetlandZone.objects.update_or_create(
                name=loc_name,
                defaults=zone_defaults
            )

        # --- D. 导入的数据默认设为已通过 (可选) ---
        # 如果你希望 Excel 导入的历史数据直接显示，取消下面这行的注释
        # row['status'] = 'approved'


# (2) 其他 Resource
class WetlandZoneResource(resources.ModelResource):
    name = fields.Field(attribute='name', column_name='loc')
    longitude = fields.Field(attribute='longitude', column_name='x')
    latitude = fields.Field(attribute='latitude', column_name='y')

    class Meta:
        model = WetlandZone
        import_id_fields = ('name',)
        fields = ('name', 'longitude', 'latitude')


class SpeciesInfoResource(resources.ModelResource):
    name_cn = fields.Field(attribute='name_cn', column_name='中文名')

    class Meta:
        model = SpeciesInfo
        import_id_fields = ('name_cn',)


# ====================
# 2. 管理后台注册
# ====================

@admin.register(SpeciesInfo)
class SpeciesInfoAdmin(ImportExportModelAdmin):
    resource_class = SpeciesInfoResource
    list_display = ('name_cn', 'name_latin', 'order', 'family', 'protection_level')
    search_fields = ('name_cn', 'name_latin')
    list_filter = ('protection_level', 'order')


@admin.register(WetlandZone)
class WetlandZoneAdmin(LeafletGeoAdmin, ImportExportModelAdmin):
    resource_class = WetlandZoneResource
    list_display = ('name', 'longitude', 'latitude')
    search_fields = ('name',)
    # 设置地图默认中心点 (郑州附近)
    settings_overrides = {'DEFAULT_CENTER': (34.75, 113.62), 'DEFAULT_ZOOM': 10}


@admin.register(ObservationRecord)
class ObservationRecordAdmin(ImportExportModelAdmin):
    resource_class = ObservationRecordResource
    # 👇 增加了 uploader 显示，方便看是谁传的
    list_display = ('id', 'species', 'zone', 'count', 'uploader', 'status', 'observation_time')
    list_filter = ('status', 'observation_time', 'zone')
    search_fields = ('species__name_cn', 'zone__name', 'uploader__username')
    date_hierarchy = 'observation_time'

    # 注册批量操作动作
    actions = ['approve_records', 'reject_records']

    # 动作1: 批量通过
    @admin.action(description='✅ 批量通过审核')
    def approve_records(self, request, queryset):
        # 注意：这里必须用字符串 'approved'，不能用数字 1
        rows_updated = queryset.update(status='approved')
        self.message_user(request, f"{rows_updated} 条记录已审核通过。")

    # 动作2: 批量驳回
    @admin.action(description='❌ 批量驳回')
    def reject_records(self, request, queryset):
        rows_updated = queryset.update(status='rejected')
        self.message_user(request, f"{rows_updated} 条记录已驳回。")


@admin.register(MonitoringRoute)
class MonitoringRouteAdmin(LeafletGeoAdmin):
    list_display = ('name', 'description')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    # 👇 这里的字段名改为 score (对应新 Model)
    list_display = ('user', 'score', 'avatar')
    search_fields = ('user__username',)


# 👇 新增：商品后台管理
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'stock')
    search_fields = ('name',)
    list_editable = ('stock', 'price')  # 允许在列表页直接改库存和价格


@admin.register(AIDetectionResult)
class AIDetectionResultAdmin(admin.ModelAdmin):
    list_display = ('species_name', 'confidence', 'created_at')


@admin.register(SpeciesImage)
class SpeciesImageAdmin(admin.ModelAdmin):
    list_display = ('species', 'caption', 'source', 'is_featured', 'views', 'created_at')
    list_filter = ('source', 'is_featured', 'created_at')
    search_fields = ('species__name_cn', 'caption')
    list_editable = ('is_featured',)
