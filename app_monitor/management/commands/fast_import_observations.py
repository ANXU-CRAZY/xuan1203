import csv
from collections import OrderedDict
from datetime import datetime

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app_monitor.models import ObservationRecord, SpeciesInfo, WetlandZone
from app_monitor.protection import normalize_protection_level


HEADER_ALIASES = {
    '中文名': 'name_cn',
    '种': 'name_cn',
    '物种': 'name_cn',
    'species_name': 'name_cn',
    'name_cn': 'name_cn',
    'loc': 'zone',
    '地址': 'zone',
    '点位': 'zone',
    '监测点位': 'zone',
    'zone': 'zone',
    'date': 'date',
    '日期': 'date',
    '观测日期': 'date',
    'observation_time': 'date',
    'abundance': 'count',
    '数量': 'count',
    'count': 'count',
    'latin_name': 'latin_name',
    'species': 'latin_name',
    '学名': 'latin_name',
    '拉丁名': 'latin_name',
    'order_name': 'order_name',
    '目': 'order_name',
    'family_name': 'family_name',
    '科': 'family_name',
    'protection_level': 'protection_level',
    '保护级别': 'protection_level',
    '保护等级': 'protection_level',
    'x': 'x',
    '经度': 'x',
    'longitude': 'x',
    'lng': 'x',
    'y': 'y',
    '纬度': 'y',
    'latitude': 'y',
    'lat': 'y',
}


def compact_text(value):
    return str(value or '').strip().lstrip('\ufeff')


def parse_date(value):
    text = compact_text(value)
    if not text:
        return None
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace('/', '-')).date()
    except ValueError:
        return None


def parse_int(value, default=1):
    text = compact_text(value).replace(',', '')
    if not text:
        return default
    try:
        return max(0, int(float(text)))
    except ValueError:
        return default


def parse_float(value):
    text = compact_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def clean_zone_name(value):
    text = compact_text(value)
    if '_点位' in text:
        text = text.split('_点位', 1)[0]
    return text.strip()


def coord_key(value):
    return round(value, 6) if value is not None else None


class Command(BaseCommand):
    help = 'Fast bulk import observation CSV files without using the slow admin import page.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', help='CSV file path to import.')
        parser.add_argument('--encoding', default='utf-8-sig', help='CSV encoding, default: utf-8-sig.')
        parser.add_argument('--batch-size', type=int, default=5000, help='Bulk insert batch size.')
        parser.add_argument('--replace', action='store_true', help='Delete all existing observation records before import.')
        parser.add_argument('--uploader', default='', help='Uploader username. Defaults to first superuser, then first user.')
        parser.add_argument('--dry-run', action='store_true', help='Parse and report only, do not write to database.')
        parser.add_argument('--skip-cache-refresh', action='store_true', help='Do not rebuild the home map cache after import.')

    def handle(self, *args, **options):
        csv_path = options['csv_path']
        encoding = options['encoding']
        batch_size = options['batch_size']

        try:
            rows = self.read_rows(csv_path, encoding)
        except UnicodeDecodeError:
            rows = self.read_rows(csv_path, 'gb18030')
            encoding = 'gb18030'
        except FileNotFoundError as exc:
            raise CommandError(f'CSV file not found: {csv_path}') from exc

        parsed = self.parse_rows(rows)
        if not parsed['records']:
            raise CommandError(f'No valid observation rows found. Invalid rows: {parsed["invalid"]}')

        self.stdout.write(f'CSV encoding: {encoding}')
        self.stdout.write(f'Raw rows: {parsed["raw"]}')
        self.stdout.write(f'Valid unique observation keys: {len(parsed["records"])}')
        self.stdout.write(f'Invalid rows skipped: {parsed["invalid"]}')
        self.stdout.write(f'Species to ensure: {len(parsed["species"])}')
        self.stdout.write(f'Zones to ensure: {len(parsed["zones"])}')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry run only. No database changes were made.'))
            return

        uploader = self.get_uploader(options['uploader'])

        with transaction.atomic():
            if options['replace']:
                deleted, _ = ObservationRecord.objects.all().delete()
                self.stdout.write(self.style.WARNING(f'Existing observation records deleted: {deleted}'))

            species_map = self.ensure_species(parsed['species'], batch_size)
            zone_map = self.ensure_zones(parsed['zones'], batch_size)
            created = self.create_observations(parsed['records'], species_map, zone_map, uploader, batch_size)

        self.stdout.write(self.style.SUCCESS(f'Fast import completed. Observation records created: {created}'))
        if not options['skip_cache_refresh']:
            self.stdout.write('Refreshing home map cache...')
            call_command('refresh_map_observation_cache', batch_size=batch_size)

    def read_rows(self, csv_path, encoding):
        with open(csv_path, newline='', encoding=encoding) as fp:
            reader = csv.DictReader(fp)
            if not reader.fieldnames:
                raise CommandError('CSV has no header row.')
            normalized_headers = [HEADER_ALIASES.get(compact_text(h), compact_text(h)) for h in reader.fieldnames]
            rows = []
            for raw in reader:
                row = {}
                for original, normalized in zip(reader.fieldnames, normalized_headers):
                    row[normalized] = raw.get(original)
                rows.append(row)
            return rows

    def parse_rows(self, rows):
        species = OrderedDict()
        zones = OrderedDict()
        records = OrderedDict()
        last_zone = ''
        last_x = None
        last_y = None
        invalid = 0

        for row in rows:
            name_cn = compact_text(row.get('name_cn'))
            zone_name = clean_zone_name(row.get('zone'))
            if zone_name:
                last_zone = zone_name
            elif last_zone:
                zone_name = last_zone

            x = parse_float(row.get('x'))
            y = parse_float(row.get('y'))
            if x is not None and y is not None:
                last_x, last_y = x, y
            elif zone_name == last_zone and last_x is not None and last_y is not None:
                x, y = last_x, last_y

            date = parse_date(row.get('date'))
            count = parse_int(row.get('count'))

            if not name_cn or not zone_name or not date:
                invalid += 1
                continue

            species.setdefault(name_cn, {
                'name_cn': name_cn,
                'name_latin': compact_text(row.get('latin_name')),
                'order': compact_text(row.get('order_name')),
                'family': compact_text(row.get('family_name')),
                'protection_level': normalize_protection_level(row.get('protection_level')),
            })
            if x is not None and y is not None:
                zones[zone_name] = {'name': zone_name, 'longitude': x, 'latitude': y}
            else:
                zones.setdefault(zone_name, {'name': zone_name, 'longitude': None, 'latitude': None})

            key = (name_cn, zone_name, date, coord_key(x), coord_key(y))
            if key in records:
                records[key]['count'] += count
            else:
                records[key] = {
                    'name_cn': name_cn,
                    'zone': zone_name,
                    'date': date,
                    'count': count,
                    'longitude': x,
                    'latitude': y,
                }

        return {'raw': len(rows), 'invalid': invalid, 'species': species, 'zones': zones, 'records': records}

    def get_uploader(self, username):
        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                raise CommandError(f'Uploader not found: {username}')
            return user
        return User.objects.filter(is_superuser=True).first() or User.objects.first()

    def ensure_species(self, species_data, batch_size):
        existing = {s.name_cn: s for s in SpeciesInfo.objects.filter(name_cn__in=species_data.keys())}
        to_create = []
        to_update = []

        for name, data in species_data.items():
            obj = existing.get(name)
            if obj:
                changed = False
                for field in ('name_latin', 'order', 'family', 'protection_level'):
                    value = data[field]
                    if value and getattr(obj, field) != value:
                        setattr(obj, field, value)
                        changed = True
                if changed:
                    to_update.append(obj)
            else:
                to_create.append(SpeciesInfo(**data))

        if to_create:
            SpeciesInfo.objects.bulk_create(to_create, batch_size=batch_size, ignore_conflicts=True)
        if to_update:
            SpeciesInfo.objects.bulk_update(to_update, ['name_latin', 'order', 'family', 'protection_level'], batch_size=batch_size)

        return {s.name_cn: s.id for s in SpeciesInfo.objects.filter(name_cn__in=species_data.keys()).only('id', 'name_cn')}

    def ensure_zones(self, zone_data, batch_size):
        existing = {z.name: z for z in WetlandZone.objects.filter(name__in=zone_data.keys())}
        to_create = []
        to_update = []

        for name, data in zone_data.items():
            lon = data['longitude']
            lat = data['latitude']
            point = Point(lon, lat, srid=4326) if lon is not None and lat is not None else None
            obj = existing.get(name)
            if obj:
                if point and (obj.longitude != lon or obj.latitude != lat):
                    obj.longitude = lon
                    obj.latitude = lat
                    obj.location = point
                    to_update.append(obj)
            else:
                to_create.append(WetlandZone(name=name, longitude=lon, latitude=lat, location=point))

        if to_create:
            WetlandZone.objects.bulk_create(to_create, batch_size=batch_size, ignore_conflicts=True)
        if to_update:
            WetlandZone.objects.bulk_update(to_update, ['longitude', 'latitude', 'location'], batch_size=batch_size)

        return {z.name: z.id for z in WetlandZone.objects.filter(name__in=zone_data.keys()).only('id', 'name')}

    def create_observations(self, record_data, species_map, zone_map, uploader, batch_size):
        existing_keys = {
            (species_id, zone_id, observation_time, coord_key(longitude), coord_key(latitude))
            for species_id, zone_id, observation_time, longitude, latitude in
            ObservationRecord.objects
            .filter(species_id__in=species_map.values(), zone_id__in=zone_map.values())
            .values_list('species_id', 'zone_id', 'observation_time', 'longitude', 'latitude')
        }
        to_create = []

        for record in record_data.values():
            species_id = species_map.get(record['name_cn'])
            zone_id = zone_map.get(record['zone'])
            if not species_id or not zone_id:
                continue
            longitude = record.get('longitude')
            latitude = record.get('latitude')
            key = (species_id, zone_id, record['date'], coord_key(longitude), coord_key(latitude))
            if key in existing_keys:
                continue
            existing_keys.add(key)
            point = Point(longitude, latitude, srid=4326) if longitude is not None and latitude is not None else None
            to_create.append(ObservationRecord(
                species_id=species_id,
                zone_id=zone_id,
                observation_time=record['date'],
                count=record['count'],
                longitude=longitude,
                latitude=latitude,
                location=point,
                status='approved',
                uploader=uploader,
            ))

        if to_create:
            ObservationRecord.objects.bulk_create(to_create, batch_size=batch_size)
        return len(to_create)
