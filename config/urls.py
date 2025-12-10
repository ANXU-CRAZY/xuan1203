from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter

# ▼▼▼ 核心修复点：在这里加上 TransectViewSet ▼▼▼
from app_monitor.views import ObservationViewSet, ZoneViewSet, TransectViewSet, index_view, UserProfileViewSet
from rest_framework.authtoken.views import obtain_auth_token # 👈 引入这个自带视图
# 注册 API
router = DefaultRouter()
router.register(r'observations', ObservationViewSet, basename='observation')
router.register(r'zones', ZoneViewSet)
router.register(r'transects', TransectViewSet) # 现在这行代码就不会报错了
router.register(r'profiles', UserProfileViewSet)

urlpatterns = [
    # 首页直接指向 index_view
    path('', index_view, name='home'),

    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
# 👇 专为前端准备的登录接口
    path('api/login/', obtain_auth_token, name='api_token_auth'),
]

# 开发环境图片支持
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)