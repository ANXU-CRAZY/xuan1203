"""Settings for the independently mounted ARK GeoStudio service."""
from .settings import *  # noqa: F403

ALLOWED_HOSTS = ['arklab-geoai.org.cn', 'www.arklab-geoai.org.cn', '127.0.0.1', 'localhost']
CSRF_TRUSTED_ORIGINS = ['https://arklab-geoai.org.cn', 'https://www.arklab-geoai.org.cn']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_NAME = 'geostudio_sessionid'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
ROOT_URLCONF = 'config.geostudio_urls'
STATIC_URL = '/geostudio/static/'
GEOSTUDIO_REMOTE_COMPUTE = True
