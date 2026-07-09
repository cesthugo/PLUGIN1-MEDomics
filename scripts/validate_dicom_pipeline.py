#!/usr/bin/env python3
"""
validate_dicom_pipeline.py — Validation pipeline DICOM complet (RISK)
======================================================================
Pour chaque DICOM correspondant à un patient de data_test :
  1. Charge le DICOM (Weasis ou pydicom fallback)
  2. Applique prepUS (mpeg4 roundtrip)
  3. Lance STARHE-RISK sur les frames croppées
  4. Compare avec le score de référence (data_test MP4 → RISK)

Objectif : vérifier que le pipeline DICOM produit des scores identiques
(ou très proches) à ceux obtenus depuis les MP4 data_test préprocessés.

Usage :
    python scripts/validate_dicom_pipeline.py \\
        --dicom_dir /Users/hugo/Desktop/STAGE/Testing/datasetDICOM \\
        --data_test /Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test \\
        --output    scripts/results/validation_dicom_pipeline.csv
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

from starhe_plugin.dicom.reader          import load_dicom, extract_frames, frame_to_uint8
from starhe_plugin.dicom.weasis_bridge   import weasis_available, frames_via_weasis
from starhe_plugin.dicom.prepus_bridge   import preprocess_with_prepus
from starhe_plugin.ai.starhe_risk        import STARHERiskModel
from starhe_plugin.config                import USE_WEASIS_EXPORT

DEFAULT_DICOM_DIR = "/Users/hugo/Desktop/STAGE/Testing/datasetDICOM"
DEFAULT_DATA_TEST = "/Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test"
DEFAULT_OUTPUT    = str(_SCRIPT_DIR / "results" / "validation_dicom_pipeline.csv")


def read_mp4_frames(path: str) -> np.ndarray:
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


def patient_id(name: str) -> str:
    m = re.search(r"(\d{2}-\d{4})", name)
    return m.group(1) if m else name


def dicom_to_crop_frames(dcm_path: str) -> tuple[np.ndarray, dict | None]:
    """Charge DICOM → frames RGB → prepUS → crop_only_frames."""
    ds = load_dicom(dcm_path)

    # FPS
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

    crop_frames, info = preprocess_with_prepus(frames_rgb, fps=fps)
    return crop_frames, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dicom_dir", "-d", default=DEFAULT_DICOM_DIR)
    parser.add_argument("--data_test", "-t", default=DEFAULT_DATA_TEST)
    parser.add_argument("--output",    "-o", default=DEFAULT_OUTPUT)
    parser.add_argument("--patient",   "-p", default=None,
                        help="Traiter uniquement ce patient (ex: 01-0006)")
    args = parser.parse_args()

    # List the data_test files to get the references
    ref_mp4s = {
        patient_id(f): os.path.join(args.data_test, f)
        for f in os.listdir(args.data_test)
        if f.endswith(".mp4")
    }
    _log("info", f"Références data_test : {len(ref_mp4s)} patients")

    # List the available DICOMs
    dcm_files = {
        patient_id(f): os.path.join(args.dicom_dir, f)
        for f in os.listdir(args.dicom_dir)
        if f.lower().endswith((".dcm", ".avi"))
    }

    # Intersection: patients with DICOM AND data_test reference
    common = sorted(set(ref_mp4s) & set(dcm_files))
    if args.patient:
        common = [p for p in common if args.patient in p]
    _log("info", f"Patients communs DICOM ∩ data_test : {len(common)}")

    _log("info", "Chargement STARHE-RISK…")
    risk_model = STARHERiskModel()

    CSV_FIELDS = [
        "patient", "n_frames_dicom", "n_frames_ref",
        "score_dicom", "label_dicom",
        "score_ref",   "label_ref",
        "delta_score", "labels_identiques", "duree_s", "erreur",
    ]

    rows = []
    for idx, pid in enumerate(common, 1):
        _log("info", f"\n[{idx}/{len(common)}] {pid}")
        row = dict.fromkeys(CSV_FIELDS, "")
        row["patient"] = pid

        try:
            # ── Score from data_test MP4 (reference) ───────────────────────
            ref_frames = read_mp4_frames(ref_mp4s[pid])
            row["n_frames_ref"] = len(ref_frames)
            c_ref = np.stack([ref_frames[:, :, :, 0]] * 3 if ref_frames.ndim == 4
                              else [ref_frames] * 3, axis=-1) \
                    if ref_frames.ndim == 3 else ref_frames
            # data_test frames are already RGB pseudo-gray (R=G=B)
            r_ref = risk_model.predict(ref_frames)

            # ── Score from the DICOM pipeline ──────────────────────────────
            t0 = time.perf_counter()
            crop_frames, _ = dicom_to_crop_frames(dcm_files[pid])
            row["n_frames_dicom"] = len(crop_frames)
            # Convert (T, H_crop, W_crop) grayscale → pseudo-RGB (R=G=B)
            frames_rgb = np.stack([crop_frames, crop_frames, crop_frames], axis=-1)
            r_dcm = risk_model.predict(frames_rgb)
            elapsed = time.perf_counter() - t0

            delta = r_dcm["risk_score"] - r_ref["risk_score"]
            same  = "OUI" if r_dcm["risk_label"] == r_ref["risk_label"] else "NON"

            row.update({
                "score_dicom":       f"{r_dcm['risk_score']:.6f}",
                "label_dicom":       r_dcm["risk_label"],
                "score_ref":         f"{r_ref['risk_score']:.6f}",
                "label_ref":         r_ref["risk_label"],
                "delta_score":       f"{delta:+.6f}",
                "labels_identiques": same,
                "duree_s":           f"{elapsed:.1f}",
            })
            marker = "✓" if same == "OUI" else "✗ DIVERGENCE"
            _log("info",
                 f"  DICOM={r_dcm['risk_score']:.4f} [{r_dcm['risk_label']}]  "
                 f"REF={r_ref['risk_score']:.4f} [{r_ref['risk_label']}]  "
                 f"Δ={delta:+.4f}  {marker}")

        except Exception as exc:
            _log("error", f"  Erreur {pid} : {exc}")
            row["erreur"] = str(exc)

        rows.append(row)

    risk_model.close()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    ok = [r for r in rows if not r["erreur"] and r["score_dicom"]]
    same = [r for r in ok if r["labels_identiques"] == "OUI"]
    deltas = [abs(float(r["delta_score"])) for r in ok]

    print(f"\n{'─'*80}", file=sys.stderr)
    print(f"{'Patient':<14} {'DICOM score':>12}  {'Ref score':>12}  {'|Δ|':>8}  "
          f"{'Label ok':>8}", file=sys.stderr)
    print(f"{'─'*80}", file=sys.stderr)
    for r in ok:
        print(f"{r['patient']:<14} {r['score_dicom']:>12}  {r['score_ref']:>12}  "
              f"{r['abs_delta'] if 'abs_delta' in r else abs(float(r['delta_score'])):>8.6f}  "
              f"{'✓' if r['labels_identiques']=='OUI' else '✗'}", file=sys.stderr)
    print(f"{'─'*80}", file=sys.stderr)
    if ok:
        print(f"Labels identiques : {len(same)}/{len(ok)}  ({100*len(same)/len(ok):.0f}%)",
              file=sys.stderr)
        print(f"|Δ| moyen : {np.mean(deltas):.4f}  max : {np.max(deltas):.4f}",
              file=sys.stderr)
    print(f"\n✓ CSV : {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
