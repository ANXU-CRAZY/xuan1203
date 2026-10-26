"""
方舟慧眼 · 物种识别器
Local Wildlife Identifier — 基于开源 YOLO-World 的离线物种识别工具

架构（全部经本机实测确定）：
1. 单个动态 ONNX 模型：导出时保留 BNContrastiveHead 的动态点积，
   把文本嵌入做成图输入 → 一个模型服务任意词表
   （官方导出路径会 fuse 文本特征，导致词表固化）
2. 固定 12 槽位：模型结构要求固定 nc，用户自选 2-12 个目标物种，
   不足的槽位用与所有真实嵌入正交的向量填充
3. 本地物种嵌入库：175 种中国常见兽鸟的 CLIP 文本嵌入（0.16MB），
   无需在 exe 里携带 338MB 的 CLIP 文本塔
4. fp16 权重：体积减半，精度无损
5. onnxruntime 直推：exe 体积可控在 ~60MB
6. 自带 Web UI：本地 HTTP 服务 + 浏览器，图片不离开本机

作者备注：官方「物种之眼」286 种微调权重未公开，本工具使用其基座
YOLO-World（腾讯 AI Lab，GPL-3.0）。
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import numpy as np
except Exception as exc:  # pragma: no cover - depends on the host runtime
    np = None  # type: ignore[assignment]
    NUMPY_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    NUMPY_IMPORT_ERROR = None

# ONNX Runtime is imported only on the first model request.  Some hosts do not
# have the native runtime installed; the dashboard should still be able to
# render and report that condition in Chinese.
ort = None
ORT_IMPORT_ERROR = None
from PIL import Image, ImageDraw, ImageFont

try:  # 同目录模块（PyInstaller 打包后为内置模块）
    from xlsx import Sheet, build
except ImportError:  # pragma: no cover
    from .xlsx import Sheet, build

SLOTS = 12  # 模型固定槽位数
MAX_TARGETS = 12  # 用户最多可选目标物种数


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    here = Path(__file__).resolve().parent
    for cand in (here, here.parent):
        if (cand / "model" / "model.onnx").exists():
            return cand
    return here


RES = resource_dir()
MODEL_DIR = RES / "model"
MODEL_PATH = MODEL_DIR / "model.onnx"
EMB_PATH = MODEL_DIR / "species_emb.npz"
LIB_PATH = MODEL_DIR / "species_lib.json"
SCENES_DIR = MODEL_DIR / "scenes"
CAT_PATH = MODEL_DIR / "categories.json"
CAT_EMB_PATH = MODEL_DIR / "category_emb.npz"


def find_web_dir() -> Path:
    if getattr(sys, "frozen", False):
        return RES / "web"
    here = Path(__file__).resolve().parent
    for cand in (here / "web", here.parent / "app" / "web", RES / "web"):
        if (cand / "index.html").exists():
            return cand
    return here / "web"


ASSET_DIR = find_web_dir()
# The legacy standalone handler remains in this source for provenance, but
# Django serves the copied template and static files through its own routes.
HTML = ""

SESSION: dict = {
    "sess": None,
    "emb": None,        # (N, 512) fp16
    "index": {},        # en(lower) -> row index
    "lib": {},          # 物种清单
    "scenes": {},       # 预设场景
    "cats": {},         # 大类专栏：{名称: {desc, words:[{en,zh}]}}
    "cat_emb": {},      # 大类专栏词嵌入：{英文提示词: 512维}
    "metadata_ready": False,
    "metadata_error": None,
    "ready": False,
    "error": None,
    "lock": threading.Lock(),
    "pad_vec": None,    # 正交 padding 向量
}

_LOAD_LOCK = threading.Lock()
_METADATA_LOCK = threading.Lock()

BOX = (52, 120, 246)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_metadata() -> bool:
    """Load the small species catalog without importing the native runtime."""
    if SESSION["metadata_ready"]:
        return True
    if SESSION["metadata_error"]:
        return False
    try:
        if np is None:
            raise RuntimeError(f"numpy 不可用: {NUMPY_IMPORT_ERROR}")
        for p in (EMB_PATH, LIB_PATH):
            if not p.exists():
                raise FileNotFoundError(f"资源缺失: {p.name}")
        z = np.load(EMB_PATH)
        emb = z["emb"].astype(np.float32)  # (N, 512)
        SESSION["emb"] = emb

        lib = json.loads(LIB_PATH.read_text(encoding="utf-8"))
        # 物种库未显式给出 groups / orders 时，从物种字段派生
        # （前端树形列表「类群 → 目/科 → 物种」依赖这两个键）
        if not lib.get("groups"):
            lib["groups"] = list(dict.fromkeys(
                s.get("group") for s in lib["species"] if s.get("group")))
        if not lib.get("orders"):
            lib["orders"] = list(dict.fromkeys(
                s.get("group2") for s in lib["species"] if s.get("group2")))
        SESSION["lib"] = lib
        SESSION["index"] = {
            s["en"].lower(): i for i, s in enumerate(lib["species"])
        }

        # 预设场景（若存在）
        sp = MODEL_DIR / "presets.json"
        if sp.exists():
            SESSION["scenes"] = {
                k: v
                for k, v in json.loads(sp.read_text(encoding="utf-8")).items()
                if not k.startswith("_")
            }

        # 大类专栏（若存在）：泛称词表 + 独立嵌入库
        # 大类专栏的提示词（如 "water bird"）不在物种库中，
        # 因此单独用 CLIP 文本塔编码后存成 npz，运行时不携带 CLIP。
        cp = MODEL_DIR / "categories.json"
        if cp.exists():
            SESSION["cats"] = {
                k: v
                for k, v in json.loads(cp.read_text(encoding="utf-8")).items()
                if not k.startswith("_")
            }
        if CAT_EMB_PATH.exists():
            zc = np.load(CAT_EMB_PATH)
            SESSION["cat_emb"] = {
                str(k): zc[k].astype(np.float32) for k in zc.files
            }

        # padding 向量：与所有嵌入正交
        q = np.random.RandomState(0).randn(emb.shape[1]).astype(np.float32)
        for _ in range(80):
            for v in emb:
                q -= (q @ v) * v
            n = np.linalg.norm(q)
            if n < 1e-2:
                q = np.random.RandomState(_ + 1).randn(emb.shape[1]).astype(np.float32)
                continue
            q /= n
        SESSION["pad_vec"] = (q / np.linalg.norm(q)).astype(np.float32)
        SESSION["metadata_ready"] = True
        return True
    except Exception as e:  # noqa: BLE001
        SESSION["metadata_error"] = f"{type(e).__name__}: {e}"
        SESSION["error"] = SESSION["metadata_error"]
        log(f"元数据加载失败: {SESSION['metadata_error']}")
        return False


def ensure_metadata() -> None:
    if SESSION["metadata_ready"] or SESSION["metadata_error"]:
        return
    with _METADATA_LOCK:
        load_metadata()


def load_all() -> None:
    global ort, ORT_IMPORT_ERROR
    if SESSION["ready"] or SESSION["error"]:
        return
    if not load_metadata():
        return
    try:
        if ort is None:
            try:
                import onnxruntime as ort_module
            except Exception as exc:  # pragma: no cover - host dependent
                ORT_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
                raise RuntimeError(f"onnxruntime 不可用: {ORT_IMPORT_ERROR}") from exc
            ort = ort_module
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"资源缺失: {MODEL_PATH.name}")
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = min(2, os.cpu_count() or 1)
        opts.inter_op_num_threads = 1
        opts.log_severity_level = 3
        SESSION["sess"] = ort.InferenceSession(
            str(MODEL_PATH), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        SESSION["ready"] = True
        log(
            f"就绪 | 物种库 {len(SESSION['lib']['species'])} 种 | "
            f"场景 {len(SESSION['scenes'])} 组 | "
            f"模型 {MODEL_PATH.stat().st_size/1024/1024:.1f}MB"
        )
    except Exception as e:  # noqa: BLE001
        SESSION["error"] = f"{type(e).__name__}: {e}"
        log(f"模型加载失败: {SESSION['error']}")


def ensure_loaded() -> None:
    """按需加载模型，避免 Django 启动时占用大量内存或阻塞检查命令。"""
    if SESSION["ready"] or SESSION["error"]:
        return
    with _LOAD_LOCK:
        load_all()


# ---------------------------------------------------------------- 词表处理

def resolve_targets(names: list[str]) -> list[tuple[str, str, np.ndarray]]:
    """把用户输入的物种名解析为 (英文提示词, 中文名, 嵌入向量)。

    支持：中文名、英文名、学名，大小写不敏感。
    向量统一取出，物种词与大类专栏的泛称词因此走同一条通道。
    """
    idx = SESSION["index"]
    lib = SESSION["lib"]["species"]
    emb = SESSION["emb"]
    out = []
    for raw in names:
        q = raw.strip()
        if not q:
            continue
        key = q.lower()
        if key in idx:
            i = idx[key]
            out.append((lib[i]["en"], lib[i]["zh"], emb[i]))
            continue
        # 学名匹配
        hit = None
        for i, s in enumerate(lib):
            if s.get("sci") and s["sci"].lower() == key:
                hit = i
                break
        if hit is not None:
            out.append((lib[hit]["en"], lib[hit]["zh"], emb[hit]))
            continue
        # 中文名反查
        zh_hit = None
        for i, s in enumerate(lib):
            if s.get("zh") and s["zh"] == q:
                zh_hit = i
                break
        if zh_hit is not None:
            out.append((lib[zh_hit]["en"], lib[zh_hit]["zh"], emb[zh_hit]))
    return out


def resolve_category(cat: str) -> list[tuple[str, str, np.ndarray]]:
    """把大类专栏名称解析为该大类的全部提示词。

    大类专栏的提示词（如 "water bird"）不在物种库中，
    嵌入来自单独的 category_emb.npz。
    """
    cats = SESSION["cats"]
    cemb = SESSION["cat_emb"]
    cfg = cats.get(cat)
    if not cfg:
        return []
    out = []
    for w in cfg.get("words", []):
        en = w["en"]
        v = cemb.get(en)
        # Updated groups also contain species prompts (e.g. muntjac, takin)
        # absent from the separate category embeddings. Both catalogs use the
        # same text encoder; reuse the exact species vector for those prompts.
        if v is None:
            row = SESSION["index"].get(en.lower())
            if row is not None:
                v = SESSION["emb"][row]
        if v is None:
            continue
        # 中文名统一用大类名 —— 结果只标大类，不暴露内部提示词
        out.append((en, cat, v))
    return out


def build_txt_feats(targets: list[tuple[str, str, np.ndarray]]) -> np.ndarray:
    """打包成固定槽位的文本嵌入矩阵（fp16，与模型输入类型一致）。

    空槽位用全零向量填充 —— 实测三种 padding 策略（零/正交/重复）
    准确率均为 4/4，零填充的分数分布最均衡。
    """
    out = np.zeros((1, SLOTS, 512), dtype=np.float16)
    for k, (_, _, v) in enumerate(targets[:SLOTS]):
        out[0, k] = v.astype(np.float16)
    return out


def build_txt_feats_with_aux(
    targets: list[tuple[str, str, np.ndarray]],
    aux: list[tuple[str, str, np.ndarray]],
) -> np.ndarray:
    """打包「物种槽 + 辅助槽（形态短语）」。

    物种槽在前（保证 argmax 的类名归属稳定），
    辅助槽在后（只抬升召回分数，不参与类名归属，见 detect()）。
    """
    out = np.zeros((1, SLOTS, 512), dtype=np.float16)
    k = 0
    for _, _, v in targets:
        if k >= SLOTS:
            break
        out[0, k] = v.astype(np.float16)
        k += 1
    for _, _, v in aux:
        if k >= SLOTS:
            break
        out[0, k] = v.astype(np.float16)
        k += 1
    return out


def resolve_phrase(phrase: str) -> list[tuple[str, str, np.ndarray]]:
    """解析形态短语的嵌入（短语不在物种库，嵌入来自 category_emb.npz）。"""
    cemb = SESSION.get("cat_emb") or {}
    v = cemb.get(phrase)
    if v is None:
        return []
    return [(phrase, "", v)]


# ---------------------------------------------------------------- 推理

def _letterbox(img: Image.Image, size: int = 640):
    w, h = img.size
    scale = min(size / w, size / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    im = img.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    canvas.paste(im, ((size - nw) // 2, (size - nh) // 2))
    return canvas, scale, (size - nw) // 2, (size - nh) // 2


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float = 0.5) -> list[int]:
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_thr]
    return keep


def _detect_frame(
    image: Image.Image,
    classes: list[str],
    txt_feats: np.ndarray,
    conf_thr: float = 0.20,
    iou_thr: float = 0.50,
    topk: int = 150,
    zh_map: dict | None = None,
    aux_from: int | None = None,
    aux_count: int = 0,
) -> list[dict]:
    sess = SESSION["sess"]
    zh_map = zh_map or {}
    img = image.convert("RGB")
    W, H = img.size

    canvas, scale, dx, dy = _letterbox(img, 640)
    arr = np.transpose(np.asarray(canvas, dtype=np.float32) / 255.0, (2, 0, 1))[None]

    with SESSION["lock"]:
        out = sess.run(
            None, {"images": arr.astype(np.float16), "txt_feats": txt_feats}
        )[0][0]

    # Half precision is appropriate for the network, not pixel-area arithmetic:
    # boxes larger than 256px overflow float16 during NMS and drop valid birds.
    out = out.astype(np.float32)

    if out.shape[0] < out.shape[1]:
        out = out.T
    boxes = out[:, :4]
    scores = out[:, 4:]

    n_real = min(len(classes), scores.shape[1])
    real = scores[:, :n_real]
    # 辅助槽（形态短语）：只参与打分，不参与类名归属。
    # 实测：短语槽分数常高于物种槽（如啄木鸟 0.975 vs 0.027），
    # 若让短语参与 argmax，结果类名会变成短语本身 —— 不可接受。
    # 因此：分数取「物种槽 + 辅助槽」的最大值，类名仍取物种槽的 argmax。
    n_aux = 0
    if aux_from is not None and aux_count > 0:
        n_aux = min(aux_count, scores.shape[1] - aux_from)
    if n_aux > 0:
        aux = scores[:, aux_from:aux_from + n_aux]
        best = np.maximum(real.max(axis=1), aux.max(axis=1))
        cls_idx = real.argmax(axis=1)
    else:
        cls_idx = real.argmax(axis=1)
        best = real.max(axis=1)

    mask = best >= conf_thr
    if not mask.any():
        return []
    idx = np.where(mask)[0]
    # 阈值过低时（如 0）会命中全部 8400 个锚点，NMS 开销极大。
    # 先按分数取前 N 个候选再做 NMS —— topk 的上界保证不会漏掉高置信目标。
    if len(idx) > 2000:
        keep_top = idx[np.argsort(-best[idx])[:2000]]
        idx = np.sort(keep_top)
    b = boxes[idx]
    cls_idx = cls_idx[idx]
    best = best[idx]

    cx, cy, bw, bh = b.T
    x1 = (cx - bw / 2 - dx) / scale
    y1 = (cy - bh / 2 - dy) / scale
    x2 = (cx + bw / 2 - dx) / scale
    y2 = (cy + bh / 2 - dy) / scale
    bxy = np.stack([x1, y1, x2, y2], axis=1)
    bxy[:, [0, 2]] = bxy[:, [0, 2]].clip(0, W)
    bxy[:, [1, 3]] = bxy[:, [1, 3]].clip(0, H)

    keep = _nms(bxy, best, iou_thr)
    res = []
    for i in keep:
        ci = int(cls_idx[i])
        if ci >= n_real:
            continue
        res.append(
            {
                "box": [round(float(t), 1) for t in bxy[i]],
                "score": round(float(best[i]), 4),
                "en": classes[ci],
                "zh": zh_map.get(classes[ci].lower(), ""),
            }
        )
    res.sort(key=lambda d: d["score"], reverse=True)
    return res[:topk]


def detect(image, classes, txt_feats, conf_thr=0.20, iou_thr=0.50,
           topk=150, zh_map=None, aux_from=None, aux_count=0):
    """Combine the full image with four overlapping crops for distant flocks.

    All boxes remain in original-image pixels, then one global NMS removes
    duplicates at crop boundaries. This is still the bundled ONNX model.
    """
    kwargs = dict(conf_thr=conf_thr, iou_thr=iou_thr, topk=topk,
                  zh_map=zh_map, aux_from=aux_from, aux_count=aux_count)
    results = _detect_frame(image, classes, txt_feats, **kwargs)
    width, height = image.size
    if max(width, height) >= 1600 and min(width, height) >= 600:
        crop_w, crop_h = round(width * .6), round(height * .6)
        for left in (0, width - crop_w):
            for top in (0, height - crop_h):
                crop = image.crop((left, top, left + crop_w, top + crop_h))
                for result in _detect_frame(crop, classes, txt_feats, **kwargs):
                    box = result['box']
                    result['box'] = [round(box[0] + left, 1), round(box[1] + top, 1),
                                     round(box[2] + left, 1), round(box[3] + top, 1)]
                    results.append(result)
    if not results:
        return []
    keep = _nms(np.asarray([r['box'] for r in results], dtype=np.float32),
                np.asarray([r['score'] for r in results], dtype=np.float32), iou_thr)
    return [results[i] for i in keep[:topk]]


def _load_font(size: int = 16):
    for name in (
        "msyh.ttc", "simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw(
    image: Image.Image,
    results: list[dict],
    zh_map: dict,
    show_en: bool = False,
    min_score: float = 0.0,
) -> Image.Image:
    img = image.convert("RGB").copy()
    d = ImageDraw.Draw(img)
    font = _load_font(16)
    small = _load_font(13)

    for r in results:
        if r["score"] < min_score:
            continue
        x1, y1, x2, y2 = r["box"]
        d.rectangle([x1, y1, x2, y2], outline=BOX, width=3)
        # 优先用结果项自身的 zh（用户改名后的显示名），否则回退到词表映射
        zh = r.get("zh") or zh_map.get(r["en"].lower(), "")
        label = f'{zh or r["en"]} {r["score"]:.0%}'
        if show_en and zh:
            label += f'  {r["en"]}'
        tb = d.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ty = y1 - th - 7
        if ty < 0:
            ty = min(y1 + 2, max(0, img.height - th - 6))
        d.rectangle([x1, ty, x1 + tw + 10, ty + th + 7], fill=BOX)
        d.text((x1 + 5, ty + 3), label, fill=(255, 255, 255), font=font)
    return img


def to_data_url(img: Image.Image, max_side: int = 1200) -> str:
    img = img.convert("RGB")
    if max(img.size) > max_side:
        r = max_side / max(img.size)
        img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=87)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def crop_data_url(image: Image.Image, box: list[float], pad: float = 0.08) -> str:
    """裁剪单个目标个体，输出 data url。"""
    W, H = image.size
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    px, py = w * pad, h * pad
    cx1 = max(0, int(x1 - px))
    cy1 = max(0, int(y1 - py))
    cx2 = min(W, int(x2 + px))
    cy2 = min(H, int(y2 + py))
    if cx2 - cx1 < 4 or cy2 - cy1 < 4:
        return ""
    crop = image.convert("RGB").crop((cx1, cy1, cx2, cy2))
    return to_data_url(crop, 480)


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(
        self,
        code: int,
        body: bytes,
        ctype: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(
            code,
            json.dumps(obj, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0 or n > 200 * 1024 * 1024:
            raise ValueError("请求体大小非法")
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _serve_leaflet(self, rel: str) -> None:
        """提供 Leaflet 静态资源（js/css/images），路径做安全校验。"""
        rel = rel.replace("\\", "/")
        if ".." in rel or rel.startswith("/"):
            self._json({"error": "bad path"}, 404)
            return
        f = ASSET_DIR / "leaflet" / rel
        if not f.exists() or not f.is_file():
            self._json({"error": "not found"}, 404)
            return
        ctype = {
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".png": "image/png",
            ".svg": "image/svg+xml",
        }.get(f.suffix.lower(), "application/octet-stream")
        self._send(200, f.read_bytes(), ctype)

    def _serve_tile(self, path_part: str = "") -> None:
        """代理开源地图瓦片（OpenStreetMap）。

        浏览器直连 OSM 会有跨域与限流问题，这里统一转发并加 UA，
        同时把上游失败转成明确的 JSON 错误，前端据此提示"无网络"。

        支持两种请求形式：
          /api/tile?z=4&x=13&y=6
          /api/tile/4/13/6.png
        """
        z = x = y = None
        # 形式二：路径 /4/13/6.png
        m = re.fullmatch(r"/(\d+)/(\d+)/(\d+)\.png", path_part)
        if m:
            z, x, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            # 形式一：查询参数
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            try:
                z = int(q.get("z", ["0"])[0])
                x = int(q.get("x", ["0"])[0])
                y = int(q.get("y", ["0"])[0])
            except (TypeError, ValueError):
                self._json({"error": "bad tile coords"}, 400)
                return
        if not (0 <= z <= 19):
            self._json({"error": "bad zoom"}, 400)
            return
        url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        req = urllib.request.Request(
            url, headers={"User-Agent": "FangZhouHuiYan/1.0 (species identification tool)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()
            self._send(
                200,
                data,
                "image/png",
                extra={"Cache-Control": "public, max-age=86400"},
            )
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"tile unavailable: {type(e).__name__}"}, 502)

    def do_GET(self) -> None:
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif p == "/logo.png":
            # 网页顶栏用的实验室 logo，随包分发
            logo = ASSET_DIR / "logo.png"
            if not logo.exists():
                self._json({"error": "logo missing"}, 404)
                return
            self._send(200, logo.read_bytes(), "image/png")
        elif p.startswith("/leaflet/"):
            # Leaflet 静态资源（离线分发，避免依赖 CDN）
            self._serve_leaflet(p[len("/leaflet/"):])
        elif p == "/api/tile" or p.startswith("/api/tile/"):
            # 开源地图瓦片代理：转发 OSM 瓦片，失败时返回明确错误供前端提示
            # 两种形式都支持：/api/tile?z=&x=&y= 与 /api/tile/{z}/{x}/{y}.png
            self._serve_tile(p[len("/api/tile"):])
        elif p == "/api/status":
            self._json(
                {
                    "ready": SESSION["ready"],
                    "error": SESSION["error"],
                    "species": SESSION["lib"].get("species", []),
                    "groups": SESSION["lib"].get("groups", []),
                    "orders": SESSION["lib"].get("orders", []),
                    "scenes": SESSION["scenes"],
                    "categories": SESSION["cats"],
                    "slots": SLOTS,
                    "max_targets": MAX_TARGETS,
                }
            )
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        p = self.path.split("?")[0]
        if p == "/api/detect":
            self._handle_detect()
        elif p == "/api/detect_batch":
            self._handle_batch()
        elif p == "/api/convert":
            self._handle_convert()
        elif p == "/api/relabel":
            self._handle_relabel()
        elif p == "/api/export_xlsx":
            self._handle_export_xlsx()
        else:
            self._json({"error": "not found"}, 404)

    # ---------------- 结果改名 + 重绘 ----------------
    def _handle_relabel(self) -> None:
        """按用户改名后的结果重绘标注图。

        前端改的是「显示名」（如把「雪豹」改成「雪豹(疑似)」），
        不影响模型输出。此端点接收原图 + 改名后的结果列表，
        返回重新绘制的标注图。
        """
        try:
            payload = self._body()
            image = _decode_image(payload.get("image", ""))
            if image is None:
                self._json({"error": "图片解析失败"}, 400)
                return
            results = payload.get("results") or []
            zh_map = {r.get("en", "").lower(): r.get("zh", "") for r in results if r.get("en")}
            # 改名后的中文名以结果项自身的 zh 为准，draw 优先取它
            marked = draw(
                image,
                results,
                zh_map,
                show_en=bool(payload.get("show_en")),
            )
            # 同步重算裁剪（目标物体）：删除某一行后调用方需要新的裁剪列表
            crops = []
            for idx, r in enumerate(results):
                box = r.get("box") or []
                if len(box) != 4:
                    continue
                c = crop_data_url(image, box)
                if c:
                    crops.append({
                        "idx": idx,
                        "en": r.get("en", ""),
                        "zh": r.get("zh", "") or zh_map.get(r.get("en", "").lower(), ""),
                        "img": c,
                    })
            self._json({"ok": True, "image": to_data_url(marked), "crops": crops})
        except Exception as e:  # noqa: BLE001
            log(f"重绘失败 {type(e).__name__}: {e}")
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    # ---------------- 导出 XLSX ----------------
    def _handle_export_xlsx(self) -> None:
        """把识别结果导出为 xlsx（多工作表：明细 / 统计）。"""
        try:
            payload = self._body()
            rows = payload.get("rows") or []      # [{file, zh, en, score, x1,y1,x2,y2}]
            summary = payload.get("summary") or []  # [{zh, en, count}]
            meta = payload.get("meta") or {}

            detail = Sheet(
                "识别明细",
                [
                    ["序号", "文件名", "物种", "英文名", "置信度",
                     "纬度 Lat", "经度 Lng",
                     "影像x1", "影像y1", "影像x2", "影像y2",
                     "图像宽", "图像高"],
                ]
                + [
                    [
                        i,
                        r.get("file", ""),
                        r.get("zh", ""),
                        r.get("en", ""),
                        ("percent", float(r.get("score", 0))),
                        r.get("lat", "") if r.get("lat") not in (None, "") else "",
                        r.get("lng", "") if r.get("lng") not in (None, "") else "",
                        int(round(r.get("x1", 0))),
                        int(round(r.get("y1", 0))),
                        int(round(r.get("x2", 0))),
                        int(round(r.get("y2", 0))),
                        int(r.get("img_w", 0)) if r.get("img_w") else "",
                        int(r.get("img_h", 0)) if r.get("img_h") else "",
                    ]
                    for i, r in enumerate(rows, start=1)
                ],
            )

            total = sum(int(s.get("count", 0)) for s in summary)
            stat = Sheet(
                "物种统计",
                [["物种", "英文名", "数量", "占比"]]
                + [
                    [
                        s.get("zh", ""),
                        s.get("en", ""),
                        ("int", int(s.get("count", 0))),
                        ("percent", (int(s.get("count", 0)) / total) if total else 0),
                    ]
                    for s in summary
                ],
            )

            info = Sheet(
                "说明",
                [
                    ["项目", "内容"],
                    ["导出时间", meta.get("at", "")],
                    ["目标词表", meta.get("targets", "")],
                    ["识别图片数", ("int", int(meta.get("images", 0)))],
                    ["检出目标总数", ("int", int(meta.get("detections", 0)))],
                    ["涉及物种类数", ("int", len(summary))],
                    ["置信度阈值", meta.get("conf", "")],
                    ["生成工具", "方舟慧眼 · 物种识别器（YOLO-World + ONNX Runtime）"],
                ],
            )

            data = build([detail, stat, info], title="方舟慧眼识别报告")
            self._send(
                200,
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as e:  # noqa: BLE001
            log(f"导出失败 {type(e).__name__}: {e}")
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    # ---------------- 格式转换 ----------------
    def _handle_convert(self) -> None:
        """把浏览器无法解码的格式（TIFF/HEIC/AVIF…）转成 PNG。

        前端 FileReader 拿到的是原始字节，浏览器无法解码这些格式，
        但后端 PIL 可以。此端点负责转码后回传 PNG data URL。
        """
        try:
            payload = self._body()
            raw = payload.get("image", "")
            name = payload.get("name", "image")
            if "," in raw:
                raw = raw.split(",", 1)[1]
            blob = base64.b64decode(raw)
            img = Image.open(io.BytesIO(blob))
            img.load()

            # EXIF 方向校正：相机拍摄的照片常靠 EXIF 记录旋转
            try:
                from PIL import ImageOps

                img = ImageOps.exif_transpose(img) or img
            except Exception:
                pass

            img = img.convert("RGB")
            # 限制最长边，避免超大图（如 8K）在浏览器里卡顿
            w, h = img.size
            max_side = 2400
            if max(w, h) > max_side:
                r = max_side / max(w, h)
                img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)

            self._json(
                {
                    "ok": True,
                    "name": name,
                    "size": list(img.size),
                    "image": to_data_url(img, 1600),
                    "converted": True,
                }
            )
        except Exception as e:  # noqa: BLE001
            log(f"格式转换失败 {type(e).__name__}: {e}")
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    # ---------------- 单图 ----------------
    def _handle_detect(self) -> None:
        if not SESSION["ready"]:
            self._json({"error": SESSION["error"] or "尚未就绪"}, 503)
            return
        try:
            payload = self._body()
            targets_raw = payload.get("targets") or []
            cat = payload.get("category") or ""
            phrase = (payload.get("phrase") or "").strip()
            aux = []
            if cat:
                # 大类专栏：整栏作为一个目标，词表由服务端下发
                targets = resolve_category(cat)
            else:
                if not targets_raw:
                    scene = payload.get("scene")
                    if scene and scene in SESSION["scenes"]:
                        targets_raw = SESSION["scenes"][scene]["classes"]
                targets = resolve_targets(targets_raw)
                # 细分组合的形态短语：作为辅助槽，只抬升召回分数，
                # 不参与类名归属（见 detect() 的 aux_from 逻辑）
                if phrase:
                    aux = resolve_phrase(phrase)
            if not targets:
                self._json({"error": "请先选择目标物种"}, 400)
                return
            if len(targets) > MAX_TARGETS:
                self._json({"error": f"最多选择 {MAX_TARGETS} 个目标物种"}, 400)
                return

            image = _decode_image(payload.get("image", ""))
            if image is None:
                self._json({"error": "图片解析失败"}, 400)
                return

            classes = [t[0] for t in targets]
            zh_map = {t[0].lower(): t[1] for t in targets}
            # 辅助槽（形态短语）排在物种槽之后；
            # aux_from 指向其起始槽位，detect() 据此区分「打分槽」与「类名槽」
            aux_from = None
            aux_count = 0
            if aux:
                feats = build_txt_feats_with_aux(targets, aux)
                aux_from = len(targets)
                aux_count = len(aux)
            else:
                feats = build_txt_feats(targets)

            conf = float(payload.get("conf", 0.05))
            t0 = time.time()
            results = detect(
                image,
                classes,
                feats,
                conf_thr=conf,
                iou_thr=float(payload.get("iou", 0.5)),
                zh_map=zh_map,
                aux_from=aux_from,
                aux_count=aux_count,
            )
            dt = (time.time() - t0) * 1000

            marked = draw(
                image,
                results,
                zh_map,
                show_en=bool(payload.get("show_en")),
            )
            # 裁剪全部目标（不再只取前 6 个），并带上结果行下标，
            # 前端据此把「结果行」与「裁剪个体」一一对应、点击联动标亮
            crops = []
            for idx, r in enumerate(results):
                c = crop_data_url(image, r["box"])
                if c:
                    crops.append({
                        "idx": idx,
                        "en": r["en"],
                        "zh": zh_map.get(r["en"].lower(), ""),
                        "img": c,
                    })

            self._json(
                {
                    "ok": True,
                    "count": len(results),
                    "elapsed_ms": round(dt),
                    "size": list(image.size),
                    "results": results,
                    "image": to_data_url(marked),
                    "crops": crops,
                    "targets": [{"en": t[0], "zh": t[1]} for t in targets],
                    "category": cat,
                }
            )
        except Exception as e:  # noqa: BLE001
            log(f"检测失败 {type(e).__name__}: {e}")
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    # ---------------- 批量 ----------------
    def _handle_batch(self) -> None:
        if not SESSION["ready"]:
            self._json({"error": SESSION["error"] or "尚未就绪"}, 503)
            return
        try:
            payload = self._body()
            targets_raw = payload.get("targets") or []
            cat = payload.get("category") or ""
            if cat:
                targets = resolve_category(cat)
            else:
                if not targets_raw:
                    scene = payload.get("scene")
                    if scene and scene in SESSION["scenes"]:
                        targets_raw = SESSION["scenes"][scene]["classes"]
                targets = resolve_targets(targets_raw)
            if not targets:
                self._json({"error": "请先选择目标物种"}, 400)
                return

            images = payload.get("images") or []
            if not images:
                self._json({"error": "没有待处理图片"}, 400)
                return

            classes = [t[0] for t in targets]
            zh_map = {t[0].lower(): t[1] for t in targets}
            feats = build_txt_feats(targets)
            conf = float(payload.get("conf", 0.05))

            rows = []
            t0 = time.time()
            for idx, item in enumerate(images):
                name = item.get("name") or f"image_{idx + 1}"
                try:
                    image = _decode_image(item.get("image", ""))
                    if image is None:
                        rows.append(
                            {
                                "name": name,
                                "error": "图片解析失败",
                                "results": [],
                                "image": "",
                                "size": [0, 0],
                            }
                        )
                        continue
                    results = detect(image, classes, feats, conf_thr=conf, zh_map=zh_map)
                    marked = draw(image, results, zh_map)
                    rows.append(
                        {
                            "name": name,
                            "error": "",
                            "count": len(results),
                            "results": results,
                            "image": to_data_url(marked, 900),
                            "size": list(image.size),
                        }
                    )
                except Exception as e:  # noqa: BLE001
                    rows.append(
                        {
                            "name": name,
                            "error": f"{type(e).__name__}: {e}",
                            "results": [],
                            "image": "",
                            "size": [0, 0],
                        }
                    )
            dt = (time.time() - t0) * 1000

            total_det = sum(len(r["results"]) for r in rows)
            hits = sum(1 for r in rows if r["results"])
            self._json(
                {
                    "ok": True,
                    "rows": rows,
                    "summary": {
                        "images": len(rows),
                        "with_detection": hits,
                        "detections": total_det,
                        "elapsed_ms": round(dt),
                        "avg_ms": round(dt / max(1, len(rows))),
                    },
                    "targets": [{"en": t[0], "zh": t[1]} for t in targets],
                }
            )
        except Exception as e:  # noqa: BLE001
            log(f"批量失败 {type(e).__name__}: {e}")
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)


def _decode_image(data_url: str) -> Image.Image | None:
    """解码 data URL 为 PIL Image，并做 EXIF 方向校正。

    相机拍摄的 JPEG 常把方向存在 EXIF 里而非像素本身；
    若不校正，检测框会画在错误位置。
    """
    if not data_url:
        return None
    raw = data_url.split(",", 1)[1] if "," in data_url else data_url
    try:
        img = Image.open(io.BytesIO(base64.b64decode(raw)))
        img.load()
        try:
            from PIL import ImageOps

            img = ImageOps.exif_transpose(img) or img
        except Exception:
            pass
        return img
    except Exception:
        return None


def free_port(preferred: int = 8765) -> int:
    import socket

    for port in [preferred] + list(range(8766, 8800)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    print("=" * 66)
    print("  方舟慧眼 · 物种识别器")
    print("  Local Wildlife Identifier   YOLO-World + ONNX Runtime")
    print("  全部计算在本机完成，图片不会离开这台电脑")
    print("=" * 66)

    load_all()

    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    def opener() -> None:
        time.sleep(1.4)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=opener, daemon=True).start()

    print(f"\n  服务已启动: {url}")
    print("  若浏览器未自动打开，请手动复制上面地址")
    print("  关闭本窗口即退出程序\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  已退出")


if __name__ == "__main__":
    main()
