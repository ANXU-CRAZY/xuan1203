"""Same-origin adapter for the independent, single-image SAM 2 workbench.

Never import its model code into Django or the bird identifier. The packaged
Windows application (or an externally managed source service) owns inference.
"""

from contextlib import contextmanager
import csv
import http.client
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from urllib.parse import urlsplit

from django.conf import settings
from django.core import signing
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.template.loader import render_to_string
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin


COOKIE = "huiyan_land_session"
SALT = "huiyan-land-workspace-v1"
MAX_BODY = 200 * 1024 * 1024
MAX_RESPONSE = 256 * 1024 * 1024
LEASE_SECONDS = 20 * 60
GET_PATHS = {
    "", "api/status", "api/examples", "api/obj_stats", "image", "overlay",
    "mask", "objmap", "download", "crop", "example", "example_thumb",
    "auto_overlay", "logo.png",
}
POST_PATHS = {"upload", "api/config"} | {
    "api/" + action for action in (
        "add_object", "predict", "text_detect", "text_prompt", "del_point",
        "del_object", "toggle_object", "lock_object", "rename", "set_color",
        "set_coords", "fill_coords", "clear_objects", "undo", "auto",
        "auto_params", "assign_auto", "switch_model", "batch", "video",
        "export_csv", "get_config", "save_config", "stats_reset", "history_clear",
    )
}
ASSET_ROOTS = sorted({path.split("/")[0] for path in GET_PATHS | POST_PATHS if path})
ROOT_URLS = re.compile(r'''(["'`])/(%s)(?=[/?#"'`])''' % "|".join(re.escape(x) for x in ASSET_ROOTS))


class ServiceError(Exception):
    pass


def runtime_dir():
    path = Path(getattr(settings, "HUIYAN_LAND_STATE_DIR", settings.BASE_DIR / "var" / "land-segmentation"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def workspace_lock(timeout=10):
    """OS lock serializes threads AND WSGI workers, including model switches."""
    handle = (runtime_dir() / "workspace.lock").open("a+b")
    handle.seek(0, os.SEEK_END)
    if not handle.tell():
        handle.write(b"\0")
        handle.flush()
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while not locked:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise ServiceError("分割工作台正在处理其他操作，请稍后重试。")
                time.sleep(0.1)
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def service_address():
    address = urlsplit(getattr(settings, "HUIYAN_LAND_SERVICE_URL", "http://127.0.0.1:8013"))
    if (address.scheme != "http" or address.hostname not in {"127.0.0.1", "localhost", "::1"}
            or address.username or address.password or address.path not in {"", "/"}
            or address.query or address.fragment):
        raise ServiceError("地物分割服务必须配置为本机独立 HTTP 地址。")
    return address.hostname, address.port or 80


def upstream(path, *, method="GET", body=None, content_type="application/json", timeout=180):
    host, port = service_address()
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request(method, "/" + path, body=body, headers={"Content-Type": content_type})
        response = connection.getresponse()
        if response.getheader("Content-Length") and int(response.getheader("Content-Length")) > MAX_RESPONSE:
            raise ServiceError("分割结果过大，请减少目标或缩小图片后重试。")
        data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ServiceError("分割结果过大，请减少目标或缩小图片后重试。")
        if 300 <= response.status < 400:
            raise ServiceError("分割服务返回了不支持的重定向。")
        return response.status, dict(response.getheaders()), data
    finally:
        connection.close()


def ensure_service():
    """Called under the workspace lock. Never replace a service on a busy port."""
    try:
        status, _, data = upstream("api/status", timeout=3)
    except (ConnectionRefusedError, ConnectionResetError):
        status = None
    except OSError as exc:
        raise ServiceError("地物分割服务暂未响应，请稍后重新打开工作台。") from exc
    if status is not None:
        try:
            info = json.loads(data)
            valid = status == 200 and {"has_image", "objects", "model", "device"} <= info.keys()
        except (ValueError, AttributeError):
            valid = False
        if not valid:
            raise ServiceError("地物分割端口已被其他服务占用，请检查配置；未更换端口。")
        return
    executable = Path(getattr(settings, "HUIYAN_LAND_EXECUTABLE", ""))
    if not getattr(settings, "HUIYAN_LAND_AUTOSTART", False) or os.name != "nt" or not executable.is_file():
        raise ServiceError("地物分割服务尚未启动。请运行配置的轻量版服务后点击重试。")
    _, port = service_address()
    model = getattr(settings, "HUIYAN_LAND_MODEL", "tiny")
    device = getattr(settings, "HUIYAN_LAND_DEVICE", "cpu")
    if model not in {"tiny", "small", "base_plus", "large"} or device not in {"cpu", "cuda", "auto"}:
        raise ServiceError("地物分割模型或设备配置无效。")
    command = [str(executable), "--port", str(port), "--model", model, "--device", device, "--no-browser"]
    with (runtime_dir() / "service.log").open("ab") as log:
        process = subprocess.Popen(command, cwd=executable.parent, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    (runtime_dir() / "service.pid").write_text(str(process.pid), encoding="ascii")
    for _ in range(40):
        if process.poll() is not None:
            break
        try:
            status, _, data = upstream("api/status", timeout=1)
            info = json.loads(data)
            if status == 200 and {"has_image", "objects", "model", "device"} <= info.keys():
                return
        except (OSError, ValueError, AttributeError, http.client.HTTPException):
            pass
        time.sleep(0.5)
    raise ServiceError("地物分割服务正在启动或启动失败，请稍后重试；日志位于 var/land-segmentation/service.log。")


def _owner(request):
    try:
        return signing.loads(request.COOKIES.get(COOKIE, ""), salt=SALT, max_age=86400)
    except signing.BadSignature:
        return None


def _cookie(response, token, request):
    response.set_cookie(COOKIE, signing.dumps(token, salt=SALT), max_age=86400,
                        httponly=True, secure=request.is_secure(), samesite="Lax")
    response["Cache-Control"] = "no-store, private"
    return response


def _read_lease():
    try:
        return json.loads((runtime_dir() / "lease.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_lease(lease):
    path = runtime_dir() / "lease.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(lease), encoding="utf-8")
    temporary.replace(path)


@require_GET
def choice_page(request):
    return render(request, "app_monitor/recognition_choice.html")


@require_GET
def page(request):
    token = _owner(request) or secrets.token_urlsafe(32)
    return _cookie(render(request, "app_monitor/land_segmentation.html"), token, request)


@require_POST
def release(request):
    token = _owner(request)
    try:
        with workspace_lock():
            lease = _read_lease()
            if token and lease.get("owner") == token:
                if request.POST.get("preserve") == "1":
                    # Browser back/close frees the single workspace. A reload
                    # by this owner can resume until another browser claims it.
                    _write_lease({"resume_owner": token, "initialized": lease.get("initialized", False), "expires": 0})
                else:
                    _write_lease({})
    except ServiceError as exc:
        return JsonResponse({"error": str(exc)}, status=423)
    return JsonResponse({"ok": True})


def _workbench_html(data, request):
    """Adapt transport and colours; retain native layout, controls and prompts."""
    base = reverse("huiyan_land_proxy", kwargs={"upstream_path": ""})
    text = ROOT_URLS.sub(lambda match: match[1] + base + match[2], data.decode("utf-8"))
    text = re.sub(r"<title>.*?</title>", "<title>方舟慧眼 · 地物识别器</title>", text, count=1, flags=re.S)
    # Replace just the native canvas location block, keeping its panel and all
    # other workbench controls. Install before native initialization starts.
    map_start = text.find('<div class="gpsmap">')
    map_end = text.find('</section>', map_start) if map_start >= 0 else -1
    if map_start >= 0 and map_end >= 0:
        text = text[:map_start] + render_to_string('app_monitor/land_map.html') + '\n</div>\n' + text[map_end:]
        text = text.replace('// ---------- 初始化 ----------',
                            '// ---------- 初始化 ----------\nwindow.installLandMap();', 1)
    # The native UI posts raw bytes/JSON. Supply Django's CSRF header without
    # exempting the proxy or altering any upstream event handler or control.
    config = json.dumps({"base": base, "csrf": get_token(request),
                         "tdtKey": getattr(settings, "TDT_KEY", "")}).replace("<", "\\u003c")
    transport = """<script>(function(){const cfg=__WORKBENCH_OPTIONS__,send=window.fetch.bind(window);
window.LAND_MAP_CONFIG={tdtKey:cfg.tdtKey};
try{let theme='light',saved=localStorage.getItem('huiyanTheme');try{saved=JSON.parse(saved);}catch(_){}
if(saved==='light'||saved==='dark')theme=saved;localStorage.setItem('sam2theme',theme);}catch(_){}
document.addEventListener('DOMContentLoaded',function(){
const remember=function(){try{localStorage.setItem('huiyanTheme',JSON.stringify(document.body.classList.contains('light')?'light':'dark'));}catch(_){}};
new MutationObserver(remember).observe(document.body,{attributes:true,attributeFilter:['class']});});
window.fetch=function(input,options){const opts=options||{},url=new URL(input instanceof Request?input.url:input,location.href);
const method=String(opts.method||(input instanceof Request?input.method:'GET')).toUpperCase();
if(url.origin===location.origin&&url.pathname.startsWith(cfg.base)&&!['GET','HEAD','OPTIONS'].includes(method)){
const headers=new Headers(opts.headers||(input instanceof Request?input.headers:undefined));headers.set('X-CSRFToken',cfg.csrf);
return send(input,Object.assign({},opts,{headers:headers}));}return send(input,opts);};})();</script>""".replace("__WORKBENCH_OPTIONS__", config)
    assets = ('<link rel="stylesheet" href="/static/app_monitor/huiyan/leaflet/leaflet.css">'
              '<link rel="stylesheet" href="/static/app_monitor/huiyan/land-theme.css?v=20261108-2">'
              '<script src="/static/app_monitor/huiyan/leaflet/leaflet.js"></script>'
              '<script src="/static/app_monitor/huiyan/land-map.js?v=20261108-1"></script>')
    return text.replace("</head>", assets + transport + "</head>", 1)


def _csv_with_coordinates(data):
    """Use object fields: the supplied executable reverses its CSV lat/lon."""
    payload = json.loads(data)
    source = payload.get("csv", "")
    rows = list(csv.reader(io.StringIO(source.lstrip("\ufeff"))))
    if not rows or not {"编号", "经度", "纬度"} <= set(rows[0]):
        return data
    status, _, content = upstream("api/status", timeout=5)
    if status != 200:
        raise ServiceError("无法核对导出坐标，请重试。")
    objects = {str(obj["id"]): obj for obj in json.loads(content).get("objects", [])}
    id_col, lon_col, lat_col = (rows[0].index(key) for key in ("编号", "经度", "纬度"))
    for row in rows[1:]:
        obj = objects.get(row[id_col])
        if obj:
            row[lon_col] = obj.get("lon") if obj.get("lon") is not None else ""
            row[lat_col] = obj.get("lat") if obj.get("lat") is not None else ""
    output = io.StringIO(newline="")
    csv.writer(output).writerows(rows)
    payload["csv"] = "\ufeff" + output.getvalue()
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


@require_http_methods(["GET", "POST"])
@xframe_options_sameorigin
def proxy(request, upstream_path=""):
    allowed = GET_PATHS if request.method == "GET" else POST_PATHS
    if upstream_path not in allowed:
        return JsonResponse({"error": "没有这个分割接口。"}, status=404)
    if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_BODY:
        return JsonResponse({"error": "文件过大，上限为 200 MB。"}, status=413)
    token = _owner(request)
    if not token and (request.method != "GET" or upstream_path):
        return JsonResponse({"error": "请先打开地物识别工作台。"}, status=403)
    token = token or secrets.token_urlsafe(32)
    try:
        body = request.read(MAX_BODY + 1) if request.method == "POST" else None
        if body is not None and len(body) > MAX_BODY:
            return JsonResponse({"error": "文件过大，上限为 200 MB。"}, status=413)
        payload = None
        if request.method == "POST" and upstream_path.startswith("api/"):
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                return JsonResponse({"error": "分割参数不是有效的 JSON。"}, status=400)
            if not isinstance(payload, dict):
                return JsonResponse({"error": "分割参数必须是 JSON 对象。"}, status=400)
            action = upstream_path.split("/")[1]
            valid_actions = {action} if action != "config" else {"get_config", "save_config"}
            if payload.get("action", action) not in valid_actions:
                return JsonResponse({"error": "分割操作与接口不一致。"}, status=400)
            if action == "switch_model" and payload.get("model") not in {"tiny", "small", "base_plus", "large"}:
                return JsonResponse({"error": "请选择有效的分割模型。"}, status=400)
            items = payload.get("items", [])
            if action == "batch" and (not isinstance(items, list) or not all(isinstance(item, dict) for item in items)):
                return JsonResponse({"error": "批量图片参数无效。"}, status=400)
            names = [item.get("name", "") for item in items] if action == "batch" else []
            if action == "video":
                names.append(payload.get("name", ""))
            if any(not isinstance(name, str) or not name or name in {".", ".."} or any(c in name for c in '/\\:\x00') for name in names):
                return JsonResponse({"error": "文件名不能包含路径。"}, status=400)
            if action == "batch" and payload.get("format") not in {"overlay", "cutout", "mask"}:
                return JsonResponse({"error": "请选择有效的批量导出格式。"}, status=400)
        if upstream_path in {"example", "example_thumb"}:
            name = request.GET.get("name", "")
            if not name or name in {".", ".."} or any(c in name for c in '/\\:\x00'):
                return JsonResponse({"error": "无效的例图文件名。"}, status=400)
        with workspace_lock(timeout=180):
            lease = _read_lease()
            if lease.get("owner") != token and lease.get("expires", 0) > time.time():
                raise ServiceError("分割工作台正在被另一浏览器使用，请等待对方退出后重试。")
            if lease.get("owner") != token:
                initialized = lease.get("initialized", False) if lease.get("resume_owner") == token else False
                lease = {"owner": token, "initialized": initialized}
            if upstream_path == "":
                ensure_service()
            if not lease.get("initialized") and upstream_path in {"upload", "example", "api/video", "api/batch"}:
                # Native counters/history survive an upload. Reset them before
                # a new owner loads anything so previous filenames never leak.
                for action in ("clear_objects", "stats_reset", "history_clear"):
                    reset_status, _, _ = upstream("api/" + action, method="POST", body=json.dumps({"action": action}).encode())
                    if reset_status != 200:
                        raise ServiceError("无法重置上一工作会话，请重新打开工作台。")
            # No browser may observe the preceding owner's image, masks,
            # coordinates, history, or host-level saved configuration.
            if upstream_path in {"api/config", "api/get_config", "api/save_config"}:
                response = JsonResponse({"ok": True, "config": {}})
            elif not lease.get("initialized") and upstream_path == "api/status":
                status, _, data = upstream("api/status", timeout=5)
                if status != 200:
                    raise ServiceError("地物分割服务状态异常，请重新打开工作台。")
                info = json.loads(data)
                clean = {key: info[key] for key in ("model", "device", "auto_params") if key in info}
                response = JsonResponse({**clean, "has_image": False, "image_name": "", "w": 0, "h": 0,
                                         "objects": [], "auto_count": 0, "busy": False, "gps": None,
                                         "stats": {}, "species": [], "history": []})
            elif not lease.get("initialized") and upstream_path not in {"", "upload", "example", "logo.png", "example_thumb", "api/examples", "api/switch_model", "api/auto_params"}:
                return JsonResponse({"error": "请先载入图片。"}, status=409)
            else:
                # Query parameters remain encoded; paths come only from the
                # allowlist. Never forward client cookies, auth, or redirects.
                path = upstream_path
                if request.META.get("QUERY_STRING"):
                    path += "?" + request.META["QUERY_STRING"]
                status, headers, data = upstream(path, method=request.method, body=body,
                                                 content_type=request.content_type or "application/octet-stream")
                if status == 200 and upstream_path == "api/export_csv":
                    data = _csv_with_coordinates(data)
                response = HttpResponse(_workbench_html(data, request) if not upstream_path and status == 200 else data,
                                        status=status, content_type=headers.get("Content-Type", "application/octet-stream"))
                if headers.get("Content-Disposition"):
                    response["Content-Disposition"] = headers["Content-Disposition"]
                if status == 200 and upstream_path in {"upload", "example", "api/video", "api/batch"}:
                    lease["initialized"] = True
            lease["expires"] = time.time() + LEASE_SECONDS
            _write_lease(lease)
            return _cookie(response, token, request)
    except (ServiceError, OSError, ValueError, http.client.HTTPException) as exc:
        message = str(exc) if isinstance(exc, ServiceError) else "地物分割服务暂时无法连接，请重新打开工作台。"
        if not upstream_path:
            response = render(request, "app_monitor/land_unavailable.html", {"message": message}, status=503)
        else:
            response = JsonResponse({"error": message}, status=423 if isinstance(exc, ServiceError) else 503)
        response["Cache-Control"] = "no-store, private"
        return response
