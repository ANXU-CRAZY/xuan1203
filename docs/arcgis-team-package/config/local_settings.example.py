"""Machine-specific settings. Copy this file to config/local_settings.py.

Do not commit the copied file. It contains the database password of the
developer who owns this computer.
"""

LOCAL_DATABASE_OVERRIDES = {
    'NAME': 'yellow_river_arcgis',
    'USER': 'postgres',
    'PASSWORD': 'replace-with-your-own-postgresql-password',
    'HOST': '127.0.0.1',
    'PORT': '5432',
}

LOCAL_CACHE_LOCATION = 'yellow-river-arcgis-cache'
