"""Platform-owned input/output bridge for GeoLibre's Whitebox runtime."""
import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from .workbench_sidecar import ensure_running

TOOL_ID = re.compile(r'^[a-zA-Z0-9_]{1,100}$')


def _local(request):
    return (request.get_host().split(':')[0] in {'127.0.0.1', 'localhost'} and
            request.META.get('REMOTE_ADDR') in {'127.0.0.1', '::1'})


def _call(path, payload=None):
    token = (Path(settings.BASE_DIR) / 'var/geolibre/sidecar.token').read_text(encoding='utf-8').strip()
    headers = {'X-GeoLibre-Token': token}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    with urlopen(Request('http://127.0.0.1:18765/' + path, data=body, headers=headers), timeout=30) as response:
        return json.load(response)


def _contains_path(value):
    if isinstance(value, str):
        return '/' in value or '\\' in value or '..' in value
    if isinstance(value, dict):
        return any(_contains_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_path(item) for item in value)
    return False


@require_POST
@csrf_protect
def whitebox_start(request):
    if not _local(request):
        raise Http404
    try:
        manifest = json.loads(request.POST.get('manifest', ''))
        tool_id = manifest['tool_id']
        parameters = manifest.get('parameters', {})
        inputs = manifest.get('inputs', [])
        if (not isinstance(tool_id, str) or not TOOL_ID.fullmatch(tool_id) or
                not isinstance(parameters, dict) or not isinstance(inputs, list) or len(inputs) > 12 or
                sum(file.size for file in request.FILES.values()) > 50_000_000):
            raise ValueError
        # Paths are generated below; model-provided paths must not reach the server.
        if _contains_path(parameters):
            raise ValueError
        if not ensure_running():
            return JsonResponse({'detail': '空间计算组件不可用。'}, status=503)
        tool = _call('whitebox/tools/' + tool_id)
        if tool.get('locked') or tool.get('available') is False:
            return JsonResponse({'detail': '该工具当前不可用。'}, status=400)
        input_names = {item.get('name') for item in tool.get('params', []) if item.get('io_role') == 'input'}
        supplied_inputs = {item.get('name') for item in inputs if isinstance(item, dict)}
        if any(name in parameters and name not in supplied_inputs for name in input_names):
            return JsonResponse({'detail': '请从当前工程中选择有效的输入图层。'}, status=400)
        supplied = {str(item['name']): str(item['kind']) for item in manifest.get('output_kinds', [])}
        folder = Path(settings.BASE_DIR) / 'var/geolibre/jobs' / uuid.uuid4().hex
        folder.mkdir(parents=True)
        input_paths = {}
        for index, entry in enumerate(inputs):
            name, key, kind = entry['name'], entry['file'], entry['kind']
            if not TOOL_ID.fullmatch(name) or key not in request.FILES or kind not in {'vector_in', 'raster_in', 'lidar_in'}:
                raise ValueError
            suffix = {'vector_in': '.geojson', 'raster_in': '.tif', 'lidar_in': '.las'}[kind]
            target = folder / ('input-' + str(index) + suffix)
            with target.open('wb') as stream:
                for chunk in request.FILES[key].chunks():
                    stream.write(chunk)
            input_paths.setdefault(name, []).append(str(target))
        for name, paths in input_paths.items():
            parameters[name] = ','.join(paths)
        artifacts = []
        for param in tool.get('params', []):
            name = str(param.get('name', ''))
            kind = supplied.get(name, '')
            if kind not in {'raster_out', 'vector_out', 'file_out'} or not TOOL_ID.fullmatch(name):
                continue
            suffix = {'raster_out': '.tif', 'vector_out': '.geojson', 'file_out': '.json'}[kind]
            path = folder / ('output-' + str(len(artifacts)) + suffix)
            parameters[name] = str(path)
            artifacts.append({'name': name, 'path': str(path), 'kind': kind})
        job = _call('whitebox/run', {'tool_id': tool_id, 'parameters': parameters, 'tool': tool})
        job_id = str(uuid.UUID(job['id']))
        (folder / 'job.json').write_text(json.dumps({'job_id': job_id, 'artifacts': artifacts}), encoding='utf-8')
        return JsonResponse({'job': job, 'directory': folder.name, 'artifacts': artifacts})
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'detail': '分析参数或输入数据不正确。'}, status=400)
    except (OSError, HTTPError, URLError, TimeoutError):
        return JsonResponse({'detail': '空间计算任务启动失败。'}, status=503)


@require_GET
def whitebox_artifact(request, directory, index):
    if not _local(request) or not re.fullmatch(r'[0-9a-f]{32}', directory):
        raise Http404
    folder = (Path(settings.BASE_DIR) / 'var/geolibre/jobs' / directory).resolve()
    try:
        data = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
        path = Path(data['artifacts'][index]['path'])
        if path.is_symlink() or path.resolve().parent != folder or not path.is_file():
            raise Http404
        if data['artifacts'][index]['kind'] == 'raster_out':
            # Whitebox often writes striped TIFFs; GeoLibre's browser renderer
            # needs a tiled COG. Conversion happens inside the packaged runtime.
            cog = folder / (path.stem + '.cog.tif')
            if not cog.is_file():
                python = Path(settings.BASE_DIR) / ('var/geolibre/venv/Scripts/python.exe' if os.name == 'nt' else 'var/geolibre/venv/bin/python')
                temp = folder / (uuid.uuid4().hex + '.tif')
                env = os.environ.copy()
                env.pop('PROJ_DATA', None)
                env.pop('PROJ_LIB', None)
                try:
                    subprocess.run([str(python), '-c',
                        'import sys; from rasterio.shutil import copy; copy(sys.argv[1], sys.argv[2], driver="COG", compress="DEFLATE")',
                        str(path), str(temp)], check=True, timeout=120, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    temp.replace(cog)
                finally:
                    temp.unlink(missing_ok=True)
            path = cog
        return FileResponse(path.open('rb'), content_type='application/octet-stream')
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        raise Http404
