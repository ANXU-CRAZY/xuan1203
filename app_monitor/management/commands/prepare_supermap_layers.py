from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = 'Creates the read-only PostGIS view consumed by SuperMap iServer.'

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError('SuperMap layer preparation requires PostgreSQL/PostGIS.')

        with connection.cursor() as cursor:
            cursor.execute(
                '''
                CREATE OR REPLACE VIEW supermap_observation_points AS
                SELECT
                    record_id AS source_record_id,
                    observation_time,
                    count AS observation_count,
                    status,
                    species_id_cached AS species_id,
                    species_name,
                    species_latin,
                    species_protection,
                    zone_id_cached AS zone_id,
                    zone_name,
                    transect_name,
                    image_url,
                    description,
                    longitude,
                    latitude,
                    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geometry(Point, 4326) AS geom
                FROM app_monitor_mapobservationcache
                WHERE longitude BETWEEN -180 AND 180
                  AND latitude BETWEEN -90 AND 90
                '''
            )
            cursor.execute(
                'SELECT COUNT(*), COALESCE(MIN(ST_SRID(geom)), 0) FROM supermap_observation_points'
            )
            record_count, srid = cursor.fetchone()

        self.stdout.write(
            self.style.SUCCESS(
                f'SuperMap view ready: supermap_observation_points ({record_count} records, EPSG:{srid}).'
            )
        )
