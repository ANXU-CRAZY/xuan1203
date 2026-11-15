"""Loopback-only transport to the local, token-protected GeoLibre sidecar."""
from pathlib import Path
import os
import secrets
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_protect
from .workbench_access import is_local, may_compute, owner_id
import json
import re

_START_LOCK = threading.Lock()


def ensure_running():
    """Start the bundled calculation component on demand, inside the platform."""
    base = Path(settings.BASE_DIR) / 'var/geolibre'
    python = base / ('venv/Scripts/python.exe' if os.name == 'nt' else 'venv/bin/python')
    if not python.is_file():
        return False
    def ready():
        try:
            with urlopen('http://127.0.0.1:18765/health', timeout=1):
                return True
        except (OSError, URLError):
            return False
    if ready():
        return True
    with _START_LOCK:
        if ready():
            return True
        token_file = base / 'sidecar.token'
        if not token_file.exists():
            token_file.write_text(secrets.token_urlsafe(32), encoding='utf-8')
        env = os.environ.copy()
        env.update(GEOLIBRE_SIDECAR_TOKEN=token_file.read_text(encoding='utf-8').strip(),
                   GEOLIBRE_CONVERSION_PYTHON=str(python), WBW_EXTERNAL_PYTHON=str(python))
        subprocess.Popen([str(python), '-m', 'uvicorn', 'geolibre_server.app.main:app',
                          '--host', '127.0.0.1', '--port', '18765'], cwd=settings.BASE_DIR,
                         env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if ready():
                return True
            time.sleep(.15)
    return False


@csrf_protect
def proxy(request, path):
    if not may_compute(request):
        raise Http404
    if not is_local(request):
        # Never expose raw filesystem, conversion or execution endpoints online.
        allowed = (request.method == 'GET' and (
            path in {'health', 'algorithms', 'whitebox/status', 'whitebox/tools',
                     'raster/status', 'vector/status', 'conversion/status'} or
            re.fullmatch(r'whitebox/tools/[A-Za-z0-9_]{1,100}', path)))
        job = re.fullmatch(r'whitebox/jobs/([0-9a-fA-F-]{36})', path)
        if request.method == 'GET' and job:
            try:
                import uuid
                job_id = str(uuid.UUID(job.group(1)))
                index = Path(settings.BASE_DIR) / 'var/geolibre/job-index' / (job_id + '.json')
                allowed = json.loads(index.read_text(encoding='utf-8')).get('owner') == owner_id(request)
            except (ValueError, OSError, json.JSONDecodeError):
                allowed = False
        if not allowed:
            raise Http404
    if request.method not in {'GET', 'POST'} or not (
        path in {'health', 'algorithms'} or path.startswith(('raster/', 'vector/', 'whitebox/', 'conversion/jobs/'))
    ) or '..' in path.split('/'):
        raise Http404
    try:
        if not ensure_running():
            return JsonResponse({'detail': '空间计算组件尚未安装或启动失败。'}, status=503)
        token = (Path(settings.BASE_DIR) / 'var/geolibre/sidecar.token').read_text(encoding='utf-8').strip()
        target = 'http://127.0.0.1:18765/' + path
        if request.META.get('QUERY_STRING'):
            target += '?' + request.META['QUERY_STRING']
        headers = {'X-GeoLibre-Token': token}
        if request.content_type:
            headers['Content-Type'] = request.META.get('CONTENT_TYPE', request.content_type)
        upstream_request = Request(target, data=request.body if request.method == 'POST' else None,
                                   headers=headers, method=request.method)
        try:
            upstream = urlopen(upstream_request, timeout=90)
        except HTTPError as error:
            upstream = error
        with upstream:
            response = HttpResponse(upstream.read(), status=upstream.status,
                                    content_type=upstream.headers.get('Content-Type', 'application/json'))
        response['Cache-Control'] = 'no-store'
        return response
    except (OSError, URLError, TimeoutError):
        return JsonResponse({'detail': '本地空间计算服务不可用。'}, status=503)
