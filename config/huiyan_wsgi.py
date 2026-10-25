"""Same Django settings, with only Huiyan routes in the inference process.

The original bird-recognition URL configuration imports PyTorch. Avoid loading
that separate model stack in the bounded ONNX worker. The main WSGI entry point
and its full URL configuration remain unchanged.
"""

import os

from django.conf import settings
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
settings.ROOT_URLCONF = 'config.huiyan_urls'
application = get_wsgi_application()
