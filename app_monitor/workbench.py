"""Local GeoLibre frontend and static assets. No business or model API calls."""
import json
import mimetypes
import math
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_safe
from .workbench_basemaps import make_style, provider_config
from .gis_methods import METHODS


@require_safe
def page(request):
    response = render(request, 'workbench.html', {
        'geostudio_online': getattr(settings, 'GEOSTUDIO_REMOTE_COMPUTE', False),
        'analysis_labels': {m.native: m.name for m in METHODS if not m.raster},
    })
    response['Cache-Control'] = 'no-store'
    return response


@require_safe
@xframe_options_sameorigin
def engine(request, asset=''):
    root = Path(getattr(settings, 'GEOLIBRE_WEB_ROOT', settings.BASE_DIR / 'var/geolibre/dist')).resolve()
    name = asset or 'index.html'
    if '\\' in name or any(part.startswith('.') for part in name.split('/')):
        raise Http404
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise Http404
    if name == 'example-project.json':
        project = json.loads((settings.BASE_DIR / 'app_monitor/static/app_monitor/workbench/yellow-river.geolibre.json').read_text(encoding='utf-8'))
        project['basemapStyleUrl'] = reverse('workbench_engine') + 'basemap.json'
        response = HttpResponse(json.dumps(project, ensure_ascii=False), content_type='application/json; charset=utf-8')
        response['Cache-Control'] = 'no-store'
        return response
    if name == 'basemap.json':
        try:
            args = [float(request.GET.get(k, default)) for k, default in [('lng',113.58),('lat',34.96),('zoom',10),('width',1024),('height',768)]]
            if not all(math.isfinite(v) for v in args) or not (-180 <= args[0] <= 180 and -85 <= args[1] <= 85 and 0 <= args[2] <= 22 and 1 <= args[3] <= 8192 and 1 <= args[4] <= 8192):
                raise ValueError('无效的底图范围。')
            style = make_style(provider_config(settings.BASE_DIR), request.GET.get('kind','vector'), request.GET.get('labels','1') != '0', args[:2], *args[2:])
            response = HttpResponse(json.dumps(style, ensure_ascii=False), content_type='application/json; charset=utf-8')
        except (ValueError, TypeError):
            response = HttpResponse('底图配置不可用，请检查本地地图配置。', status=400)
        response['Cache-Control'] = 'no-store'
        return response
    if name == 'deployment.json':
        policy = json.loads((settings.BASE_DIR / 'integrations/geolibre/deployment.json').read_text(encoding='utf-8'))
        # Only this exact host may control the embedded map; never a wildcard.
        policy['sharing']['embedOrigins'] = [request.build_absolute_uri('/').rstrip('/')]
        response = HttpResponse(json.dumps(policy, ensure_ascii=False), content_type='application/json; charset=utf-8')
        response['Cache-Control'] = 'no-store'
        return response
    if not target.is_file():
        if name == 'index.html':
            return HttpResponse('地图工作台尚未准备好，请完成本地构建后重试。', status=503, content_type='text/plain; charset=utf-8')
        raise Http404
    if name == 'index.html':
        base = reverse('home')
        html = target.read_text(encoding='utf-8')
        styles = ''.join('<link rel="stylesheet" href="' + base + 'static/app_monitor/workbench/' + name + '.css?v=20261115-credit1">' for name in ['engine', 'background'])
        html = html.replace('</head>', styles + '</head>')
        response = HttpResponse(html)
        response['Cache-Control'] = 'no-cache'
        return response
    content_type = {'.js': 'application/javascript', '.mjs': 'application/javascript',
                    '.wasm': 'application/wasm', '.geojson': 'application/geo+json'}.get(target.suffix)
    response = FileResponse(target.open('rb'), content_type=content_type or mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
    response['Cache-Control'] = 'public, max-age=86400' if name.startswith('assets/') else 'no-cache'
    return response
