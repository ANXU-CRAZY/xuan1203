import json
from pathlib import Path

from django.core.management.base import BaseCommand

from app_monitor.models import SpeciesInfo


class Command(BaseCommand):
    help = 'Sync species names, taxonomy, protection levels, and habits from bundled metadata.'

    def handle(self, *args, **options):
        data_path = Path(__file__).resolve().parents[2] / 'fixtures' / 'species_metadata.json'
        if not data_path.exists():
            self.stdout.write(self.style.WARNING(f'Species metadata not found: {data_path}'))
            return

        species_data = json.loads(data_path.read_text(encoding='utf-8'))
        metadata = {
            item['name_cn'].strip(): item
            for item in species_data
            if item.get('name_cn')
        }

        updated = 0
        created = 0
        unmatched = []

        for name, item in metadata.items():
            species = SpeciesInfo.objects.filter(name_cn=name).first()
            if not species:
                species = SpeciesInfo(name_cn=name)
                created += 1

            changed = False
            for field in ('name_latin', 'order', 'family', 'protection_level', 'distribution_habit'):
                new_value = (item.get(field) or '').strip()
                if new_value and getattr(species, field) != new_value:
                    setattr(species, field, new_value)
                    changed = True

            if changed or species.pk is None:
                species.save()
                updated += 1

        for species in SpeciesInfo.objects.all():
            normalized = self._normalize_legacy_level(species.protection_level)
            if normalized and normalized != species.protection_level:
                species.protection_level = normalized
                species.save(update_fields=['protection_level'])
                updated += 1

            if species.name_cn.strip() not in metadata and not species.protection_level:
                unmatched.append(species.name_cn)

        self.stdout.write(self.style.SUCCESS(
            f'Species metadata synced: updated={updated}, created={created}'
        ))
        if unmatched:
            preview = ', '.join(unmatched[:30])
            suffix = '...' if len(unmatched) > 30 else ''
            self.stdout.write(self.style.WARNING(
                f'Species without bundled metadata: {len(unmatched)} ({preview}{suffix})'
            ))

    def _normalize_legacy_level(self, level):
        text = (level or '').strip()
        if text in ('Ⅰ', 'I', '国家一级', '一级'):
            return '国家一级重点保护野生动物'
        if text in ('Ⅱ', 'II', '国家二级', '二级'):
            return '国家二级重点保护野生动物'
        if text in ('三有', '三有动物'):
            return '国家三有保护动物'
        return text
