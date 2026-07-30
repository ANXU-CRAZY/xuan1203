#!/usr/bin/env python
"""
检查物种图片加载问题
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from app_monitor.views import _load_species_image_map
from app_monitor.models import SpeciesInfo

print("=" * 60)
print("物种图片诊断")
print("=" * 60)

# 1. 检查图片映射加载
img_map = _load_species_image_map()
print(f"\n✅ 加载了 {len(img_map)} 个物种图片映射")
if len(img_map) > 0:
    print(f"前5个物种图片:")
    for i, (name, url) in enumerate(list(img_map.items())[:5]):
        print(f"  {i+1}. {name}: {url[:80]}...")
else:
    print("❌ 警告：没有加载到任何图片映射！")

# 2. 检查数据库中的物种数量
species_count = SpeciesInfo.objects.count()
print(f"\n✅ 数据库中有 {species_count} 个物种")

# 3. 检查有多少物种有图片
species_with_images = 0
species_without_images = []
for species in SpeciesInfo.objects.all()[:20]:  # 只检查前20个
    name = species.name_cn
    if name in img_map:
        species_with_images += 1
    else:
        species_without_images.append(name)

print(f"\n前20个物种中:")
print(f"  ✅ 有图片: {species_with_images} 个")
print(f"  ❌ 无图片: {len(species_without_images)} 个")
if species_without_images:
    print(f"  缺失图片的物种: {', '.join(species_without_images[:10])}")

print("\n" + "=" * 60)
