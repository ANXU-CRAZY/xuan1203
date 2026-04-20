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
    index_view, UserProfileViewSet, bird_recognition_page,
    ProductViewSet, SpeciesViewSet, RegisterViewSet,
    ArticleViewSet, SpeciesImageViewSet,
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
    path('api/', include(router.urls)),

    # 专为前端准备的登录接口
    path('api/login/', obtain_auth_token, name='api_token_auth'),

    # 水鸟识别 API（由 bird_recognition 应用提供）
    path('bird/', include('bird_recognition.urls')),

    # 水鸟识别前端页面（集成在 app_monitor 中）
    path('bird-page/', bird_recognition_page, name='bird_recognition'),
]

# === 3. 核心修复：强制让 Django 处理静态文件 ===
urlpatterns += [
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
