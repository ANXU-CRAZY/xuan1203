#!/usr/bin/env python
"""
合并重复物种：基于拉丁名 + 中文名相似度合并
自动执行，无需交互
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from app_monitor.models import SpeciesInfo, ObservationRecord, SpeciesImage
from collections import defaultdict


def find_duplicates_by_latin():
    """按拉丁名分组，找出重复"""
    groups = defaultdict(list)
    for s in SpeciesInfo.objects.exclude(name_latin='').exclude(name_latin__isnull=True):
        key = s.name_latin.strip().lower()
        if key:
            groups[key].append(s)
    return {k: v for k, v in groups.items() if len(v) > 1}


def find_duplicates_by_name():
    """按中文名相似度找出重复（如：暗绿绣眼 vs 暗绿绣眼鸟）"""
    all_species = list(SpeciesInfo.objects.all())
    groups = defaultdict(list)
    for s in all_species:
        # 去除"鸟"后缀，去除空格、括号等
        import re
        key = re.sub(r"[（）()\[\]【】\s·,，、/\\-]", "", (s.name_cn or '').strip())
        key = key.rstrip('鸟').strip()
        if key:
            groups[key].append(s)
    return {k: v for k, v in groups.items() if len(v) > 1}


def merge_species(keep, delete_list):
    """把 delete_list 中物种的所有数据迁移到 keep，然后删除"""
    for s in delete_list:
        if s.id == keep.id:
            continue
        # 迁移观测记录
        obs_count = ObservationRecord.objects.filter(species=s).update(species=keep)
        # 迁移图库图片
        img_count = SpeciesImage.objects.filter(species=s).update(species=keep)
        # 如果 keep 没有图但 s 有，迁移过来
        if not keep.cover_image and s.cover_image:
            keep.cover_image = s.cover_image
            keep.save()
        if (not keep.distribution_habit or keep.distribution_habit == '暂无详细习性数据') and s.distribution_habit and s.distribution_habit != '暂无详细习性数据':
            keep.distribution_habit = s.distribution_habit
            keep.save()
        if not keep.protection_level and s.protection_level:
            keep.protection_level = s.protection_level
            keep.save()
        # 删除被合并的物种
        print(f"  ✂️  删除: {s.name_cn} (ID:{s.id}) - 迁移了 {obs_count} 条观测, {img_count} 张图")
        s.delete()


def choose_keep(species_list):
    """从一组重复物种中选择保留哪一个：优先有图片、有描述、名字短的"""
    def score(s):
        return (
            1 if s.cover_image else 0,
            1 if s.distribution_habit and s.distribution_habit != '暂无详细习性数据' else 0,
            1 if s.images.exists() else 0,
            -len(s.name_cn or ''),  # 名字短的优先（"暗绿绣眼" 比 "暗绿绣眼鸟" 优先）
            -s.id  # ID 小的优先
        )
    return max(species_list, key=score)


print("=" * 80)
print("自动合并重复物种")
print("=" * 80)

total_before = SpeciesInfo.objects.count()
print(f"\n合并前物种总数: {total_before}")

# 1. 按拉丁名合并
latin_dups = find_duplicates_by_latin()
print(f"\n📋 按拉丁名找到 {len(latin_dups)} 组重复，开始合并...\n")
merged_count_latin = 0
for latin, group in latin_dups.items():
    keep = choose_keep(group)
    delete_list = [s for s in group if s.id != keep.id]
    print(f"🔹 [{latin}] 保留: {keep.name_cn} (ID:{keep.id})")
    merge_species(keep, delete_list)
    merged_count_latin += len(delete_list)

# 2. 按中文名合并（处理"鸟"后缀差异）
name_dups = find_duplicates_by_name()
print(f"\n📋 按中文名找到 {len(name_dups)} 组重复，开始合并...\n")
merged_count_name = 0
for key, group in name_dups.items():
    keep = choose_keep(group)
    delete_list = [s for s in group if s.id != keep.id]
    if delete_list:
        print(f"🔹 [{key}] 保留: {keep.name_cn} (ID:{keep.id})")
        merge_species(keep, delete_list)
        merged_count_name += len(delete_list)

total_after = SpeciesInfo.objects.count()

print("\n" + "=" * 80)
print(f"✅ 合并完成！")
print(f"   合并前: {total_before} 个物种")
print(f"   合并后: {total_after} 个物种")
print(f"   按拉丁名合并: {merged_count_latin} 个")
print(f"   按中文名合并: {merged_count_name} 个")
print(f"   共减少: {total_before - total_after} 个")
print("=" * 80)
