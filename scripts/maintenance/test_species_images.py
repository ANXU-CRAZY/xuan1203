#!/usr/bin/env python
"""测试物种图片加载"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# 清除缓存
import app_monitor.views
app_monitor.views._SPECIES_IMG_CACHE = None

from app_monitor.views import _load_species_image_map, _lookup_species_image
from app_monitor.models import SpeciesInfo
from app_monitor.serializers import SpeciesInfoSerializer
from rest_framework.request import Request
from django.test import RequestFactory

print("=" * 80)
print("测试物种图片加载")
print("=" * 80)

# 1. 加载图片映射
image_map = _load_species_image_map()
print(f"\n✅ 加载了 {len(image_map)} 个物种图片映射")

# 2. 测试前10个物种
factory = RequestFactory()
request = factory.get('/')

print("\n测试前10个物种的图片URL：\n")
for species in SpeciesInfo.objects.all()[:10]:
    name = species.name_cn
    
    # 方法1：直接查找
    direct_url = _lookup_species_image(image_map, name)
    
    # 方法2：通过Serializer
    serializer = SpeciesInfoSerializer(species, context={'request': request})
    api_url = serializer.data.get('cover_image_url')
    
    print(f"物种: {name}")
    print(f"  直接查找: {direct_url[:80] if direct_url else '❌ None'}...")
    print(f"  API返回: {api_url[:80] if api_url else '❌ None'}...")
    print()

print("=" * 80)
