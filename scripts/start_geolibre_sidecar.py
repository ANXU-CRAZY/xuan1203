"""Start the optional local analysis runtime without exposing its token."""
import os
from pathlib import Path
import secrets
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'var/geolibre'
PYTHON = BASE / 'venv/Scripts/python.exe'
TOKEN = BASE / 'sidecar.token'

if not PYTHON.is_file():
    raise SystemExit('请先创建 var/geolibre/venv 并安装 GeoLibre 计算依赖。')
try:
    with urllib.request.urlopen('http://127.0.0.1:18765/health', timeout=2):
        print('GeoLibre 本地计算服务已运行。')
        raise SystemExit(0)
except OSError:
    pass
BASE.mkdir(parents=True, exist_ok=True)
if not TOKEN.is_file():
    TOKEN.write_text(secrets.token_urlsafe(32), encoding='utf-8')
env = os.environ.copy()
env['GEOLIBRE_SIDECAR_TOKEN'] = TOKEN.read_text(encoding='utf-8').strip()
env['GEOLIBRE_CONVERSION_PYTHON'] = str(PYTHON)
env['WBW_EXTERNAL_PYTHON'] = str(PYTHON)
subprocess.Popen([str(PYTHON), '-m', 'uvicorn', 'geolibre_server.app.main:app',
                  '--host', '127.0.0.1', '--port', '18765'], cwd=ROOT, env=env,
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
print('正在启动 GeoLibre 本地计算服务。')
