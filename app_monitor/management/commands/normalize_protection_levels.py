from django.core.management.base import BaseCommand

from app_monitor.models import SpeciesInfo
from app_monitor.protection import normalize_protection_level


class Command(BaseCommand):
    help = 'Normalize legacy species protection levels to canonical Chinese labels.'

    def handle(self, *args, **options):
        updated = 0
        examples = []

        for species in SpeciesInfo.objects.only('id', 'name_cn', 'protection_level'):
            old_value = species.protection_level or ''
            new_value = normalize_protection_level(old_value)
            if new_value != old_value:
                SpeciesInfo.objects.filter(pk=species.pk).update(protection_level=new_value)
                updated += 1
                if len(examples) < 12:
                    examples.append(f'{species.name_cn}: {old_value or "-"} -> {new_value or "-"}')

        self.stdout.write(self.style.SUCCESS(f'Protection levels normalized: {updated} species updated.'))
        for example in examples:
            self.stdout.write(f'  {example}')
