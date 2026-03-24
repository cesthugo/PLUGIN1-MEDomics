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
    _m = types.ModuleType("tqdm")
    _m.tqdm = lambda it=None, *a, **kw: (it if it is not None else iter([]))
    sys.modules.setdefault("tqdm", _m)
    sys.modules.setdefault("tqdm.auto", _m)

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
import torchvision.ops as tv_ops
import mmcv.ops.nms  # noqa: F401  — déclenche load_ext avec stub _ext
from mmcv.ops.nms import NMSop


def _tv_nms_fwd(ctx, bboxes, scores, iou_threshold,
                offset, score_threshold, max_num):
    is_filtering = score_threshold > 0
    if is_filtering:
        valid_mask = scores > score_threshold
        valid_inds = valid_mask.nonzero(as_tuple=False).squeeze(dim=1)
        bboxes = bboxes[valid_mask]
        scores = scores[valid_mask]
    else:
        valid_inds = None
    inds = tv_ops.nms(bboxes.float(), scores.float(), float(iou_threshold))
    if max_num > 0:
        inds = inds[:max_num]
    if is_filtering and valid_inds is not None:
        inds = valid_inds[inds]
    return inds


NMSop.forward = staticmethod(_tv_nms_fwd)

# ─── 5. Imports mmdet ────────────────────────────────────────────────────────
import cv2
import numpy as np
from mmengine.config import Config
from mmengine.registry import DefaultScope
import mmdet.models  # noqa: F401  — enregistre les classes dans le registre
from mmdet.registry import MODELS

# ─── Constantes prétraitement ─────────────────────────────────────────────────
_INPUT_SIZE = 640
_PAD_VAL    = 114.0
_MEAN = torch.tensor([103.53, 116.28, 123.675]).view(3, 1, 1)
_STD  = torch.tensor([ 57.375,  57.12,  58.395]).view(3, 1, 1)


def _replace_syncbn(d):
    if isinstance(d, dict):
        if d.get("type") == "SyncBN":
            d["type"] = "BN"
        for v in d.values():
            _replace_syncbn(v)
    elif isinstance(d, (list, tuple)):
        for item in d:
            _replace_syncbn(item)


def _preprocess(frame: np.ndarray):
    orig_H, orig_W = frame.shape[:2]
    scale = min(_INPUT_SIZE / orig_H, _INPUT_SIZE / orig_W)
    new_H, new_W = int(round(orig_H * scale)), int(round(orig_W * scale))
    resized = cv2.resize(frame, (new_W, new_H), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), _PAD_VAL, dtype=np.float32)
    canvas[:new_H, :new_W] = resized.astype(np.float32)
    tensor = torch.from_numpy(canvas.transpose(2, 0, 1))
    tensor = (tensor - _MEAN) / _STD
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


def main():
    parser = argparse.ArgumentParser(description="RTMDet single-image inference")
    parser.add_argument("--config",    required=True)
    parser.add_argument("--ckpt",      required=True)
    parser.add_argument("--image",     required=True)
    parser.add_argument("--out",       required=True)
    parser.add_argument("--score-thr", type=float, default=0.001)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Charger le modèle
    cfg = Config.fromfile(args.config)
    _replace_syncbn(cfg._cfg_dict)
    with DefaultScope.overwrite_default_scope("mmdet"):
        model = MODELS.build(cfg.model)
        _load_ckpt(model, args.ckpt, device)
    model.to(device).eval()

    # Lire l'image (BGR → garder tel quel, le modèle accepte BGR d'après config)
    frame = cv2.imread(args.image)
    if frame is None:
        sys.exit(f"Impossible de lire l'image : {args.image}")

    tensor, meta = _preprocess(frame)
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

    detections = [
        {
            "bbox":  [float(x) for x in bb],
            "score": float(sc),
            "label": "tumor",
        }
        for bb, sc in zip(bboxes, scores)
        if sc >= args.score_thr
    ]

    Path(args.out).write_text(
        json.dumps(detections, indent=2), encoding="utf-8"
    )
    print(f"[rtmdet_runner] {len(detections)} detection(s) saved -> {args.out}")


if __name__ == "__main__":
    main()
