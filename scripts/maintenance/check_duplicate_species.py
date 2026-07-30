#!/usr/bin/env python
"""检查重复的物种"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from app_monitor.models import SpeciesInfo
from collections import Counter

print("=" * 80)
print("检查重复物种")
print("=" * 80)

# 统计物种名称出现次数
names = [s.name_cn for s in SpeciesInfo.objects.all()]
name_counts = Counter(names)

# 找出重复的
duplicates = {name: count for name, count in name_counts.items() if count > 1}

if duplicates:
    print(f"\n❌ 发现 {len(duplicates)} 个重复的物种名称：\n")
    for name, count in duplicates.items():
        print(f"  {name}: {count} 条记录")
        species_list = SpeciesInfo.objects.filter(name_cn=name)
        for s in species_list:
            print(f"    - ID: {s.id}, 拉丁名: {s.name_latin}, 保护级别: {s.protection_level}")
    
    print("\n建议：在Django admin后台删除重复的物种记录")
else:
    print("\n✅ 没有发现重复的物种")

print("\n" + "=" * 80)
