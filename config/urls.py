from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.shortcuts import render
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from app_monitor.views import (
    ObservationViewSet, ZoneViewSet, TransectViewSet,
    index_view, ecology_center_view, ecology_3d_view, ecology_scene_river, ecology_realspace_proxy, ecology_iserver_probe_proxy, ecology_report_view, supermap_3d_sdk_proxy, UserProfileViewSet, bird_recognition_page,
    ProductViewSet, SpeciesViewSet, RegisterViewSet,
    ArticleViewSet, SpeciesImageViewSet,
    ai_chat, map_observations, supermap_status, supermap_protected_buffer,
    supermap_pick_observation, supermap_thematic_points,
    ecology_layers, ecology_capacity, ecology_risk_alerts, ecology_hotspots,
    ecology_patrol_plan, ecology_live_feed, ecology_report_data,
    ecology_dem_imagery_health,
    local_terrain_config, local_terrain_tile,
)

# === 1. 注册 API 路由 ===
router = DefaultRouter()
router.register(r'species', SpeciesViewSet, basename='species')
router.register(r'observations', ObservationViewSet, basename='observation')
router.register(r'zones', ZoneViewSet)
router.register(r'transects', TransectViewSet)
router.register(r'profiles', UserProfileViewSet)
router.register(r'products', ProductViewSet, basename='product')
router.register(r'auth', RegisterViewSet, basename='auth')
router.register(r'articles', ArticleViewSet, basename='article')
router.register(r'species-images', SpeciesImageViewSet, basename='species-image')

# === 2. 定义 URL 模式 ===
urlpatterns = [
    # Generated B79 assets are also served in the local DEBUG=False demo.
    re_path(
        r'^static/app_monitor/eco/(?P<path>.*)$',
        serve,
        {'document_root': settings.BASE_DIR / 'app_monitor' / 'static' / 'app_monitor' / 'eco'},
    ),
    re_path(r'^supermap-sdk/(?P<path>.*)$', supermap_3d_sdk_proxy, name='supermap_3d_sdk_proxy'),
    # SuperMap3D resolves scene metadata relative to the iServer REST path.
    # Keep that exact path on the web origin so every follow-up request hits
    # the same compatibility proxy instead of becoming a browser 404.
    re_path(
        r'^iserver/services/YellowRiverEcology3D/rest/realspace(?:/(?P<resource_path>.*))?$',
        ecology_realspace_proxy,
        name='ecology_realspace_iserver_proxy',
    ),
    re_path(
        r'^iserver/(?P<probe_path>services/YellowRiverEcology3D\.rjson|manager/license\.json)$',
        ecology_iserver_probe_proxy,
        name='ecology_iserver_probe_proxy',
    ),
    # SuperMap3D resolves this capability probe from the current site root.
    path(
        'manager/license.json',
        ecology_iserver_probe_proxy,
        {'probe_path': 'manager/license.json'},
        name='ecology_iserver_license_proxy',
    ),
    # 首页直接指向 index_view
    path('', index_view, name='home'),
    path('supermap/', index_view, name='supermap'),
    path('ecology/', ecology_center_view, name='ecology_center'),
    path('ecology/3d/', ecology_3d_view, name='ecology_3d'),
    path('api/ecology/scene-assets/river/', ecology_scene_river, name='ecology_scene_river'),
    path('api/ecology/dem-imagery-health/', ecology_dem_imagery_health, name='ecology_dem_imagery_health'),
    # 本地生成的地形瓦片(绕开 iServer,供 SuperMapTerrainProvider isSct 加载)
    path('api/terrain/datas/terrain/config', local_terrain_config, name='local_terrain_config'),
    re_path(r'^api/terrain/datas/terrain/data/path/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)\.terrainz$', local_terrain_tile, name='local_terrain_tile'),
    re_path(r'^api/ecology/realspace(?:/(?P<resource_path>.*))?$', ecology_realspace_proxy, name='ecology_realspace_proxy'),
    path('ecology/report/', ecology_report_view, name='ecology_report'),
    path('supermap/status/', lambda r: render(r, 'supermap.html'), name='supermap_status_page'),

    # 协作者补充的前端页面
    path('report/', lambda r: render(r, 'report.html'), name='report'),
    path('profile/', lambda r: render(r, 'profile.html'), name='profile'),
    path('login/', lambda r: render(r, 'login.html'), name='login'),
    path('bird-guess/', lambda r: render(r, 'bird-guess.html'), name='bird_guess'),
    path('bird-runner/', lambda r: render(r, 'bird-runner.html'), name='bird_runner'),
    path('wetland-restorer/', lambda r: render(r, 'wetland-restorer.html'), name='wetland_restorer'),
    path('migration/', lambda r: render(r, 'migration.html'), name='migration'),
    path('wetland-detective/', lambda r: render(r, 'wetland-detective.html'), name='wetland_detective'),
    path('floating-island/', lambda r: render(r, 'floating-island.html'), name='floating_island'),
    path('species/', lambda r: render(r, 'species.html'), name='species'),
    re_path(r'^species/(?P<species_id>\d+)/$', lambda r, species_id: render(r, 'species-detail.html'), name='species_detail'),
    path('gallery/', lambda r: render(r, 'species-gallery.html'), name='species_gallery'),
    path('image-gallery/', lambda r: render(r, 'image-gallery.html'), name='image_gallery'),
    path('articles/', lambda r: render(r, 'articles.html'), name='articles'),
    re_path(r'^articles/(?P<article_id>\d+)/$', lambda r, article_id: render(r, 'article-detail.html'), name='article_detail'),

    # 管理后台
    path('admin/', admin.site.urls),

    # API 接口
    path('api/map-observations/', map_observations, name='map_observations'),
    path('api/supermap/status/', supermap_status, name='supermap_status'),
    path('api/supermap/protected-buffer/', supermap_protected_buffer, name='supermap_protected_buffer'),
    path('api/supermap/pick/', supermap_pick_observation, name='supermap_pick_observation'),
    path('api/supermap/thematic-points/', supermap_thematic_points, name='supermap_thematic_points'),
    path('api/ecology/layers/', ecology_layers, name='ecology_layers'),
    path('api/ecology/capacity/', ecology_capacity, name='ecology_capacity'),
    path('api/ecology/risk-alerts/', ecology_risk_alerts, name='ecology_risk_alerts'),
    path('api/ecology/hotspots/', ecology_hotspots, name='ecology_hotspots'),
    path('api/ecology/patrol-plan/', ecology_patrol_plan, name='ecology_patrol_plan'),
    path('api/ecology/live-feed/', ecology_live_feed, name='ecology_live_feed'),
    path('api/ecology/report-data/', ecology_report_data, name='ecology_report_data'),
    path('api/', include(router.urls)),

    # 专为前端准备的登录接口
    path('api/login/', obtain_auth_token, name='api_token_auth'),
    path('api/ai/chat/', ai_chat, name='ai_chat'),

    # 水鸟识别 API（由 bird_recognition 应用提供）
    path('bird/', include('bird_recognition.urls')),

    # 水鸟识别前端页面（集成在 app_monitor 中）
    path('bird-page/', bird_recognition_page, name='bird_recognition'),
]

# === 3. 开发环境静态文件服务 ===
if settings.DEBUG:
    # 开发模式下，Django会自动从STATICFILES_DIRS和各app的static目录加载
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # 生产环境由Nginx处理静态文件
    urlpatterns += [
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
