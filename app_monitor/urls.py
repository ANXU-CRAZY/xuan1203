from django.urls import path
from django.views.generic import RedirectView

# 设置应用命名空间（可选，便于在模板中反向解析）
app_name = 'app_monitor'

urlpatterns = [
    path('bird/', RedirectView.as_view(pattern_name='huiyan'), name='bird_recognition'),
]
