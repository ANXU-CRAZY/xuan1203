import os, sys, re
from collections import defaultdict

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()

from app_monitor.models import SpeciesInfo, ObservationRecord, SpeciesImage

output = []

def log(msg):
    output.append(msg)
    print(msg)

total_before = SpeciesInfo.objects.count()
log(f"合并前物种总数: {total_before}")

# 按拉丁名找重复
groups = defaultdict(list)
for s in SpeciesInfo.objects.exclude(name_latin='').exclude(name_latin__isnull=True):
    key = s.name_latin.strip().lower()
    if key:
        groups[key].append(s)
latin_dups = {k: v for k, v in groups.items() if len(v) > 1}
log(f"按拉丁名找到 {len(latin_dups)} 组重复")

for latin, group in latin_dups.items():
    # 选择保留的：有图、有描述、名字短的
    keep = max(group, key=lambda s: (
        1 if s.images.exists() else 0,
        1 if s.distribution_habit and s.distribution_habit != '暂无详细习性数据' else 0,
        -len(s.name_cn or ''),
        -s.id
    ))
    for s in group:
        if s.id == keep.id:
            continue
        obs = ObservationRecord.objects.filter(species=s).update(species=keep)
        img = SpeciesImage.objects.filter(species=s).update(species=keep)
        if not keep.distribution_habit and s.distribution_habit:
            keep.distribution_habit = s.distribution_habit
            keep.save()
        log(f"  [{latin}] 删除 {s.name_cn}(ID:{s.id}) -> 保留 {keep.name_cn}(ID:{keep.id})")
        s.delete()

# 按中文名找重复（去掉"鸟"后缀）
groups2 = defaultdict(list)
for s in SpeciesInfo.objects.all():
    key = re.sub(r"[（）()\[\]【】\s·,，、/\\-]", "", (s.name_cn or '').strip())
    key = key.rstrip('鸟').strip()
    if key:
        groups2[key].append(s)
name_dups = {k: v for k, v in groups2.items() if len(v) > 1}
log(f"按中文名找到 {len(name_dups)} 组重复")

for key, group in name_dups.items():
    keep = max(group, key=lambda s: (
        1 if s.images.exists() else 0,
        1 if s.distribution_habit and s.distribution_habit != '暂无详细习性数据' else 0,
        -len(s.name_cn or ''),
        -s.id
    ))
    for s in group:
        if s.id == keep.id:
            continue
        obs = ObservationRecord.objects.filter(species=s).update(species=keep)
        img = SpeciesImage.objects.filter(species=s).update(species=keep)
        log(f"  [{key}] 删除 {s.name_cn}(ID:{s.id}) -> 保留 {keep.name_cn}(ID:{keep.id})")
        s.delete()

total_after = SpeciesInfo.objects.count()
log(f"合并后物种总数: {total_after} (减少 {total_before - total_after})")

# 写入文件
with open('dedupe_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))
