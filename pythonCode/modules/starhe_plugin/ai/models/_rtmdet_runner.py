"""
ai/models/_rtmdet_runner.py — Script standalone RTMDet
=======================================================
Script appelé EN SUBPROCESS par starhe_detect.py.
NE PAS importer directement — utiliser via subprocess uniquement.

Usage :
    python _rtmdet_runner.py \\
        --config  <path/rtmdet_starhe.py>   \\
        --ckpt    <path/best_xxx.pth>        \\
        --image   <path/frame.png>           \\
        --out     <path/results.json>        \\
        [--score-thr 0.001]

Sortie JSON (liste de détections) :
    [{"bbox": [x0,y0,x1,y1], "score": 0.87, "label": "tumor"}, ...]
"""

import sys
import json
import base64
import types
import argparse
from pathlib import Path

# ─── 1. Stub mmcv._ext (avant tout import mmcv/mmdet) ────────────────────────
if "mmcv._ext" not in sys.modules:
    class _CExtStub(types.ModuleType):
        def __getattr__(self, name):
            def _unavailable(*a, **kw):
                raise RuntimeError(f"mmcv._ext.{name}: C-extension absente.")
            return _unavailable
    sys.modules["mmcv._ext"] = _CExtStub("mmcv._ext")

# ─── 2. Stub tqdm si absent ───────────────────────────────────────────────────
try:
    import tqdm  # noqa: F401
except ImportError:
    import importlib.machinery as _im
    _m = types.ModuleType("tqdm")
    _m.tqdm = lambda it=None, *a, **kw: (it if it is not None else iter([]))
    _m.__spec__ = _im.ModuleSpec("tqdm", None)
    _m_auto = types.ModuleType("tqdm.auto")
    _m_auto.tqdm = _m.tqdm
    _m_auto.__spec__ = _im.ModuleSpec("tqdm.auto", None)
    sys.modules.setdefault("tqdm", _m)
    sys.modules.setdefault("tqdm.auto", _m_auto)

# ─── 3. Patch inspect.getmodule (Python 3.13 / mmengine compat) ──────────────
import inspect as _inspect

_orig_getmodule = _inspect.getmodule


def _safe_getmodule(obj, _filename=None):
    try:
        return _orig_getmodule(obj, _filename)
    except (AttributeError, TypeError, OSError):
        if isinstance(obj, types.FrameType):
            mod_name = obj.f_globals.get("__name__")
            if mod_name:
                return sys.modules.get(mod_name)
        return None


_inspect.getmodule = _safe_getmodule

# ─── 4. Patch NMSop.forward → torchvision.ops.nms ───────────────────────────
import torch
import torch.nn.functional as F

# ── Reproductibilité cross-plateforme ─────────────────────────────────────────
# Sur les GPU NVIDIA Ampere+ (RTX 30xx/40xx), PyTorch active TF32 par défaut :
# TF32 n'utilisent que 10 bits de mantisse (≈ float16) pour les matmuls, vs
# 23 bits pour float32.  Cela provoque des différences de ~0.5-2 % par score
# par rapport à CPU/MPS et peut faire basculer des détections borderline.
# → On désactive TF32 et on active le mode déterministe cuDNN pour que les
#   résultats sur CUDA restent cohérents avec CPU/MPS.
if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = False   # désactive TF32 matmul
    torch.backends.cudnn.allow_tf32      = False    # désactive TF32 cuDNN
    torch.backends.cudnn.deterministic   = True     # algos déterministes
    torch.backends.cudnn.benchmark       = False    # pas de sélection auto
# Algorithmes déterministes globaux (protège scatter/atomics sur MPS et CUDA)
torch.use_deterministic_algorithms(True, warn_only=True)

import torchvision.ops as tv_ops
import mmcv.ops.nms  # noqa: F401  — déclenche load_ext avec stub _ext
from mmcv.ops.nms import NMSop


def _tv_nms_fwd(ctx, bboxes, scores, iou_threshold,
                offset, score_threshold, max_num):
    # Force CPU: torchvision NMS may not support MPS, and mmengine
    # InstanceData.__getitem__ only accepts torch.LongTensor (CPU).
    bboxes = bboxes.float().cpu()
    scores = scores.float().cpu()
    is_filtering = score_threshold > 0
    if is_filtering:
        valid_mask = scores > score_threshold
        valid_inds = valid_mask.nonzero(as_tuple=False).squeeze(dim=1)
        bboxes = bboxes[valid_mask]
        scores = scores[valid_mask]
    else:
        valid_inds = None
    inds = tv_ops.nms(bboxes, scores, float(iou_threshold))
    if max_num > 0:
        inds = inds[:max_num]
    if is_filtering and valid_inds is not None:
        inds = valid_inds[inds]
    return inds  # CPU tensor — compatible with mmengine InstanceData


NMSop.forward = staticmethod(_tv_nms_fwd)

# ─── 5. Imports mmdet ────────────────────────────────────────────────────────
import cv2
import numpy as np
from mmengine.config import Config
from mmengine.registry import DefaultScope
import mmdet.models  # noqa: F401  — enregistre les classes dans le registre
from mmdet.registry import MODELS

# ─── 6. Patch mmengine InstanceData pour MPS ─────────────────────────────────
# mmengine.InstanceData.__getitem__ ne supporte que torch.LongTensor (CPU).
# Sur MPS, les tensors sont sur mps:0 → assertion fail + cross-device indexing.
# On patche pour copier les champs non-CPU vers CPU avant l'indexation.
from mmengine.structures.instance_data import InstanceData as _InstData
_orig_inst_getitem = _InstData.__getitem__


def _mps_safe_getitem(self, item):
    if isinstance(item, torch.Tensor) and item.device.type not in ("cpu", "cuda"):
        # Move index to CPU for isinstance check
        item = item.cpu()
    # If any field is on a non-standard device (MPS), copy everything to CPU first
    has_nonstandard = any(
        isinstance(v, torch.Tensor) and v.device.type not in ("cpu", "cuda")
        for v in self.values()
    )
    if has_nonstandard:
        cpu_self = type(self)()
        for k, v in self.items():
            cpu_self[k] = v.cpu() if isinstance(v, torch.Tensor) else v
        return _orig_inst_getitem(cpu_self, item)
    return _orig_inst_getitem(self, item)


_InstData.__getitem__ = _mps_safe_getitem

# ─── Constantes prétraitement ─────────────────────────────────────────────────
_INPUT_SIZE = 640
_PAD_VAL    = 114.0
# Précalcul des variants float32 / float64 pour _preprocess (évite .to() à chaque appel)
_MEAN_F32 = torch.tensor([103.53, 116.28, 123.675]).view(3, 1, 1)          # float32
_STD_F32  = torch.tensor([ 57.375,  57.12,  58.395]).view(3, 1, 1)          # float32
_MEAN_F64 = _MEAN_F32.double()                                               # float64
_STD_F64  = _STD_F32.double()                                                # float64


def _replace_syncbn(d):
    if isinstance(d, dict):
        if d.get("type") == "SyncBN":
            d["type"] = "BN"
        for v in d.values():
            _replace_syncbn(v)
    elif isinstance(d, (list, tuple)):
        for item in d:
            _replace_syncbn(item)


def _preprocess(frame: np.ndarray, use_double: bool = False):
    orig_H, orig_W = frame.shape[:2]
    scale = min(_INPUT_SIZE / orig_H, _INPUT_SIZE / orig_W)
    new_H, new_W = int(round(orig_H * scale)), int(round(orig_W * scale))
    np_dtype = np.float64 if use_double else np.float32
    mean      = _MEAN_F64 if use_double else _MEAN_F32
    std       = _STD_F64  if use_double else _STD_F32
    # F.interpolate : noyau C++ identique x86/ARM.
    # use_double=True : frame converti en float64 AVANT l'interpolation,
    # éliminant les 1-2 ULP de différence AVX2/NEON float32 qui survivent
    # jusqu'au score même après le cast tardif.
    t = torch.from_numpy(
        np.ascontiguousarray(frame, dtype=np_dtype)
    ).permute(2, 0, 1).unsqueeze(0)                    # (1, 3, H, W)
    resized = F.interpolate(t, size=(new_H, new_W), mode='bilinear', align_corners=False)
    resized = resized.squeeze(0).permute(1, 2, 0).numpy()  # (new_H, new_W, 3)
    canvas = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), _PAD_VAL, dtype=np_dtype)
    canvas[:new_H, :new_W] = resized
    tensor = torch.from_numpy(np.ascontiguousarray(canvas.transpose(2, 0, 1)))
    tensor = (tensor - mean) / std
    tensor = tensor.unsqueeze(0)
    meta = {
        "img_shape":         (_INPUT_SIZE, _INPUT_SIZE),
        "ori_shape":         (orig_H, orig_W),
        "scale_factor":      (float(new_W / orig_W), float(new_H / orig_H)),
        "pad_shape":         (_INPUT_SIZE, _INPUT_SIZE),
        "batch_input_shape": (_INPUT_SIZE, _INPUT_SIZE),
    }
    return tensor, meta


def _load_ckpt(model, ckpt_path, device):
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    state_dict = ckpt.get("state_dict", ckpt)
    state_dict = {k: v for k, v in state_dict.items()
                  if not k.startswith("data_preprocessor.")}
    model.load_state_dict(state_dict, strict=False)


def _infer_one_frame(model, frame: np.ndarray, score_thr: float, device: str,
                     use_double: bool = False) -> list:
    """Inference on a single BGR uint8 numpy frame."""
    tensor, meta = _preprocess(frame, use_double=use_double)  # dtype déjà correct
    tensor = tensor.to(device)
    with torch.no_grad():
        feats      = model.backbone(tensor)
        neck_feats = model.neck(feats)
        head_outs  = model.bbox_head(neck_feats)
        results    = model.bbox_head.predict_by_feat(
            *head_outs, batch_img_metas=[meta], rescale=True
        )
    instances = results[0]
    bboxes = instances.bboxes.cpu().numpy()
    scores = instances.scores.cpu().numpy()
    # Arrondi à 6 décimales avant la comparaison au seuil :
    # MKL (Windows x86) et Accelerate (macOS ARM) produisent des résultats float64
    # qui diffèrent de ~1e-11 par couche convolutive.  Après un backbone de 50+
    # couches, l'erreur cumulée peut atteindre ~1e-9 — suffisant pour faire passer
    # un score de 0.6999999991 (Mac) à 0.7000000002 (Win) et changer le résultat.
    # Tolérance 5e-7 >> 1e-9 → résultats identiques cross-plateforme.
    # Le score stocké dans la détection garde la précision d'origine (non arrondi).
    return [
        {"bbox": [float(x) for x in bb], "score": float(sc), "label": "tumor"}
        for bb, sc in zip(bboxes, scores)
        if round(float(sc), 6) >= score_thr
    ]


def _infer_one(model, image_path: str, score_thr: float, device: str) -> list:
    """Legacy wrapper: read image from disk then infer."""
    frame = cv2.imread(image_path)
    if frame is None:
        return []
    return _infer_one_frame(model, frame, score_thr, device)


def _infer_batch_frames(model, frames: list, score_thr: float, device: str,
                        use_double: bool = False) -> list:
    """Batch inference on a list of BGR uint8 numpy frames."""
    tensors   = []
    metas     = []
    valid_idx = []

    for i, frame in enumerate(frames):
        if frame is None:
            continue
        tensor, meta = _preprocess(frame, use_double=use_double)  # dtype déjà correct
        tensors.append(tensor)
        metas.append(meta)
        valid_idx.append(i)

    results_out = [[] for _ in frames]
    if not valid_idx:
        return results_out

    batch_tensor = torch.cat(tensors, dim=0).to(device)

    with torch.no_grad():
        feats      = model.backbone(batch_tensor)
        neck_feats = model.neck(feats)
        head_outs  = model.bbox_head(neck_feats)
        results    = model.bbox_head.predict_by_feat(
            *head_outs, batch_img_metas=metas, rescale=True
        )

    for pos, orig_idx in enumerate(valid_idx):
        instances = results[pos]
        bboxes = instances.bboxes.cpu().numpy()
        scores = instances.scores.cpu().numpy()
        results_out[orig_idx] = [
            {"bbox": [float(x) for x in bb], "score": float(sc), "label": "tumor"}
            for bb, sc in zip(bboxes, scores)
            if round(float(sc), 6) >= score_thr
        ]

    return results_out


def _decode_b64_frames(frames_b64: list, shapes: list = None,
                       shape: list = None) -> list:
    """Decode a list of base64-encoded BGR uint8 frames."""
    out = []
    for i, b64 in enumerate(frames_b64):
        raw = base64.b64decode(b64)
        s   = shapes[i] if shapes else shape
        out.append(np.frombuffer(raw, dtype=np.uint8).reshape(s))
    return out


def _infer_batch(model, image_paths: list, score_thr: float, device: str) -> list:
    """Legacy wrapper: read images from disk then batch-infer."""
    frames = [cv2.imread(p) for p in image_paths]
    return _infer_batch_frames(model, frames, score_thr, device)


def _build_model(config_path: str, ckpt_path: str, device: str):
    cfg = Config.fromfile(config_path)
    _replace_syncbn(cfg._cfg_dict)
    with DefaultScope.overwrite_default_scope("mmdet"):
        model = MODELS.build(cfg.model)
        _load_ckpt(model, ckpt_path, device)
    model.to(device).eval()
    return model


def main():
    parser = argparse.ArgumentParser(description="RTMDet inference — mode image ou serveur")
    parser.add_argument("--config",    required=True)
    parser.add_argument("--ckpt",      required=True)
    parser.add_argument("--score-thr", type=float, default=0.001)
    # Mode image unique (legacy)
    parser.add_argument("--image",     default=None, help="Chemin image (mode one-shot)")
    parser.add_argument("--out",       default=None, help="Fichier JSON de sortie (mode one-shot)")
    # Mode serveur persistant
    parser.add_argument("--mode",      default="image", choices=["image", "server"],
                        help="'server' : stdin/stdout JSON, 'image' : one-shot (défaut)")
    # Device override (INFERENCE_DEVICE in config.py)
    parser.add_argument("--device",    default=None,
                        help="Force le device : 'cpu', 'cuda', 'mps'. "
                             "Par défaut : auto-détection.")
    # Reproductibilité cross-plateforme : CPU + float64
    parser.add_argument("--deterministic", action="store_true",
                        help="Force CPU + float64 pour des résultats identiques "
                             "entre Windows (MKL) et macOS (Accelerate).")
    args = parser.parse_args()

    # ── Sélection du device ──────────────────────────────────────────────────
    if args.deterministic:
        # DETERMINISTIC_INFERENCE : force CPU indépendamment du hardware disponible.
        # Raison : MPS (Mac Apple Silicon GPU) vs CPU (Windows) donne des résultats
        # float32 complètement différents (écart ~0.01 sur les scores borderline).
        # Sur CPU, float64 réduit l'erreur BLAS MKL↔Accelerate de ~1e-4 à ~1e-13.
        device = "cpu"
    elif args.device and args.device != "auto":
        device = args.device
    elif torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    # Reproductibilité cross-plateforme sur CPU :
    # PyTorch utilise MKL (Windows) ou Accelerate/OpenBLAS (macOS) selon la plateforme.
    # Avec plusieurs threads, l'ordre d'accumulation flottante varie selon le thread count.
    # 1 thread → ordre déterministe sur chaque plateforme, différence résiduelle ~1e-5 par op.
    if device == "cpu":
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)

    model = _build_model(args.config, args.ckpt, device)

    if args.deterministic:
        # Convert all parameters/buffers to float64.
        # Float64 BLAS error between MKL and Accelerate is ~1e-13 per op,
        # vs ~1e-4 for float32 — invisible after sigmoid/threshold comparison.
        model = model.double()
    use_double = args.deterministic

    if args.mode == "server":
        # ── Mode serveur ────────────────────────────────────────────────────
        # Protocole :
        #   stdin  → une ligne JSON par requête : {"image": "<path>", "score_thr": 0.70}
        #            ou la chaîne littérale "__EXIT__" pour fermer proprement
        #   stdout → une ligne JSON par réponse : [{"bbox":…, "score":…, "label":…}, …]
        # flush obligatoire après chaque écriture pour débloquer le parent
        hw_info = {"device": device}
        if device == "cuda":
            try:
                free, total = torch.cuda.mem_get_info(0)
                hw_info["vram_free_mb"]  = round(free  / (1024 ** 2), 1)
                hw_info["vram_total_mb"] = round(total / (1024 ** 2), 1)
            except Exception:
                pass
        elif device in ("mps", "cpu"):
            # Mesure la RAM libre APRÈS chargement du modèle dans ce subprocess.
            # Beaucoup plus précis que de mesurer dans le processus parent.
            try:
                import psutil
                hw_info["ram_free_mb"] = round(
                    psutil.virtual_memory().available / (1024 ** 2), 1
                )
            except Exception:
                pass
        print(f"[rtmdet_server] READY {json.dumps(hw_info)}", flush=True)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            if line == "__EXIT__":
                break
            try:
                req      = json.loads(line)
                thr      = float(req.get("score_thr", args.score_thr))
                # Base64 protocol (no disk I/O)
                if "frames_b64" in req:
                    frames = _decode_b64_frames(
                        req["frames_b64"],
                        shapes=req.get("shapes"),
                        shape=req.get("shape"),
                    )
                    dets = _infer_batch_frames(model, frames, thr, device,
                                              use_double=use_double)
                elif "frame_b64" in req:
                    raw   = base64.b64decode(req["frame_b64"])
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape(req["shape"])
                    dets  = _infer_one_frame(model, frame, thr, device,
                                            use_double=use_double)
                # Legacy file-path protocol (backward compat)
                elif "images" in req:
                    dets = _infer_batch(model, req["images"], thr, device)
                else:
                    dets = _infer_one(model, req["image"], thr, device)
                print(json.dumps(dets), flush=True)
            except Exception as exc:
                print(json.dumps({"error": str(exc)}), flush=True)

    else:
        # ── Mode one-shot (legacy) ───────────────────────────────────────────
        if not args.image or not args.out:
            sys.exit("--image et --out requis en mode 'image'")
        dets = _infer_one_frame(model,
                                cv2.imread(args.image),
                                args.score_thr, device,
                                use_double=use_double)
        Path(args.out).write_text(json.dumps(dets, indent=2), encoding="utf-8")
        print(f"[rtmdet_runner] {len(dets)} detection(s) saved -> {args.out}")


if __name__ == "__main__":
    main()
