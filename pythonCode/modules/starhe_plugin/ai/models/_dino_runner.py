"""
ai/models/_dino_runner.py — Standalone DINO-DETR script
========================================================
Script called AS A SUBPROCESS by starhe_detect.py.
DO NOT import directly — use via subprocess only.

Usage:
    python _dino_runner.py \\
        --config    <path/dino_starhe.py>           \\
        --ckpt      <path/best_xxx.pth>             \\
        --starhe-root <path/starhe_share/>          \\
        --image     <path/frame.png>                \\
        --out       <path/results.json>             \\
        [--score-thr 0.001]

JSON output (list of detections):
    [{"bbox": [x0,y0,x1,y1], "score": 0.87, "label": "tumor"}, ...]
"""

import sys
import json
import types
import argparse
from pathlib import Path

# ─── 1. Stub mmcv._ext (before any mmcv/mmdet import) ────────────────────────
if "mmcv._ext" not in sys.modules:
    class _CExtStub(types.ModuleType):
        def __getattr__(self, name):
            def _unavailable(*a, **kw):
                raise RuntimeError(f"mmcv._ext.{name}: C-extension absente.")
            return _unavailable
    sys.modules["mmcv._ext"] = _CExtStub("mmcv._ext")

# ─── 2. Stub tqdm if missing ──────────────────────────────────────────────────
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
import mmcv.ops.nms  # noqa: F401
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

# ─── 5. Entry point ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="_dino_runner.py",
        description="DINO-DETR inference — called as a subprocess by starhe_detect.py",
    )
    parser.add_argument("--config",      required=True, help="Path to dino_starhe.py")
    parser.add_argument("--ckpt",        required=True, help="Path to the .pth checkpoint")
    parser.add_argument("--starhe-root", required=True, dest="starhe_root",
                        help="Root of the starhe_share repo (directory containing `starhe/`)")
    parser.add_argument("--image",       required=True, help="Path to the image (PNG/JPEG)")
    parser.add_argument("--out",         required=True, help="JSON output path")
    parser.add_argument("--score-thr",   type=float, default=0.001, dest="score_thr",
                        help="Minimum confidence threshold (default: 0.001)")
    args = parser.parse_args()

    # Register the custom starhe modules
    if args.starhe_root not in sys.path:
        sys.path.insert(0, args.starhe_root)
    try:
        import starhe.models  # noqa: F401
    except ImportError as e:
        print(f"[dino_runner] ERREUR import starhe.models : {e}", file=sys.stderr)
        sys.exit(1)

    # mmdet imports (safe after stubs + starhe registration)
    import cv2
    import numpy as np
    from mmcv.transforms import Compose
    from mmdet.apis import init_detector, inference_detector

    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Model loading
    model = init_detector(args.config, args.ckpt, device=device)

    # Replace the file loader with an in-memory loader
    cfg = model.cfg.copy()
    cfg.test_dataloader.dataset.pipeline[0].type = "LoadImageFromNDArray"
    test_pipeline = Compose(cfg.test_dataloader.dataset.pipeline)

    class_names = list(model.dataset_meta.get("classes", ["tumor"]))

    # Image loading (BGR, OpenCV format)
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"[dino_runner] ERREUR : image introuvable : {image_path}", file=sys.stderr)
        sys.exit(1)

    bgr = cv2.imread(str(image_path))
    if bgr is None:
        print(f"[dino_runner] ERREUR : impossible de lire {image_path}", file=sys.stderr)
        sys.exit(1)

    # Inference
    with torch.no_grad():
        result = inference_detector(model, bgr, test_pipeline=test_pipeline)

    pred   = result.pred_instances
    bboxes = pred.bboxes.cpu().numpy()
    scores = pred.scores.cpu().numpy()
    labels = pred.labels.cpu().numpy()

    detections = [
        {
            "bbox":  [float(x) for x in bb],
            "score": float(sc),
            "label": (
                class_names[int(lb)] if int(lb) < len(class_names) else str(lb)
            ),
        }
        for bb, sc, lb in zip(bboxes, scores, labels)
        if sc >= args.score_thr
    ]

    # JSON write
    Path(args.out).write_text(
        json.dumps(detections, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[dino_runner] {len(detections)} détection(s) écrite(s) → {args.out}")


if __name__ == "__main__":
    main()
