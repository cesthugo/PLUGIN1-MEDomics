#!/usr/bin/env python3
"""
compare_detect_vs_reference.py — STARHE-DETECT : notre runner vs référence officielle
=======================================================================================
Compare, vidéo par vidéo, les détections produites par :
  • OFFICIEL : init_detector() + inference_detector() (API mmdet officielle,
               identique à starhe_share/.../video_demo.py)
  • NOTRE PROJET : ai/models/_rtmdet_runner.py (_build_model + _infer_one_frame)

Les deux chemins partagent le même checkpoint et le même patch NMS
(torchvision), donc le NMS n'est pas une variable de confusion : seules les
différences de prétraitement / appel modèle sont mesurées.

Échantillonnage : un frame sur DETECT_EVERY_N (config.py), comme en
production (pipeline.py) — pas une comparaison frame-par-frame exhaustive.

Usage :
    <venv>/bin/python scripts/compare_detect_vs_reference.py \\
        --input  /Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test \\
        --output /Users/hugo/Desktop/STAGE/comparaison_detect.csv
"""

import argparse
import csv
import glob
import importlib.machinery as _im
import importlib.util
import inspect as _inspect
import os
import sys
import time
import types

import cv2
import numpy as np

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MOD_PATH   = os.path.join(_SCRIPT_DIR, "..", "pythonCode", "modules")
if _MOD_PATH not in sys.path:
    sys.path.insert(0, _MOD_PATH)

_RUNNER_PATH = os.path.join(
    _MOD_PATH, "starhe_plugin", "ai", "models", "_rtmdet_runner.py"
)
_CONFIG = os.path.join(_MOD_PATH, "starhe_plugin", "models", "rtmdet_starhe.py")
_CKPT   = os.path.join(
    _MOD_PATH, "starhe_plugin", "models", "best_coco_bbox_mAP_50_iter_2100.pth"
)

from starhe_plugin.config import DETECT_EVERY_N, DETECT_SCORE_THRESHOLD


# ─── Stubs identiques à _rtmdet_runner.py (AVANT tout import mmcv/mmdet) ──────
if "mmcv._ext" not in sys.modules:
    class _CExtStub(types.ModuleType):
        def __getattr__(self, name):
            def _unavailable(*a, **kw):
                raise RuntimeError(f"mmcv._ext.{name}: C-extension absente.")
            return _unavailable
    _stub = _CExtStub("mmcv._ext")
    _stub.__spec__ = _im.ModuleSpec("mmcv._ext", loader=None)  # requis par init_detector
    sys.modules["mmcv._ext"] = _stub

try:
    import tqdm  # noqa: F401
except ImportError:
    _m = types.ModuleType("tqdm")
    _m.tqdm = lambda it=None, *a, **kw: (it if it is not None else iter([]))
    _m.__spec__ = _im.ModuleSpec("tqdm", None)
    _m_auto = types.ModuleType("tqdm.auto")
    _m_auto.tqdm = _m.tqdm
    _m_auto.__spec__ = _im.ModuleSpec("tqdm.auto", None)
    sys.modules.setdefault("tqdm", _m)
    sys.modules.setdefault("tqdm.auto", _m_auto)

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

import torch

_orig_torch_load = torch.load
def _patched_load(*a, **kw):
    kw.setdefault("weights_only", False)  # checkpoint local de confiance
    return _orig_torch_load(*a, **kw)
torch.load = _patched_load

import torchvision.ops as tv_ops
import mmcv.ops.nms  # noqa: F401
from mmcv.ops.nms import NMSop

def _tv_nms_fwd(ctx, bboxes, scores, iou_threshold, offset, score_threshold, max_num):
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
    return inds
NMSop.forward = staticmethod(_tv_nms_fwd)

from mmengine.structures.instance_data import InstanceData as _InstData
_orig_inst_getitem = _InstData.__getitem__
def _mps_safe_getitem(self, item):
    if isinstance(item, torch.Tensor) and item.device.type not in ("cpu", "cuda"):
        item = item.cpu()
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


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _load_models():
    """Construit le modèle officiel (init_detector) et notre runner."""
    from mmdet.apis import init_detector, inference_detector
    from mmcv.transforms import Compose

    _log("Chargement du modèle OFFICIEL (init_detector)…")
    official_model = init_detector(_CONFIG, _CKPT, device="cpu")
    pipeline_cfg = official_model.cfg.test_pipeline
    pipeline_cfg[0]["type"] = "LoadImageFromNDArray"
    test_pipeline = Compose(pipeline_cfg)

    _log("Chargement de NOTRE runner (_rtmdet_runner._build_model)…")
    spec = importlib.util.spec_from_file_location("_rtmdet_runner_cmp", _RUNNER_PATH)
    runner = importlib.util.module_from_spec(spec)
    sys.modules["_rtmdet_runner_cmp"] = runner
    spec.loader.exec_module(runner)
    our_model = runner._build_model(_CONFIG, _CKPT, "cpu")

    return official_model, inference_detector, test_pipeline, runner, our_model


def _iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _diff_stats(off, ours, score_floor=0.05):
    """Greedy IoU-matching (IoU > 0.5) au-dessus de score_floor."""
    off_f  = [d for d in off if d["score"] >= score_floor]
    ours_f = [d for d in ours if d["score"] >= score_floor]
    used = set()
    bbox_diffs, score_diffs = [], []
    unmatched_off = 0
    for od in off_f:
        best_j, best_iou = -1, 0.0
        for j, ud in enumerate(ours_f):
            if j in used:
                continue
            iou = _iou(od["bbox"], ud["bbox"])
            if iou > best_iou:
                best_iou, best_j = iou, j
        if best_j >= 0 and best_iou > 0.5:
            used.add(best_j)
            ud = ours_f[best_j]
            bbox_diffs.append(max(abs(a - b) for a, b in zip(od["bbox"], ud["bbox"])))
            score_diffs.append(abs(od["score"] - ud["score"]))
        else:
            unmatched_off += 1
    return {
        "n_candidates_official": len(off_f),
        "n_candidates_ours": len(ours_f),
        "n_matched": len(bbox_diffs),
        "n_unmatched_official": unmatched_off,
        "n_unmatched_ours": len(ours_f) - len(used),
        "max_bbox_diff": max(bbox_diffs) if bbox_diffs else 0.0,
        "max_score_diff": max(score_diffs) if score_diffs else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Compare STARHE-DETECT (notre projet) à la référence officielle "
                    "sur un dossier de vidéos MP4 préprocessées, et exporte un CSV récapitulatif."
    )
    parser.add_argument("--input", required=True,
                        help="Dossier contenant les .mp4 à comparer (ex: data_test)")
    parser.add_argument("--output", required=True,
                        help="Chemin du CSV de sortie")
    parser.add_argument("--score-thr", type=float, default=0.05,
                        help="Seuil minimum pour qu'une détection soit considérée "
                             "comme un 'candidat' réel (filtre le bruit float, défaut 0.05)")
    parser.add_argument("--stride", type=int, default=DETECT_EVERY_N,
                        help=f"Pas d'échantillonnage des frames (défaut DETECT_EVERY_N={DETECT_EVERY_N}, "
                             "identique à la production)")
    args = parser.parse_args()

    videos = sorted(glob.glob(os.path.join(args.input, "*.mp4")))
    if not videos:
        _log(f"Aucune vidéo .mp4 trouvée dans {args.input}")
        sys.exit(1)

    official_model, inference_detector, test_pipeline, runner, our_model = _load_models()

    rows = []
    t_start = time.time()

    for vid_path in videos:
        vid_name = os.path.basename(vid_path)
        cap = cv2.VideoCapture(vid_path)
        n_frames_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        sampled_idx = list(range(0, n_frames_total, max(1, args.stride)))
        n_det_frames_off = 0
        n_det_frames_ours = 0
        agg = {
            "n_candidates_official": 0, "n_candidates_ours": 0,
            "n_matched": 0, "n_unmatched_official": 0, "n_unmatched_ours": 0,
        }
        max_bbox_diff = 0.0
        max_score_diff = 0.0
        n_perfect_frames = 0

        idx_set = set(sampled_idx)
        i = 0
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                break
            if i in idx_set:
                result = inference_detector(official_model, frame_bgr, test_pipeline=test_pipeline)
                inst = result.pred_instances
                off_dets = [
                    {"bbox": [float(x) for x in bb], "score": float(sc)}
                    for bb, sc in zip(inst.bboxes.cpu().numpy(), inst.scores.cpu().numpy())
                    if sc >= 0.001
                ]
                ours_dets = runner._infer_one_frame(
                    our_model, frame_bgr, 0.001, "cpu", use_double=False
                )

                if any(d["score"] >= DETECT_SCORE_THRESHOLD for d in off_dets):
                    n_det_frames_off += 1
                if any(d["score"] >= DETECT_SCORE_THRESHOLD for d in ours_dets):
                    n_det_frames_ours += 1

                stats = _diff_stats(off_dets, ours_dets, score_floor=args.score_thr)
                for k in agg:
                    agg[k] += stats[k]
                max_bbox_diff = max(max_bbox_diff, stats["max_bbox_diff"])
                max_score_diff = max(max_score_diff, stats["max_score_diff"])
                if (stats["n_unmatched_official"] == 0 and stats["n_unmatched_ours"] == 0
                        and stats["max_bbox_diff"] == 0.0 and stats["max_score_diff"] == 0.0):
                    n_perfect_frames += 1
            i += 1
        cap.release()

        n_sampled = len(sampled_idx)
        statut = "IDENTIQUE" if n_perfect_frames == n_sampled else "DIFFERENT"

        rows.append({
            "video": vid_name,
            "n_frames_total": n_frames_total,
            "n_frames_analyses": n_sampled,
            "n_frames_avec_detection_officiel": n_det_frames_off,
            "n_frames_avec_detection_notre_projet": n_det_frames_ours,
            "n_candidats_officiel": agg["n_candidates_official"],
            "n_candidats_notre_projet": agg["n_candidates_ours"],
            "n_appaires": agg["n_matched"],
            "n_non_appaires_officiel": agg["n_unmatched_official"],
            "n_non_appaires_notre_projet": agg["n_unmatched_ours"],
            "max_diff_bbox_px": round(max_bbox_diff, 6),
            "max_diff_score": round(max_score_diff, 8),
            "frames_bit_exactes": f"{n_perfect_frames}/{n_sampled}",
            "statut": statut,
        })
        _log(f"[{statut:9s}] {vid_name:20s} "
             f"{n_perfect_frames}/{n_sampled} frames bit-exactes "
             f"(max_bbox_diff={max_bbox_diff:.4f}px, max_score_diff={max_score_diff:.6f}) "
             f"— det. officiel={n_det_frames_off}, det. notre projet={n_det_frames_ours}")

    # ── Ligne récapitulative GLOBAL ────────────────────────────────────────────
    total_sampled  = sum(r["n_frames_analyses"] for r in rows)
    total_perfect  = sum(int(r["frames_bit_exactes"].split("/")[0]) for r in rows)
    rows.append({
        "video": "TOTAL",
        "n_frames_total": sum(r["n_frames_total"] for r in rows),
        "n_frames_analyses": total_sampled,
        "n_frames_avec_detection_officiel": sum(r["n_frames_avec_detection_officiel"] for r in rows),
        "n_frames_avec_detection_notre_projet": sum(r["n_frames_avec_detection_notre_projet"] for r in rows),
        "n_candidats_officiel": sum(r["n_candidats_officiel"] for r in rows),
        "n_candidats_notre_projet": sum(r["n_candidats_notre_projet"] for r in rows),
        "n_appaires": sum(r["n_appaires"] for r in rows),
        "n_non_appaires_officiel": sum(r["n_non_appaires_officiel"] for r in rows),
        "n_non_appaires_notre_projet": sum(r["n_non_appaires_notre_projet"] for r in rows),
        "max_diff_bbox_px": round(max((r["max_diff_bbox_px"] for r in rows), default=0.0), 6),
        "max_diff_score": round(max((r["max_diff_score"] for r in rows), default=0.0), 8),
        "frames_bit_exactes": f"{total_perfect}/{total_sampled}",
        "statut": "IDENTIQUE" if total_perfect == total_sampled else "DIFFERENT",
    })

    fieldnames = list(rows[0].keys())
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    elapsed = time.time() - t_start
    _log(f"\nCSV écrit : {args.output} ({len(rows) - 1} vidéos + 1 ligne TOTAL, {elapsed:.0f}s)")


if __name__ == "__main__":
    main()
