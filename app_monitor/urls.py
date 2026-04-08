from django.urls import path
from . import views

# 设置应用命名空间（可选，便于在模板中反向解析）
app_name = 'app_monitor'

urlpatterns = [
    # 其他已有路由...
    path('bird/', views.bird_recognition_page, name='bird_recognition'),
]