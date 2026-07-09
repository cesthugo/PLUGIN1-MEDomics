#!/usr/bin/env python3
"""
validate_dicom_detect.py — Validation pipeline DICOM complet (DETECT)
======================================================================
Pour chaque DICOM correspondant à un patient de data_test :

  Chemin A (DICOM) :
    DICOM → Weasis (LUT) → frames RGB → prepUS → crop_only_frames → DETECT

  Chemin B (data_test référence) :
    data_test MP4 (déjà cropé par prepUS d'Adrien) → frames RGB → DETECT

Métriques comparées :
  - n_frames              : nombre total de frames de la vidéo
  - n_analysed            : frames effectivement envoyées au modèle (stride DETECT_EVERY_N)
  - n_detected_frames     : frames (samplées) avec au moins 1 détection
  - detection_rate        : n_detected_frames / n_analysed
  - mean_max_score        : moyenne du score max par frame samplée (0 si aucune détection)
  - max_score_overall     : score de confiance le plus élevé trouvé dans toute la vidéo
  - has_detection / label : "Détection" ou "Pas de détection"

"labels_identiques" : les deux chemins s'accordent sur has_detection.

Usage :
    python scripts/validate_dicom_detect.py \\
        --dicom_dir /Users/hugo/Desktop/STAGE/Testing/datasetDICOM \\
        --data_test /Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test \\
        --output    scripts/results/validation_dicom_detect.csv \\
        [--patient  01-0006]   # traiter un seul patient pour tester
"""

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
_MOD_PATH   = _SCRIPT_DIR.parent / "pythonCode" / "modules"
if str(_MOD_PATH) not in sys.path:
    sys.path.insert(0, str(_MOD_PATH))

from starhe_plugin.utils.go_print import set_log_sink

def _log(level: str, msg: str) -> None:
    print(f"[{level.upper():8s}] {msg}", file=sys.stderr, flush=True)

set_log_sink(_log)

from starhe_plugin.dicom.reader        import load_dicom, extract_frames, frame_to_uint8
from starhe_plugin.dicom.weasis_bridge import weasis_available, frames_via_weasis
from starhe_plugin.dicom.prepus_bridge import preprocess_with_prepus_inmem
from starhe_plugin.ai.starhe_detect    import STARHEDetectModel
from starhe_plugin.config              import USE_WEASIS_EXPORT, DETECT_EVERY_N, DETECT_SCORE_THRESHOLD

DEFAULT_DICOM_DIR = "/Users/hugo/Desktop/STAGE/Testing/datasetDICOM"
DEFAULT_DATA_TEST = "/Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test"
DEFAULT_OUTPUT    = str(_SCRIPT_DIR / "results" / "validation_dicom_detect.csv")


# ── Helpers ────────────────────────────────────────────────────────────────────

def patient_id(name: str) -> str:
    m = re.search(r"(\d{2}-\d{4})", name)
    return m.group(1) if m else name


def read_mp4_frames(path: str) -> np.ndarray:
    """Lit un fichier MP4 et retourne (T, H, W, 3) uint8 RGB."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir : {path}")
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()
    if not frames:
        raise RuntimeError("Aucune frame lisible.")
    return np.stack(frames)


def dicom_to_detect_frames(dcm_path: str) -> tuple[np.ndarray, dict | None]:
    """
    DICOM → Weasis → frames RGB → prepUS (inmem) → frames 3ch pour DETECT.
    Retourne (frames_3ch, info) où frames_3ch est (T, H_crop, W_crop, 3).
    """
    ds = load_dicom(dcm_path)

    rdp = float(getattr(ds, "RecommendedDisplayFrameRate", 0))
    cr  = float(getattr(ds, "CineRate", 0))
    ft  = float(getattr(ds, "FrameTime", 0))
    if rdp > 0:
        fps = rdp
    elif cr > 0:
        fps = cr
    elif ft > 0:
        fps = 1000.0 / ft
    else:
        fps = 22.0

    frames_rgb = None
    if USE_WEASIS_EXPORT and weasis_available():
        try:
            frames_rgb, fps_w = frames_via_weasis(dcm_path)
            if fps_w > 0:
                fps = fps_w
        except Exception as exc:
            _log("warning", f"Weasis échoué ({exc}) — fallback pydicom")
            frames_rgb = None

    if frames_rgb is None:
        frames_raw  = extract_frames(ds)
        frames_norm = np.stack([frame_to_uint8(f) for f in frames_raw])
        if frames_norm.ndim == 3:
            frames_rgb = np.stack([frames_norm] * 3, axis=-1)
        else:
            frames_rgb = frames_norm

    # prepUS → crop_only_frames (T, H_crop, W_crop) uint8 niveaux de gris
    crop_gray, info = preprocess_with_prepus_inmem(frames_rgb, fps=fps)

    # Same conversion as pipeline.py: grayscale → pseudo-RGB 3 channels
    frames_3ch = np.stack([crop_gray, crop_gray, crop_gray], axis=-1)
    return frames_3ch, info


def run_detect_on_frames(
    frames_3ch: np.ndarray,
    detect_model: STARHEDetectModel,
    stride: int,
) -> dict:
    """
    Lance DETECT sur les frames samplées (stride).
    Retourne un dict avec toutes les métriques.
    """
    n_frames   = len(frames_3ch)
    sampled_idx = list(range(0, n_frames, stride))
    sampled_frames = [frames_3ch[i] for i in sampled_idx]
    n_analysed = len(sampled_frames)

    # Batch inference
    batch_dets = detect_model.predict_batch(sampled_frames,
                                            score_thr=DETECT_SCORE_THRESHOLD)

    # Compute the metrics on the sampled frames only
    n_detected = 0
    max_scores = []
    for dets in batch_dets:
        if dets:
            n_detected += 1
            max_scores.append(max(d["score"] for d in dets))
        else:
            max_scores.append(0.0)

    detection_rate   = n_detected / n_analysed if n_analysed else 0.0
    mean_max_score   = float(np.mean(max_scores)) if max_scores else 0.0
    max_score_overall = float(max(max_scores)) if max_scores else 0.0
    has_detection    = n_detected > 0

    return {
        "n_frames":         n_frames,
        "n_analysed":       n_analysed,
        "n_detected_frames": n_detected,
        "detection_rate":   round(detection_rate, 4),
        "mean_max_score":   round(mean_max_score, 6),
        "max_score_overall": round(max_score_overall, 6),
        "has_detection":    has_detection,
        "label":            "Détection" if has_detection else "Pas de détection",
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dicom_dir", "-d", default=DEFAULT_DICOM_DIR)
    parser.add_argument("--data_test", "-t", default=DEFAULT_DATA_TEST)
    parser.add_argument("--output",    "-o", default=DEFAULT_OUTPUT)
    parser.add_argument("--patient",   "-p", default=None,
                        help="Traiter uniquement ce patient (ex: 01-0006)")
    args = parser.parse_args()

    ref_mp4s = {
        patient_id(f): os.path.join(args.data_test, f)
        for f in os.listdir(args.data_test)
        if f.endswith(".mp4")
    }
    _log("info", f"Références data_test : {len(ref_mp4s)} patients")

    dcm_files = {
        patient_id(f): os.path.join(args.dicom_dir, f)
        for f in os.listdir(args.dicom_dir)
        if f.lower().endswith((".dcm", ".avi"))
    }

    common = sorted(set(ref_mp4s) & set(dcm_files))
    if args.patient:
        common = [p for p in common if args.patient in p]
    _log("info", f"Patients communs DICOM ∩ data_test : {len(common)}")

    stride = max(1, DETECT_EVERY_N)
    _log("info", f"DETECT_EVERY_N={stride}, DETECT_SCORE_THRESHOLD={DETECT_SCORE_THRESHOLD}")

    _log("info", "Chargement STARHE-DETECT (RTMDet)…")
    detect_model = STARHEDetectModel()

    CSV_FIELDS = [
        "patient",
        # Chemin A — DICOM → prepUS → DETECT
        "n_frames_dicom", "n_analysed_dicom",
        "n_detected_dicom", "detection_rate_dicom",
        "mean_max_score_dicom", "max_score_dicom",
        "label_dicom",
        # Chemin B — data_test → DETECT
        "n_frames_ref", "n_analysed_ref",
        "n_detected_ref", "detection_rate_ref",
        "mean_max_score_ref", "max_score_ref",
        "label_ref",
        # Comparaison
        "labels_identiques",
        "delta_detection_rate",
        "delta_mean_score",
        # Meta
        "duree_s", "erreur",
    ]

    rows   = []
    agreed = 0

    with detect_model:
        for pid in common:
            dcm_path = dcm_files[pid]
            ref_path = ref_mp4s[pid]
            _log("info", f"── {pid} ──")
            row = {"patient": pid, "erreur": ""}
            t0  = time.time()

            try:
                # ── Chemin A : DICOM → prepUS → DETECT ──────────────────────
                _log("info", f"  [A] DICOM → prepUS…")
                frames_dicom, _info = dicom_to_detect_frames(dcm_path)
                metrics_dicom = run_detect_on_frames(frames_dicom, detect_model, stride)

                _log("info",
                     f"  [A] {metrics_dicom['n_frames']} frames, "
                     f"{metrics_dicom['n_analysed']} analysées, "
                     f"{metrics_dicom['n_detected_frames']} détectées "
                     f"({metrics_dicom['detection_rate']*100:.1f}%) "
                     f"label={metrics_dicom['label']}")

                # ── Chemin B : data_test → DETECT ───────────────────────────
                _log("info", f"  [B] data_test MP4…")
                frames_ref     = read_mp4_frames(ref_path)
                # Ensure 3 channels (data_test may be read as grayscale)
                if frames_ref.ndim == 3:
                    frames_ref = np.stack([frames_ref]*3, axis=-1)
                metrics_ref = run_detect_on_frames(frames_ref, detect_model, stride)

                _log("info",
                     f"  [B] {metrics_ref['n_frames']} frames, "
                     f"{metrics_ref['n_analysed']} analysées, "
                     f"{metrics_ref['n_detected_frames']} détectées "
                     f"({metrics_ref['detection_rate']*100:.1f}%) "
                     f"label={metrics_ref['label']}")

                labels_ok = metrics_dicom["label"] == metrics_ref["label"]
                if labels_ok:
                    agreed += 1

                row.update({
                    "n_frames_dicom":       metrics_dicom["n_frames"],
                    "n_analysed_dicom":     metrics_dicom["n_analysed"],
                    "n_detected_dicom":     metrics_dicom["n_detected_frames"],
                    "detection_rate_dicom": metrics_dicom["detection_rate"],
                    "mean_max_score_dicom": metrics_dicom["mean_max_score"],
                    "max_score_dicom":      metrics_dicom["max_score_overall"],
                    "label_dicom":          metrics_dicom["label"],

                    "n_frames_ref":         metrics_ref["n_frames"],
                    "n_analysed_ref":       metrics_ref["n_analysed"],
                    "n_detected_ref":       metrics_ref["n_detected_frames"],
                    "detection_rate_ref":   metrics_ref["detection_rate"],
                    "mean_max_score_ref":   metrics_ref["mean_max_score"],
                    "max_score_ref":        metrics_ref["max_score_overall"],
                    "label_ref":            metrics_ref["label"],

                    "labels_identiques":      "OUI" if labels_ok else "NON",
                    "delta_detection_rate":   round(
                        metrics_dicom["detection_rate"] - metrics_ref["detection_rate"], 4),
                    "delta_mean_score":       round(
                        metrics_dicom["mean_max_score"] - metrics_ref["mean_max_score"], 6),
                    "duree_s": round(time.time() - t0, 1),
                })

            except Exception as exc:
                _log("error", f"  {pid} : {exc}")
                row.update({
                    "erreur": str(exc),
                    "duree_s": round(time.time() - t0, 1),
                })

            rows.append(row)
            _log("info", f"  → labels_identiques={row.get('labels_identiques','ERR')} "
                         f"({row.get('duree_s','?')}s)")

    # ── Écriture CSV ──────────────────────────────────────────────────────────
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ── Summary ───────────────────────────────────────────────────────────────
    ok_rows = [r for r in rows if not r.get("erreur")]
    n_ok    = len(ok_rows)
    _log("info", "")
    _log("info", f"{'='*60}")
    _log("info", f"RÉSUMÉ  —  {n_ok}/{len(common)} patients traités")
    _log("info", f"  Labels identiques : {agreed}/{n_ok}")
    if n_ok:
        rates_dicom = [r["detection_rate_dicom"] for r in ok_rows]
        rates_ref   = [r["detection_rate_ref"]   for r in ok_rows]
        _log("info", f"  detection_rate moyen DICOM : {np.mean(rates_dicom)*100:.1f}%")
        _log("info", f"  detection_rate moyen REF   : {np.mean(rates_ref)*100:.1f}%")
        divergences = [r["patient"] for r in ok_rows if r["labels_identiques"] == "NON"]
        if divergences:
            _log("warning", f"  Divergences label : {', '.join(divergences)}")
    _log("info", f"  CSV : {args.output}")
    _log("info", f"{'='*60}")


if __name__ == "__main__":
    main()
