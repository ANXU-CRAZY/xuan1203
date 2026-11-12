from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.views.generic import RedirectView
from django.shortcuts import render
from rest_framework.routers import DefaultRouter
from app_monitor import account, password_reset
from app_monitor import monitoring, monitoring_report
from app_monitor import games
from app_monitor.views import (
    ObservationViewSet, ZoneViewSet, TransectViewSet,
    index_view, UserProfileViewSet,
    ProductViewSet, SpeciesViewSet, RegisterViewSet,
    ArticleViewSet, SpeciesImageViewSet,
    ai_chat, map_observations,
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
    # 首页直接指向 index_view
    path('', index_view, name='home'),

    # 协作者补充的前端页面
    path('report/', lambda r: render(r, 'report.html'), name='report'),
    path('profile/', lambda r: render(r, 'profile.html'), name='profile'),
    path('login/', account.login_page, name='login'),
    path('account/', account.entry, name='account_entry'),
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
    path('api/games/birds/', games.birds, name='game_birds'),
    path('api/map-observations/', map_observations, name='map_observations'),
    path('api/monitoring/years/', monitoring.years, name='monitoring_years'),
    path('api/monitoring/heatmap/', monitoring.heatmap, name='monitoring_heatmap'),
    path('api/monitoring/buffer/', monitoring.buffer_analysis, name='monitoring_buffer'),
    path('api/monitoring/buffer.csv', monitoring.buffer_csv, name='monitoring_buffer_csv'),
    path('api/monitoring/records/<int:record_id>/', monitoring.detail, name='monitoring_detail'),
    path('api/', include(router.urls)),

    # 专为前端准备的登录接口
    path('api/login/', account.PlatformTokenView.as_view(), name='api_token_auth'),
    path('api/auth/password-reset/send-code/', password_reset.send_code, name='password_reset_send'),
    path('api/auth/password-reset/confirm/', password_reset.confirm, name='password_reset_confirm'),
    path('api/account/login/', account.PlatformLoginView.as_view(), name='account_login'),
    path('api/account/session/', account.restore_session, name='account_session'),
    path('api/account/logout/', account.sign_out, name='account_logout'),
    path('api/ai/chat/', ai_chat, name='ai_chat'),
    path('api/ai/monitoring-report/', monitoring_report.download, name='ai_monitoring_report'),

    # 水鸟识别 API（由 bird_recognition 应用提供）
    path('bird/', include('bird_recognition.urls')),

    path('bird-page/', RedirectView.as_view(pattern_name='huiyan'), name='bird_recognition'),

    # 方舟慧眼（同源封装：不再启动独立 8765 服务）
    path('', include('config.huiyan_urls')),
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
