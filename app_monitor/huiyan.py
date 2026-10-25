"""Django adapter for the bundled Fangzhou Huiyan identifier.

The original project is an offline HTTP application.  This module keeps its
inference implementation in :mod:`huiyan_runtime.engine` while exposing the
same capabilities through the current Django process and same-origin URLs.
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
import urllib.parse

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from PIL import Image, ImageOps

from .huiyan_runtime import engine
from .huiyan_runtime.xlsx import Sheet, build


MAX_BODY_BYTES = 200 * 1024 * 1024


def page(request: HttpRequest) -> HttpResponse:
    return render(request, "app_monitor/huiyan.html", {"huiyan_tdt_key": settings.TDT_KEY})


def _json_body(request: HttpRequest) -> dict:
    # Read the bounded stream explicitly: large TIFF/base64 payloads exceed
    # Django's default 2.5 MB request.body limit even before Pillow sees them.
    if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_BODY_BYTES:
        raise ValueError("请求体大小非法")
    body = request.read(MAX_BODY_BYTES + 1)
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("请求体大小非法")
    if not body:
        raise ValueError("请求体为空")
    value = json.loads(body.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("请求格式非法")
    return value


def _error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _ready_error() -> JsonResponse | None:
    engine.ensure_loaded()
    if not engine.SESSION["ready"]:
        return _error(engine.SESSION["error"] or "尚未就绪", 503)
    return None


@require_GET
def status(request: HttpRequest) -> JsonResponse:
    # Initialize on a Huiyan request, never when Django starts the dashboard.
    engine.ensure_loaded()
    lib = engine.SESSION.get("lib") or {}
    return JsonResponse(
        {
            "ready": bool(engine.SESSION["ready"]),
            "error": engine.SESSION.get("metadata_error"),
            "model_error": engine.SESSION.get("error") if not engine.SESSION["ready"] else None,
            "species": lib.get("species", []),
            "groups": lib.get("groups", []),
            "orders": lib.get("orders", []),
            "scenes": engine.SESSION.get("scenes", {}),
            "categories": engine.SESSION.get("cats", {}),
            "slots": engine.SLOTS,
            "max_targets": engine.MAX_TARGETS,
        })


def _targets(payload: dict):
    targets_raw = payload.get("targets") or []
    category = payload.get("category") or ""
    if category:
        return engine.resolve_category(category), category
    if not targets_raw:
        scene = payload.get("scene")
        if scene and scene in engine.SESSION["scenes"]:
            targets_raw = engine.SESSION["scenes"][scene]["classes"]
    return engine.resolve_targets(targets_raw), ""


@csrf_exempt
@require_POST
def detect(request: HttpRequest) -> JsonResponse:
    ready = _ready_error()
    if ready:
        return ready
    try:
        payload = _json_body(request)
        targets, category = _targets(payload)
        phrase = (payload.get("phrase") or "").strip()
        aux = engine.resolve_phrase(phrase) if phrase else []
        if not targets:
            return _error("请先选择目标物种")
        if len(targets) > engine.MAX_TARGETS:
            return _error(f"最多选择 {engine.MAX_TARGETS} 个目标物种")
        image = engine._decode_image(payload.get("image", ""))
        if image is None:
            return _error("图片解析失败")

        classes = [target[0] for target in targets]
        zh_map = {target[0].lower(): target[1] for target in targets}
        aux_from = len(targets) if aux else None
        feats = engine.build_txt_feats_with_aux(targets, aux) if aux else engine.build_txt_feats(targets)
        started = time.perf_counter()
        results = engine.detect(
            image,
            classes,
            feats,
            conf_thr=float(payload.get("conf", 0.05)),
            iou_thr=float(payload.get("iou", 0.5)),
            zh_map=zh_map,
            aux_from=aux_from,
            aux_count=len(aux),
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        marked = engine.draw(image, results, zh_map, show_en=bool(payload.get("show_en")))
        crops = []
        for idx, result in enumerate(results):
            crop = engine.crop_data_url(image, result["box"])
            if crop:
                crops.append({
                    "idx": idx,
                    "en": result["en"],
                    "zh": zh_map.get(result["en"].lower(), ""),
                    "img": crop,
                })
        return JsonResponse({
            "ok": True,
            "count": len(results),
            "elapsed_ms": elapsed_ms,
            "size": list(image.size),
            "results": results,
            "image": engine.to_data_url(marked),
            "crops": crops,
            "targets": [{"en": t[0], "zh": t[1]} for t in targets],
            "category": category,
        })
    except Exception as exc:  # noqa: BLE001
        engine.log(f"检测失败 {type(exc).__name__}: {exc}")
        return _error(f"{type(exc).__name__}: {exc}", 500)


@csrf_exempt
@require_POST
def detect_batch(request: HttpRequest) -> JsonResponse:
    ready = _ready_error()
    if ready:
        return ready
    try:
        payload = _json_body(request)
        targets, _ = _targets(payload)
        if not targets:
            return _error("请先选择目标物种")
        images = payload.get("images") or []
        if not images:
            return _error("没有待处理图片")
        classes = [target[0] for target in targets]
        zh_map = {target[0].lower(): target[1] for target in targets}
        feats = engine.build_txt_feats(targets)
        conf = float(payload.get("conf", 0.05))
        rows = []
        started = time.perf_counter()
        for idx, item in enumerate(images):
            name = item.get("name") or f"image_{idx + 1}"
            try:
                image = engine._decode_image(item.get("image", ""))
                if image is None:
                    raise ValueError("图片解析失败")
                results = engine.detect(image, classes, feats, conf_thr=conf, zh_map=zh_map)
                rows.append({
                    "name": name,
                    "error": "",
                    "count": len(results),
                    "results": results,
                    "image": engine.to_data_url(engine.draw(image, results, zh_map), 900),
                    "size": list(image.size),
                })
            except Exception as exc:  # noqa: BLE001
                rows.append({"name": name, "error": f"{type(exc).__name__}: {exc}", "results": [], "image": "", "size": [0, 0]})
        total = sum(len(row["results"]) for row in rows)
        hits = sum(1 for row in rows if row["results"])
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        return JsonResponse({
            "ok": True,
            "rows": rows,
            "summary": {"images": len(rows), "with_detection": hits, "detections": total, "elapsed_ms": elapsed_ms, "avg_ms": round(elapsed_ms / max(1, len(rows)))},
            "targets": [{"en": t[0], "zh": t[1]} for t in targets],
        })
    except Exception as exc:  # noqa: BLE001
        engine.log(f"批量失败 {type(exc).__name__}: {exc}")
        return _error(f"{type(exc).__name__}: {exc}", 500)


@csrf_exempt
@require_POST
def convert(request: HttpRequest) -> JsonResponse:
    try:
        payload = _json_body(request)
        raw = payload.get("image", "")
        if "," in raw:
            raw = raw.split(",", 1)[1]
        image = Image.open(io.BytesIO(base64.b64decode(raw)))
        image.load()
        image = ImageOps.exif_transpose(image) or image
        image = image.convert("RGB")
        max_side = 2400
        if max(image.size) > max_side:
            scale = max_side / max(image.size)
            image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
        return JsonResponse({"ok": True, "name": payload.get("name", "image"), "size": list(image.size), "image": engine.to_data_url(image, 2400), "converted": True})
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}", 500)


@csrf_exempt
@require_POST
def relabel(request: HttpRequest) -> JsonResponse:
    try:
        payload = _json_body(request)
        image = engine._decode_image(payload.get("image", ""))
        if image is None:
            return _error("图片解析失败")
        results = payload.get("results") or []
        zh_map = {result.get("en", "").lower(): result.get("zh", "") for result in results if result.get("en")}
        marked = engine.draw(image, results, zh_map, show_en=bool(payload.get("show_en")))
        crops = []
        for idx, result in enumerate(results):
            if len(result.get("box") or []) != 4:
                continue
            crop = engine.crop_data_url(image, result["box"])
            if crop:
                crops.append({"idx": idx, "en": result.get("en", ""), "zh": result.get("zh", "") or zh_map.get(result.get("en", "").lower(), ""), "img": crop})
        return JsonResponse({"ok": True, "image": engine.to_data_url(marked), "crops": crops})
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}", 500)


@csrf_exempt
@require_POST
def export_xlsx(request: HttpRequest) -> HttpResponse:
    try:
        payload = _json_body(request)
        rows = payload.get("rows") or []
        summary = payload.get("summary") or []
        meta = payload.get("meta") or {}
        detail = Sheet("识别明细", [["序号", "文件名", "物种", "英文名", "置信度", "纬度 Lat", "经度 Lng", "影像x1", "影像y1", "影像x2", "影像y2", "图像宽", "图像高"]] + [
            [i, row.get("file", ""), row.get("zh", ""), row.get("en", ""), ("percent", float(row.get("score", 0))), row.get("lat", "") if row.get("lat") not in (None, "") else "", row.get("lng", "") if row.get("lng") not in (None, "") else "", int(round(float(row.get("x1", 0)))), int(round(float(row.get("y1", 0)))), int(round(float(row.get("x2", 0)))), int(round(float(row.get("y2", 0)))), int(row.get("img_w", 0)) if row.get("img_w") else "", int(row.get("img_h", 0)) if row.get("img_h") else ""]
            for i, row in enumerate(rows, 1)
        ])
        total = sum(int(row.get("count", 0)) for row in summary)
        stat = Sheet("物种统计", [["物种", "英文名", "数量", "占比"]] + [[row.get("zh", ""), row.get("en", ""), ("int", int(row.get("count", 0))), ("percent", int(row.get("count", 0)) / total if total else 0)] for row in summary])
        info = Sheet("说明", [["项目", "内容"], ["导出时间", meta.get("at", "")], ["目标词表", meta.get("targets", "")], ["识别图片数", ("int", int(meta.get("images", 0)))], ["检出目标总数", ("int", int(meta.get("detections", 0)))], ["涉及物种类数", ("int", len(summary))], ["置信度阈值", meta.get("conf", "")], ["生成工具", "方舟慧眼 · 物种识别器（YOLO-World + ONNX Runtime）"]])
        response = HttpResponse(build([detail, stat, info], title="方舟慧眼识别报告"), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="huiyan-report.xlsx"'
        return response
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}", 500)


@require_GET
def geosearch(request: HttpRequest) -> JsonResponse:
    keyword = request.GET.get("q", "").strip()[:100]
    if not keyword:
        return _error("请输入地名")
    query = {"keyWord": keyword, "level": 12, "mapBound": "73,18,135,54", "queryType": 1, "start": 0, "count": 5}
    params = urllib.parse.urlencode({"postStr": json.dumps(query, ensure_ascii=False), "type": "query", "tk": settings.TDT_KEY})
    return HttpResponseRedirect("https://api.tianditu.gov.cn/v2/search?" + params)



@require_GET
def tile(request: HttpRequest, tile_path: str = "") -> HttpResponse:
    match = re.fullmatch(r"/(\d+)/(\d+)/(\d+)\.png", "/" + tile_path.lstrip("/"))
    if match:
        z, x, y = (int(value) for value in match.groups())
    else:
        try:
            z, x, y = (int(request.GET.get(key, "0")) for key in ("z", "x", "y"))
        except ValueError:
            return _error("地图坐标非法")
    if not (0 <= z <= 18 and 0 <= x < 2**z and 0 <= y < 2**z):
        return _error("地图缩放级别非法")
    layer = request.GET.get("layer", "vec")
    if layer not in ("vec", "cva", "img", "cia"):
        return _error("地图图层非法")
    params = urllib.parse.urlencode({"SERVICE": "WMTS", "REQUEST": "GetTile", "VERSION": "1.0.0", "LAYER": layer, "STYLE": "default", "TILEMATRIXSET": "w", "FORMAT": "tiles", "TILEMATRIX": z, "TILEROW": y, "TILECOL": x, "tk": settings.TDT_KEY})
    # The existing project key is a browser key. Server-side proxy requests
    # are rejected by Tianditu; let the browser follow the public tile URL.
    return HttpResponseRedirect(f"https://t{(x+y)%8}.tianditu.gov.cn/{layer}_w/wmts?{params}")
