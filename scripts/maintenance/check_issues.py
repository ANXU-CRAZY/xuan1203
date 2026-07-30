#!/usr/bin/env python
"""检查物种图片和重复问题"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from app_monitor.models import SpeciesInfo
from collections import Counter

print("=" * 80)
print("1. 检查重复物种")
print("=" * 80)

names = [s.name_cn for s in SpeciesInfo.objects.all()]
name_counts = Counter(names)
duplicates = {name: count for name, count in name_counts.items() if count > 1}

if duplicates:
    print(f"\n发现 {len(duplicates)} 个重复的物种名称：\n")
    for name, count in duplicates.items():
        print(f"  {name}: {count} 条记录")
        species_list = SpeciesInfo.objects.filter(name_cn=name)
        for s in species_list:
            print(f"    - ID: {s.id}, 拉丁名: {s.name_latin or '无'}")
else:
    print("\n没有发现重复的物种")

print("\n" + "=" * 80)
print("2. 检查物种图片情况")
print("=" * 80)

total = SpeciesInfo.objects.count()
with_cover = SpeciesInfo.objects.exclude(cover_image='').exclude(cover_image__isnull=True).count()
with_gallery = SpeciesInfo.objects.filter(images__isnull=False).distinct().count()

print(f"\n总物种数: {total}")
print(f"有封面图的: {with_cover}")
print(f"有图库图片的: {with_gallery}")
print(f"没有任何图片的: {total - max(with_cover, with_gallery)}")

print("\n" + "=" * 80)
