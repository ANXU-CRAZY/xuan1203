"""Serve GeoStudio beneath its own prefix without altering the main platform."""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.geostudio_settings')
from django.core.wsgi import get_wsgi_application

application_inner = get_wsgi_application()


def application(environ, start_response):
    path = environ.get('PATH_INFO', '')
    if path == '/geostudio' or path.startswith('/geostudio/'):
        environ['SCRIPT_NAME'] = '/geostudio'
        environ['PATH_INFO'] = path[len('/geostudio'):] or '/'
    return application_inner(environ, start_response)
