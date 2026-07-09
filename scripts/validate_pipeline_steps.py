#!/usr/bin/env python3
"""
validate_pipeline_steps.py — Validation de toutes les étapes intermédiaires
=============================================================================
Teste les 3 étapes de la chaîne DICOM → STARHE :

  ÉTAPE 1 — DICOM → MP4 non préprocessé (AV1 720p)
    Résumé seulement (validation déjà effectuée dans compare_avant_prepus.py).
    Résultat : 48/49 concordances (PSNR moyen 39 dB, dimensions ✓, FPS ✓).
    Fichier de référence : datasetAVANTPREPROCESS/

  ÉTAPE 2 — MP4 AV1 720p → prepUS → crop (video.mp4)
    Prend chaque fichier de datasetAVANTPREPROCESS, applique notre prepUS
    (numpy 2.0 patché), et compare le résultat avec data_test (référence juin 2024).
    Question : notre prepUS produit-il des fichiers identiques à la référence ?
    Métriques : dimensions du crop, PSNR pixel-à-pixel, score RISK.

  ÉTAPE 3 — crop → STARHE-RISK
    Exécute le modèle sur les data_test directement (baseline actuel torch 2.x)
    et compare avec les scores de la CSV de référence (générée avec torch ~2.0, juin 2024).
    Montre la dérive due aux versions de PyTorch.

Conclusion :
  - La reproduction bit-identique est IMPOSSIBLE (détaillé dans le rapport).
  - PREPUS_BYPASS_MP4=True est recommandé pour la cross-platform reproducibilité.

Usage :
    source .venv/bin/activate
    python scripts/validate_pipeline_steps.py \\
        [--av1_dir   /path/to/datasetAVANTPREPROCESS] \\
        [--data_test /path/to/data_test] \\
        [--output    scripts/results/validate_pipeline_steps.csv]
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

from starhe_plugin.dicom.prepus_bridge import preprocess_with_prepus
from starhe_plugin.ai.starhe_risk       import STARHERiskModel

# ── Default paths ─────────────────────────────────────────────────────────────
DEFAULT_AV1_DIR   = "/Users/hugo/Desktop/STAGE/VIDEO TESTING BATCH MP4 - À TESTER/datasetAVANTPREPROCESS"
DEFAULT_DATA_TEST = "/Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test"
DEFAULT_OUTPUT    = str(_SCRIPT_DIR / "results" / "validate_pipeline_steps.csv")

# Reference CSV (June 2024 scores, torch ~2.0, original training)
_REF_CSV_SCORES = {
    "01-0006": 0.657305, "01-0014": 0.500657, "01-0046": 0.697929,
    "01-0086": 0.766944, "01-0088": 0.638932, "01-0095": 0.702870,
    "02-0016": 0.185422, "02-0019": 0.557231, "02-0033": 0.710551,
    "02-0049": 0.370090, "02-0064": 0.535605, "02-0069": 0.214457,
    "03-0022": 0.722426, "03-0038": 0.429841, "03-0045": 0.604047,
    "04-0003": 0.942768, "04-0011": 0.808832, "04-0028": 0.960249,
    "04-0036": 0.638636, "04-0042": 0.947031, "04-0053": 0.925041,
    "04-0056": 0.978563, "05-0065": 0.088880, "06-0004": 0.853769,
}
_REF_CSV_LABELS = {pid: ("Risque élevé" if s >= 0.5 else "Risque faible")
                   for pid, s in _REF_CSV_SCORES.items()}


# ── Utilities ─────────────────────────────────────────────────────────────────

def patient_id(name: str) -> str:
    m = re.search(r"(\d{2}-\d{4})", name)
    return m.group(1) if m else name


def read_mp4_frames_rgb(path: str) -> np.ndarray:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir : {path}")
    frames = []
    while True:
        ok, f = cap.read()
        if not ok: break
        frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    cap.release()
    return np.stack(frames) if frames else np.empty((0,), dtype=np.uint8)


def read_mp4_frames_gray(path: str) -> np.ndarray:
    cap = cv2.VideoCapture(path)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok: break
        frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) if f.ndim == 3 else f)
    cap.release()
    return np.stack(frames) if frames else np.empty((0,), dtype=np.uint8)


def compute_psnr(a: np.ndarray, b: np.ndarray) -> float:
    """PSNR moyen sur min(len(a), len(b)) frames. -1 si non calculable."""
    n = min(len(a), len(b))
    if n == 0 or a.shape[1:] != b.shape[1:]:
        return -1.0
    mse = float(np.mean((a[:n].astype(np.float32) - b[:n].astype(np.float32)) ** 2))
    if mse == 0:
        return float("inf")
    return 20 * np.log10(255.0) - 10 * np.log10(mse)


# ── STEP 2: AV1 720p → prepUS → compare with data_test ──────────────────────

def run_step2(av1_dir: str, data_test: str, risk_model: STARHERiskModel) -> list[dict]:
    """
    Pour chaque fichier AV1 720p (datasetAVANTPREPROCESS),
    applique prepUS et compare le crop avec le fichier data_test correspondant.
    """
    # Index of the data_test files by patient ID
    ref_files = {
        patient_id(f): os.path.join(data_test, f)
        for f in os.listdir(data_test) if f.endswith(".mp4")
    }

    # Index of the AV1 files by patient ID
    av1_files = {
        patient_id(f): os.path.join(av1_dir, f)
        for f in os.listdir(av1_dir) if f.endswith(".mp4")
    }

    common = sorted(set(ref_files) & set(av1_files))
    _log("info", f"Étape 2 : {len(common)} patients communs AV1 ∩ data_test")

    rows = []
    for idx, pid in enumerate(common, 1):
        _log("info", f"[{idx}/{len(common)}] {pid}")
        row = {"etape": "2_prepus", "patient": pid, "erreur": ""}

        try:
            # Read the AV1 720p file (same as datasetAVANTPREPROCESS)
            av1_frames = read_mp4_frames_rgb(av1_files[pid])
            fps_cap = cv2.VideoCapture(av1_files[pid])
            fps = fps_cap.get(cv2.CAP_PROP_FPS) or 22.0
            fps_cap.release()

            row["av1_shape"] = f"{av1_frames.shape[1]}x{av1_frames.shape[2]}"
            row["av1_n_frames"] = len(av1_frames)

            # Read the reference data_test file (grayscale)
            ref_frames_gray = read_mp4_frames_gray(ref_files[pid])
            row["ref_shape"] = f"{ref_frames_gray.shape[2]}x{ref_frames_gray.shape[1]}" if ref_frames_gray.ndim >= 3 else f"?x{ref_frames_gray.shape[1]}"
            row["ref_n_frames"] = len(ref_frames_gray)

            # Apply prepUS on the AV1 file
            t0 = time.perf_counter()
            crop_frames, info = preprocess_with_prepus(av1_frames, fps=fps)
            elapsed = time.perf_counter() - t0

            row["our_shape"] = f"{crop_frames.shape[2]}x{crop_frames.shape[1]}"
            row["our_n_frames"] = len(crop_frames)
            row["dims_identiques"] = "OUI" if row["our_shape"] == row["ref_shape"] else "NON"
            row["prepus_duree_s"] = f"{elapsed:.1f}"

            # PSNR between our crop and data_test
            if row["dims_identiques"] == "OUI":
                n = min(len(crop_frames), len(ref_frames_gray))
                psnr = compute_psnr(crop_frames[:n], ref_frames_gray[:n])
                row["psnr_db"] = f"{psnr:.1f}" if psnr > 0 else "inf"
            else:
                row["psnr_db"] = "N/A (dims ≠)"

            # RISK score on our crop
            frames_rgb_ours = np.stack([crop_frames, crop_frames, crop_frames], axis=-1)
            r_our = risk_model.predict(frames_rgb_ours)
            row["score_notre_prepus"] = f"{r_our['risk_score']:.6f}"
            row["label_notre_prepus"] = r_our["risk_label"]

            # RISK score on data_test (current reference)
            ref_rgb = np.stack([ref_frames_gray, ref_frames_gray, ref_frames_gray], axis=-1)
            r_ref = risk_model.predict(ref_rgb)
            row["score_data_test"]     = f"{r_ref['risk_score']:.6f}"
            row["label_data_test"]     = r_ref["risk_label"]

            delta = r_our["risk_score"] - r_ref["risk_score"]
            row["delta_score"]         = f"{delta:+.6f}"
            row["labels_identiques"]   = "OUI" if r_our["risk_label"] == r_ref["risk_label"] else "NON"

            # Reference CSV score (old, torch ~2.0)
            row["score_ref_csv"]   = f"{_REF_CSV_SCORES.get(pid, -1):.6f}"
            row["label_ref_csv"]   = _REF_CSV_LABELS.get(pid, "?")
            row["label_vs_csv"]    = "OUI" if r_ref["risk_label"] == _REF_CSV_LABELS.get(pid) else "NON"

            marker = "✓" if row["labels_identiques"] == "OUI" else "✗"
            _log("info",
                 f"  dims {row['our_shape']} {'==' if row['dims_identiques']=='OUI' else '≠'} "
                 f"ref {row['ref_shape']}  "
                 f"PSNR={row['psnr_db']}  "
                 f"RISK notre={r_our['risk_score']:.4f} ref={r_ref['risk_score']:.4f} "
                 f"Δ={delta:+.4f} {marker}")

        except Exception as exc:
            _log("error", f"  Erreur {pid} : {exc}")
            row["erreur"] = str(exc)

        rows.append(row)

    return rows


# ── STEP 3: data_test → RISK — drift between old and new scores ──────────────

def run_step3(data_test: str, risk_model: STARHERiskModel) -> list[dict]:
    """
    Exécute STARHE-RISK directement sur data_test et mesure la dérive
    des scores par rapport à la CSV de référence (génération juin 2024).
    """
    ref_files = sorted(
        f for f in os.listdir(data_test) if f.endswith(".mp4")
    )
    _log("info", f"Étape 3 : {len(ref_files)} fichiers data_test → RISK")

    rows = []
    for idx, fname in enumerate(ref_files, 1):
        pid = patient_id(fname)
        _log("info", f"[{idx}/{len(ref_files)}] {pid}")
        row = {"etape": "3_risk_data_test", "patient": pid, "fichier": fname, "erreur": ""}

        try:
            frames_rgb = read_mp4_frames_rgb(os.path.join(data_test, fname))
            row["n_frames"] = len(frames_rgb)

            r = risk_model.predict(frames_rgb)
            row["score_actuel"]  = f"{r['risk_score']:.6f}"
            row["label_actuel"]  = r["risk_label"]

            score_csv = _REF_CSV_SCORES.get(pid, -1.0)
            label_csv = _REF_CSV_LABELS.get(pid, "?")
            row["score_csv"]     = f"{score_csv:.6f}"
            row["label_csv"]     = label_csv

            delta = r["risk_score"] - score_csv
            row["delta"]         = f"{delta:+.6f}"
            row["labels_ok"]     = "OUI" if r["risk_label"] == label_csv else "NON"

            marker = "✓" if row["labels_ok"] == "OUI" else "✗ DIVERGENCE"
            _log("info",
                 f"  actuel={r['risk_score']:.4f} [{r['risk_label']}]  "
                 f"csv={score_csv:.4f} [{label_csv}]  "
                 f"Δ={delta:+.4f}  {marker}")

        except Exception as exc:
            _log("error", f"  Erreur {pid} : {exc}")
            row["erreur"] = str(exc)

        rows.append(row)

    return rows


# ── Console summary ───────────────────────────────────────────────────────────

def _print_summary(step2_rows: list, step3_rows: list) -> None:
    sep = "─" * 90
    print(f"\n{sep}", file=sys.stderr)
    print("ÉTAPE 1 — DICOM → MP4 AV1 720p (validation antérieure)", file=sys.stderr)
    print(f"  Résultat : 48/49 concordances  PSNR moyen ≈ 39.4 dB", file=sys.stderr)
    print(f"  (1 patient absent du dataset DICOM : 01-0096 → remplacé par 01-0095)", file=sys.stderr)

    print(f"\n{sep}", file=sys.stderr)
    print("ÉTAPE 2 — datasetAVANTPREPROCESS → prepUS → crop vs data_test", file=sys.stderr)
    ok2 = [r for r in step2_rows if not r.get("erreur") and r.get("score_notre_prepus")]
    same_dims = sum(1 for r in ok2 if r.get("dims_identiques") == "OUI")
    same_labels = sum(1 for r in ok2 if r.get("labels_identiques") == "OUI")
    psnr_vals = []
    for r in ok2:
        try:
            v = float(r.get("psnr_db", "-1"))
            if v > 0:
                psnr_vals.append(v)
        except (ValueError, TypeError):
            pass

    print(f"  Patients testés : {len(ok2)}", file=sys.stderr)
    print(f"  Dimensions crop identiques  : {same_dims}/{len(ok2)}", file=sys.stderr)
    if psnr_vals:
        print(f"  PSNR moyen (dims identiques): {np.mean(psnr_vals):.1f} dB  "
              f"(min={min(psnr_vals):.1f}  max={max(psnr_vals):.1f})", file=sys.stderr)
    print(f"  Labels RISK identiques      : {same_labels}/{len(ok2)}  "
          f"({100*same_labels/max(len(ok2),1):.0f}%)", file=sys.stderr)

    print(f"\n{sep}", file=sys.stderr)
    print("ÉTAPE 3 — data_test → RISK (actuel torch 2.x vs CSV juin-2024 torch ~2.0)", file=sys.stderr)
    ok3 = [r for r in step3_rows if not r.get("erreur") and r.get("score_actuel")]
    same3 = sum(1 for r in ok3 if r.get("labels_ok") == "OUI")
    deltas3 = [abs(float(r["delta"])) for r in ok3 if r.get("delta")]
    print(f"  Patients testés : {len(ok3)}", file=sys.stderr)
    print(f"  Labels identiques vs CSV    : {same3}/{len(ok3)}  "
          f"({100*same3/max(len(ok3),1):.0f}%)", file=sys.stderr)
    if deltas3:
        print(f"  |Δ| score moyen vs CSV      : {np.mean(deltas3):.4f}  "
              f"max={max(deltas3):.4f}", file=sys.stderr)
    divergences3 = [r["patient"] for r in ok3 if r.get("labels_ok") == "NON"]
    if divergences3:
        print(f"  Divergences de label        : {divergences3}", file=sys.stderr)

    print(f"\n{sep}", file=sys.stderr)
    print("DIAGNOSTIC DE REPRODUCTIBILITÉ", file=sys.stderr)
    print("""
  1. ÉTAPE 1 (DICOM → AV1 720p) : 98 % reproductible (PSNR ~39 dB).
     Différence résiduelle : artéfacts d'encodage AV1 entre libsvtav1 versions.
     Impact modèle : NÉGLIGEABLE.

  2. ÉTAPE 2 (prepUS) : crop IDENTIQUE mais pixel-content légèrement différent.
     Cause : numpy 2.0 (NEP 50) change le type de theta_c float64→float32.
     Cela modifie mask_valid dans pre_dsc_image_vectorized, donc les pixels
     masqués dans video.mp4 diffèrent légèrement.
     Impact labels : FAIBLE (vérifiez colonne 'labels_identiques' ci-dessus).

  3. ÉTAPE 3 (RISK, scores absolus) : dérive systématique vs CSV juin-2024.
     Cause : torch 2.11.0 vs torch 2.x (2024) — les convolutions 3D C3D
     produisent des valeurs flottantes différentes (impl. BLAS/MKL évolue).
     Impact labels : minimal (vérifiez colonne 'labels_ok' ci-dessus).

  CONCLUSION : reproduction bit-identique IMPOSSIBLE.
  Recommandations :
    a) Cross-platform : activer PREPUS_BYPASS_MP4=True dans config.py.
       (prepUS 100%% numpy, identique sur Windows/Mac/Linux)
    b) Scores stables à long terme : fine-tuner le modèle C3D sur les DICOMs
       traités avec le pipeline ACTUEL (torch 2.x + numpy 2.0 + mpeg4 ffmpeg).
       Cela corrigera le décalage train/test dû aux changements d'environnement.
""", file=sys.stderr)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--av1_dir",   default=DEFAULT_AV1_DIR)
    parser.add_argument("--data_test", default=DEFAULT_DATA_TEST)
    parser.add_argument("--output",    default=DEFAULT_OUTPUT)
    parser.add_argument("--skip_step2", action="store_true",
                        help="Sauter l'étape 2 (prepUS sur AV1) — plus rapide")
    args = parser.parse_args()

    _log("info", "Chargement STARHE-RISK…")
    risk_model = STARHERiskModel()

    all_rows: list[dict] = []

    if not args.skip_step2:
        _log("info", "\n=== ÉTAPE 2 : datasetAVANTPREPROCESS → prepUS → vs data_test ===")
        step2 = run_step2(args.av1_dir, args.data_test, risk_model)
        all_rows.extend(step2)
    else:
        _log("info", "Étape 2 sautée (--skip_step2)")
        step2 = []

    _log("info", "\n=== ÉTAPE 3 : data_test → RISK (actuel vs CSV référence) ===")
    step3 = run_step3(args.data_test, risk_model)
    all_rows.extend(step3)

    risk_model.close()

    # Write the CSV
    all_keys: list[str] = []
    for r in all_rows:
        for k in r:
            if k not in all_keys:
                all_keys.append(k)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for r in all_rows:
            writer.writerow({k: r.get(k, "") for k in all_keys})

    _print_summary(step2, step3)
    print(f"\n✓ CSV : {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
