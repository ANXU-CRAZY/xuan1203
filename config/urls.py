from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from app_monitor.views import ObservationViewSet, ZoneViewSet, TransectViewSet, index_view, UserProfileViewSet

# === 1. 注册 API 路由 ===
router = DefaultRouter()
router.register(r'observations', ObservationViewSet, basename='observation')
router.register(r'zones', ZoneViewSet)
router.register(r'transects', TransectViewSet)
router.register(r'profiles', UserProfileViewSet)

# === 2. 定义 URL 模式 ===
urlpatterns = [
    # 首页直接指向 index_view
    path('', index_view, name='home'),

    # 管理后台
    path('admin/', admin.site.urls),

    # API 接口
    path('api/', include(router.urls)),

    # 专为前端准备的登录接口
    path('api/login/', obtain_auth_token, name='api_token_auth'),
]

# === 3. 核心修复：强制让 Django 处理静态文件 ===
# 这部分代码解决了 Gunicorn 下 Admin 后台没有样式的问题
# 它会拦截 /static/ 和 /media/ 开头的请求，并直接返回文件
urlpatterns += [
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]