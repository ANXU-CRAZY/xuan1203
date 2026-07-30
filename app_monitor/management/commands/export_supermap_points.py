import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = 'Exports the SuperMap observation view as an EPSG:4326 GeoJSON point layer.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default='data/supermap/YellowRiverEcology_observation_points.geojson',
            help='GeoJSON output path, relative to the project root by default.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Optional maximum number of points, for a lightweight demonstration layer.',
        )

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError('SuperMap point export requires PostgreSQL/PostGIS.')

        limit = options['limit']
        if limit is not None and limit < 1:
            raise CommandError('--limit must be greater than zero.')

        output_path = Path(options['output']).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sql = '''
            SELECT
                source_record_id,
                observation_time::text,
                observation_count,
                status,
                species_id,
                species_name,
                species_latin,
                species_protection,
                zone_id,
                zone_name,
                transect_name,
                longitude,
                latitude
            FROM supermap_observation_points
            ORDER BY observation_time DESC, source_record_id
        '''
        params = []
        if limit is not None:
            sql += ' LIMIT %s'
            params.append(limit)

        properties = (
            'source_record_id',
            'observation_time',
            'observation_count',
            'status',
            'species_id',
            'species_name',
            'species_latin',
            'species_protection',
            'zone_id',
            'zone_name',
            'transect_name',
        )

        count = 0
        with connection.cursor() as cursor, output_path.open('w', encoding='utf-8') as output:
            cursor.execute(sql, params)
            output.write('{"type":"FeatureCollection","name":"supermap_observation_points",'
                         '"crs":{"type":"name","properties":{"name":"EPSG:4326"}},'
                         '"features":[\n')
            first = True
            while rows := cursor.fetchmany(2_000):
                for row in rows:
                    feature = {
                        'type': 'Feature',
                        'geometry': {
                            'type': 'Point',
                            'coordinates': [row[-2], row[-1]],
                        },
                        'properties': dict(zip(properties, row[:-2])),
                    }
                    if not first:
                        output.write(',\n')
                    json.dump(feature, output, ensure_ascii=False, separators=(',', ':'))
                    first = False
                    count += 1
            output.write('\n]}\n')

        self.stdout.write(
            self.style.SUCCESS(
                f'Exported {count} EPSG:4326 observation points to {output_path}'
            )
        )
