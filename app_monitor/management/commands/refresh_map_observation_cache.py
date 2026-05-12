from django.core.management.base import BaseCommand
from django.db import transaction

from app_monitor.models import MapObservationCache, MonitoringRoute, ObservationRecord
from app_monitor.protection import normalize_protection_level


def get_record_coordinates(record):
    if record.location:
        return record.location.x, record.location.y
    if record.longitude is not None and record.latitude is not None:
        return record.longitude, record.latitude
    if record.zone and record.zone.longitude is not None and record.zone.latitude is not None:
        return record.zone.longitude, record.zone.latitude
    return None, None


def get_transect_name(zone_name, route_names):
    if not zone_name:
        return ''
    for route_name in route_names:
        if zone_name in route_name or route_name in zone_name:
            return route_name
    return ''


class Command(BaseCommand):
    help = 'Rebuild the lightweight observation cache used by the home map.'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=5000)
        parser.add_argument('--status', default='approved', help='Status to cache. Use "all" to cache all records.')

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        status = options['status']

        queryset = ObservationRecord.objects.select_related('species', 'zone').order_by('id')
        if status != 'all':
            queryset = queryset.filter(status=status)

        route_names = list(MonitoringRoute.objects.values_list('name', flat=True))
        cache_rows = []
        skipped = 0

        for record in queryset.iterator(chunk_size=batch_size):
            lng, lat = get_record_coordinates(record)
            if lng is None or lat is None:
                skipped += 1
                continue

            species = record.species
            zone = record.zone
            image_url = ''
            if record.image and str(record.image) not in ('', 'False', 'None'):
                image_url = record.image.url

            cache_rows.append(MapObservationCache(
                record_id=record.id,
                observation_time=record.observation_time,
                count=record.count or 1,
                status=record.status,
                species_id_cached=species.id if species else 0,
                species_name=species.name_cn if species else '',
                species_latin=species.name_latin if species else '',
                species_protection=normalize_protection_level(species.protection_level if species else ''),
                zone_id_cached=zone.id if zone else 0,
                zone_name=zone.name if zone else '',
                transect_name=get_transect_name(zone.name if zone else '', route_names),
                longitude=lng,
                latitude=lat,
                image_url=image_url,
                description=record.description or '',
            ))

        with transaction.atomic():
            MapObservationCache.objects.all().delete()
            if cache_rows:
                MapObservationCache.objects.bulk_create(cache_rows, batch_size=batch_size)

        self.stdout.write(self.style.SUCCESS(
            f'Map observation cache rebuilt: {len(cache_rows)} rows, skipped without coordinates: {skipped}.'
        ))
