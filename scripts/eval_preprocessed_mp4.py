#!/usr/bin/env python3
"""
eval_preprocessed_mp4.py — Évaluation batch sur les MP4 déjà préprocessés
==========================================================================
Les vidéos ont déjà subi prepUS — on passe les frames directement dans
STARHE-RISK (C3D) et STARHE-DETECT (RTMDet), sans aucun prétraitement
supplémentaire.

Usage :
    python scripts/eval_preprocessed_mp4.py \
        --input  /Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test \
        --output /Users/hugo/Desktop/STAGE/resultats_starhe.csv
"""

import argparse
import csv
import os
import sys
import time

import cv2
import numpy as np

# ── PYTHONPATH ────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MOD_PATH   = os.path.join(_SCRIPT_DIR, "..", "pythonCode", "modules")
if _MOD_PATH not in sys.path:
    sys.path.insert(0, _MOD_PATH)

# Redirect go_print to stderr (no Go protocol here)
from starhe_plugin.utils.go_print import set_log_sink

def _log(level: str, message: str) -> None:
    print(f"[{level.upper():8s}] {message}", file=sys.stderr, flush=True)

set_log_sink(_log)

from starhe_plugin.ai.starhe_risk   import STARHERiskModel
from starhe_plugin.ai.starhe_detect import STARHEDetectModel
from starhe_plugin.config           import DETECT_EVERY_N


CSV_FIELDS = [
    "fichier",
    "score_risque_chc",       # probabilité classe 1 (0–1)
    "risque_chc",             # Risque élevé / Risque faible
    "prob_classe_0",
    "prob_classe_1",
    "n_frames_total",
    "n_frames_avec_lesion",   # frames avec ≥1 bbox DETECT
    "n_detections_total",     # total des bboxes toutes frames confondues
    "duree_s",
    "erreur",
]


def read_mp4_frames(path: str) -> tuple[np.ndarray, float]:
    """Lit les frames d'un MP4. Retourne (frames_rgb uint8 (T,H,W,3), fps)."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir : {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 22.0
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()
    if not frames:
        raise RuntimeError("Aucune frame lisible.")
    return np.stack(frames), fps


def run_one(mp4_path: str, risk_model: STARHERiskModel) -> dict:
    name = os.path.splitext(os.path.basename(mp4_path))[0]
    t0   = time.perf_counter()

    try:
        # 1. Read frames — already preprocessed, go straight to the models
        _log("info", f"── {name} ── lecture…")
        frames, fps = read_mp4_frames(mp4_path)
        n_total = len(frames)
        _log("info", f"  {n_total} frames @ {fps:.1f} fps  {frames.shape[2]}×{frames.shape[1]} px")

        # 2. STARHE-RISK (C3D) — input: (T, H, W, 3) uint8 RGB
        _log("info", "  STARHE-RISK…")
        risk_result = risk_model.predict(frames)

        # 3. STARHE-DETECT (RTMDet) — input: list of frames (H, W, 3) uint8 RGB
        _log("info", "  STARHE-DETECT…")
        stride         = max(1, DETECT_EVERY_N)
        sampled        = list(range(0, n_total, stride))
        dets_per_frame = [[] for _ in range(n_total)]

        with STARHEDetectModel() as detect_model:
            bs = detect_model.batch_size
            for b_start in range(0, len(sampled), bs):
                batch_idx    = sampled[b_start : b_start + bs]
                batch_frames = [frames[i] for i in batch_idx]
                batch_dets   = detect_model.predict_batch(batch_frames)
                for idx, frame_dets in zip(batch_idx, batch_dets):
                    for j in range(idx, min(idx + stride, n_total)):
                        dets_per_frame[j] = frame_dets

        n_frames_with_lesion = sum(1 for d in dets_per_frame if d)
        n_detections_total   = sum(len(d) for d in dets_per_frame)

        elapsed = time.perf_counter() - t0
        _log("info",
             f"  ✓ score={risk_result['risk_score']:.4f} | {risk_result['risk_label']} | "
             f"{n_frames_with_lesion}/{n_total} frames lésion(s) | {elapsed:.1f}s")

        return {
            "fichier":              name,
            "score_risque_chc":     f"{risk_result['risk_score']:.6f}",
            "risque_chc":           risk_result["risk_label"],
            "prob_classe_0":        f"{risk_result['scores'][0]:.6f}",
            "prob_classe_1":        f"{risk_result['scores'][1]:.6f}",
            "n_frames_total":       n_total,
            "n_frames_avec_lesion": n_frames_with_lesion,
            "n_detections_total":   n_detections_total,
            "duree_s":              f"{elapsed:.1f}",
            "erreur":               "",
        }

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        _log("error", f"  ✗ {name} : {exc}")
        return {
            "fichier":              name,
            "score_risque_chc":     "",
            "risque_chc":           "",
            "prob_classe_0":        "",
            "prob_classe_1":        "",
            "n_frames_total":       "",
            "n_frames_avec_lesion": "",
            "n_detections_total":   "",
            "duree_s":              f"{elapsed:.1f}",
            "erreur":               str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", "-i",
        default="/Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test",
    )
    parser.add_argument(
        "--output", "-o",
        default="/Users/hugo/Desktop/STAGE/resultats_starhe.csv",
    )
    args = parser.parse_args()

    mp4_files = sorted(
        os.path.join(args.input, f)
        for f in os.listdir(args.input)
        if f.lower().endswith(".mp4")
    )
    if not mp4_files:
        print(f"Aucun .mp4 dans : {args.input}", file=sys.stderr)
        sys.exit(1)

    _log("info", f"{len(mp4_files)} fichier(s) → {args.output}")

    # C3D loaded only once (heavy)
    _log("info", "Chargement STARHE-RISK (C3D)…")
    risk_model = STARHERiskModel()

    rows = []
    for i, path in enumerate(mp4_files, 1):
        _log("info", f"\n[{i}/{len(mp4_files)}]")
        rows.append(run_one(path, risk_model))

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    _log("info", f"\n✓ CSV écrit : {args.output}")

    # Terminal summary
    ok  = [r for r in rows if not r["erreur"]]
    err = [r for r in rows if r["erreur"]]
    print(f"\n{'─'*65}", file=sys.stderr)
    print(f"{'Fichier':<28} {'Score':>8}  {'Label':<16}  {'Lésions':>12}", file=sys.stderr)
    print(f"{'─'*65}", file=sys.stderr)
    for r in ok:
        print(
            f"{r['fichier']:<28} {float(r['score_risque_chc']):>8.4f}  "
            f"{r['risque_chc']:<16}  "
            f"{r['n_frames_avec_lesion']:>4}/{r['n_frames_total']:<6}",
            file=sys.stderr,
        )
    if err:
        print("\nErreurs :", file=sys.stderr)
        for r in err:
            print(f"  {r['fichier']} : {r['erreur']}", file=sys.stderr)
    print(f"{'─'*65}", file=sys.stderr)


if __name__ == "__main__":
    main()
