"""Run only the monitoring contract tests on a NEW disposable PostGIS DB."""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.test.utils import get_runner

# Never reuse or delete a developer's existing test database.
connection.settings_dict['TEST']['NAME'] = 'test_monitoring_' + uuid.uuid4().hex
runner = get_runner(settings)(verbosity=2, interactive=False)
raise SystemExit(bool(runner.run_tests(sys.argv[1:] or ['app_monitor.test_monitoring'])))
