from pathlib import Path

import shapefile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


WGS84_PRJ = '''GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]'''


class Command(BaseCommand):
    help = 'Exports the SuperMap observation view as a stable EPSG:4326 Shapefile layer.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default='data/supermap/YellowRiverEcology_observation_points',
            help='Shapefile base path without extension, relative to the project root by default.',
        )
        parser.add_argument('--limit', type=int, help='Optional maximum number of points.')

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError('SuperMap point export requires PostgreSQL/PostGIS.')

        limit = options['limit']
        if limit is not None and limit < 1:
            raise CommandError('--limit must be greater than zero.')

        output_base = Path(options['output']).resolve()
        output_base.parent.mkdir(parents=True, exist_ok=True)
        sql = '''
            SELECT source_record_id, observation_time::text, observation_count, status,
                   species_id, species_name, species_latin, species_protection,
                   zone_id, zone_name, transect_name, longitude, latitude
            FROM supermap_observation_points
            ORDER BY observation_time DESC, source_record_id
        '''
        params = []
        if limit is not None:
            sql += ' LIMIT %s'
            params.append(limit)

        writer = shapefile.Writer(str(output_base), shapeType=shapefile.POINT, encoding='utf-8')
        writer.autoBalance = 1
        writer.field('SOURCE_ID', 'N', size=12, decimal=0)
        writer.field('OBS_DATE', 'C', size=10)
        writer.field('OBS_COUNT', 'N', size=10, decimal=0)
        writer.field('STATUS', 'C', size=10)
        writer.field('SPECIES_ID', 'N', size=12, decimal=0)
        writer.field('SPECIES_CN', 'C', size=100)
        writer.field('SPECIES_LAT', 'C', size=100)
        writer.field('PROTECTION', 'C', size=30)
        writer.field('ZONE_ID', 'N', size=12, decimal=0)
        writer.field('ZONE_NAME', 'C', size=100)
        writer.field('TRANSECT', 'C', size=100)

        count = 0
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                while rows := cursor.fetchmany(2_000):
                    for row in rows:
                        (
                            source_id, observation_date, observation_count, status,
                            species_id, species_name, species_latin, protection,
                            zone_id, zone_name, transect, longitude, latitude,
                        ) = row
                        writer.point(longitude, latitude)
                        writer.record(
                            source_id, observation_date, observation_count, status or '',
                            species_id, species_name or '', species_latin or '', protection or '',
                            zone_id, zone_name or '', transect or '',
                        )
                        count += 1
        finally:
            writer.close()

        output_base.with_suffix('.prj').write_text(WGS84_PRJ, encoding='ascii')
        output_base.with_suffix('.cpg').write_text('UTF-8\n', encoding='ascii')
        self.stdout.write(
            self.style.SUCCESS(
                f'Exported {count} EPSG:4326 points to {output_base.with_suffix(".shp")}'
            )
        )
