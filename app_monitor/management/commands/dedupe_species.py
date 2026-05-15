"""
合并重复物种：基于拉丁名 + 中文名相似度合并
用法: python manage.py dedupe_species
"""
import re
from collections import defaultdict
from django.core.management.base import BaseCommand
from app_monitor.models import SpeciesInfo, ObservationRecord, SpeciesImage


class Command(BaseCommand):
    help = '合并重复物种记录'

    def handle(self, *args, **options):
        self.stdout.write("=" * 80)
        self.stdout.write("自动合并重复物种")
        self.stdout.write("=" * 80)

        total_before = SpeciesInfo.objects.count()
        self.stdout.write(f"\n合并前物种总数: {total_before}")

        # 1. 按拉丁名合并
        latin_dups = self._find_duplicates_by_latin()
        self.stdout.write(f"\n按拉丁名找到 {len(latin_dups)} 组重复，开始合并...\n")
        merged_latin = 0
        for latin, group in latin_dups.items():
            keep = self._choose_keep(group)
            delete_list = [s for s in group if s.id != keep.id]
            self.stdout.write(f"  [{latin}] 保留: {keep.name_cn} (ID:{keep.id})")
            self._merge(keep, delete_list)
            merged_latin += len(delete_list)

        # 2. 按中文名合并
        name_dups = self._find_duplicates_by_name()
        self.stdout.write(f"\n按中文名找到 {len(name_dups)} 组重复，开始合并...\n")
        merged_name = 0
        for key, group in name_dups.items():
            keep = self._choose_keep(group)
            delete_list = [s for s in group if s.id != keep.id]
            if delete_list:
                self.stdout.write(f"  [{key}] 保留: {keep.name_cn} (ID:{keep.id})")
                self._merge(keep, delete_list)
                merged_name += len(delete_list)

        total_after = SpeciesInfo.objects.count()
        self.stdout.write(f"\n合并完成！ {total_before} -> {total_after} (减少 {total_before - total_after})")

    def _find_duplicates_by_latin(self):
        groups = defaultdict(list)
        for s in SpeciesInfo.objects.exclude(name_latin='').exclude(name_latin__isnull=True):
            key = s.name_latin.strip().lower()
            if key:
                groups[key].append(s)
        return {k: v for k, v in groups.items() if len(v) > 1}

    def _find_duplicates_by_name(self):
        groups = defaultdict(list)
        for s in SpeciesInfo.objects.all():
            key = re.sub(r"[（）()\[\]【】\s·,，、/\\-]", "", (s.name_cn or '').strip())
            key = key.rstrip('鸟').strip()
            if key:
                groups[key].append(s)
        return {k: v for k, v in groups.items() if len(v) > 1}

    def _choose_keep(self, species_list):
        def score(s):
            return (
                1 if s.cover_image else 0,
                1 if s.distribution_habit and s.distribution_habit != '暂无详细习性数据' else 0,
                1 if s.images.exists() else 0,
                -len(s.name_cn or ''),
                -s.id
            )
        return max(species_list, key=score)

    def _merge(self, keep, delete_list):
        for s in delete_list:
            if s.id == keep.id:
                continue
            obs = ObservationRecord.objects.filter(species=s).update(species=keep)
            img = SpeciesImage.objects.filter(species=s).update(species=keep)
            if not keep.cover_image and s.cover_image:
                keep.cover_image = s.cover_image
                keep.save()
            if (not keep.distribution_habit or keep.distribution_habit == '暂无详细习性数据') and s.distribution_habit and s.distribution_habit != '暂无详细习性数据':
                keep.distribution_habit = s.distribution_habit
                keep.save()
            if not keep.protection_level and s.protection_level:
                keep.protection_level = s.protection_level
                keep.save()
            self.stdout.write(f"    删除: {s.name_cn} (ID:{s.id}) 迁移{obs}条观测,{img}张图")
            s.delete()
