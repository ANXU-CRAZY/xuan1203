from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from app_monitor.models import SpeciesImage, SpeciesInfo


class Command(BaseCommand):
    help = 'Create SpeciesImage records from files in media/species/gallery.'

    def handle(self, *args, **options):
        gallery_dir = Path(settings.MEDIA_ROOT) / 'species' / 'gallery'
        if not gallery_dir.exists():
            self.stdout.write(self.style.WARNING(f'Gallery directory not found: {gallery_dir}'))
            return

        image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
        created = 0
        skipped = 0
        missing_species = set()

        for path in sorted(gallery_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in image_exts:
                continue

            species_name = path.stem
            if '_' in species_name:
                species_name = species_name.rsplit('_', 1)[0]

            species = SpeciesInfo.objects.filter(name_cn=species_name).first()
            if not species:
                missing_species.add(species_name)
                skipped += 1
                continue

            relative_path = f'species/gallery/{path.name}'
            existing = SpeciesImage.objects.filter(species=species, image=relative_path).first()
            if existing:
                skipped += 1
                continue

            is_first = not SpeciesImage.objects.filter(species=species, is_featured=True).exists()
            SpeciesImage.objects.create(
                species=species,
                image=relative_path,
                caption=f'{species.name_cn} 图库图片',
                source='manual',
                source_author='本地图库',
                is_featured=is_first,
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f'Species gallery synced: created={created}, skipped={skipped}'))
        if missing_species:
            preview = ', '.join(sorted(missing_species)[:20])
            self.stdout.write(self.style.WARNING(f'Species not found for {len(missing_species)} file group(s): {preview}'))
