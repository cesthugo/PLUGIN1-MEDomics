#!/usr/bin/env python3
"""
compare_risk_backends.py — Comparaison backends STARHE-RISK sur MP4 préprocessés
=================================================================================
Compare côte à côte les scores produits par :
  • backend "mmaction2" : C3D + I3DHead chargés directement depuis mmaction2
                          (subprocess _c3d_runner.py), float32 natif.
  • backend "pytorch"   : C3DRecognizer local (c3d.py), float64 deterministe.

Les deux partagent le MÊME checkpoint et le MÊME prétraitement (cv2 + notre
pipeline SampleFrames/Resize/CenterCrop). La différence attendue est ≤ 1e-5.

Usage :
    python scripts/compare_risk_backends.py \\
        --input  /Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test \\
        --output /Users/hugo/Desktop/STAGE/comparaison_backends_risk.csv
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

from starhe_plugin.utils.go_print import set_log_sink

def _log(level: str, msg: str) -> None:
    print(f"[{level.upper():8s}] {msg}", file=sys.stderr, flush=True)

set_log_sink(_log)

import starhe_plugin.config as _cfg   # noqa — charge la config avant les modèles


CSV_FIELDS = [
    "fichier",
    "n_frames",
    # mmaction2
    "mma_score_high",
    "mma_score_low",
    "mma_label",
    # pytorch
    "pt_score_high",
    "pt_score_low",
    "pt_label",
    # différence
    "delta_score",
    "labels_identiques",
    # timing
    "mma_duree_s",
    "pt_duree_s",
    "erreur",
]

LABELS = {0: "Risque faible", 1: "Risque élevé"}


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


def run_one(mp4_path: str, risk_mma, risk_pt) -> dict:
    name = os.path.splitext(os.path.basename(mp4_path))[0]
    row  = dict.fromkeys(CSV_FIELDS, "")
    row["fichier"] = name

    try:
        _log("info", f"── {name} ── lecture…")
        frames = read_mp4_frames(mp4_path)
        row["n_frames"] = len(frames)
        _log("info", f"  {len(frames)} frames  {frames.shape[2]}×{frames.shape[1]}px")

        # Backend mmaction2
        t0 = time.perf_counter()
        res_mma = risk_mma.predict(frames)
        row["mma_duree_s"]   = f"{time.perf_counter() - t0:.2f}"
        row["mma_score_high"] = f"{res_mma['risk_score']:.6f}"
        row["mma_score_low"]  = f"{res_mma['scores'][0]:.6f}"
        row["mma_label"]      = res_mma["risk_label"]

        # Backend pytorch
        t0 = time.perf_counter()
        res_pt = risk_pt.predict(frames)
        row["pt_duree_s"]   = f"{time.perf_counter() - t0:.2f}"
        row["pt_score_high"] = f"{res_pt['risk_score']:.6f}"
        row["pt_score_low"]  = f"{res_pt['scores'][0]:.6f}"
        row["pt_label"]      = res_pt["risk_label"]

        delta = abs(res_mma["risk_score"] - res_pt["risk_score"])
        row["delta_score"]        = f"{delta:.2e}"
        row["labels_identiques"]  = "OUI" if res_mma["risk_label"] == res_pt["risk_label"] else "NON"

        _log("info",
             f"  mma={res_mma['risk_score']:.4f} [{res_mma['risk_label']}]  "
             f"pt={res_pt['risk_score']:.4f} [{res_pt['risk_label']}]  "
             f"Δ={delta:.2e}  {'✓' if res_mma['risk_label']==res_pt['risk_label'] else '✗'}")

    except Exception as exc:
        _log("error", f"  ✗ {name} : {exc}")
        row["erreur"] = str(exc)

    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  "-i",
        default="/Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test")
    parser.add_argument("--output", "-o",
        default="/Users/hugo/Desktop/STAGE/comparaison_backends_risk.csv")
    args = parser.parse_args()

    mp4_files = sorted(
        os.path.join(args.input, f)
        for f in os.listdir(args.input)
        if f.lower().endswith(".mp4")
    )
    if not mp4_files:
        print(f"Aucun .mp4 dans : {args.input}", file=sys.stderr)
        sys.exit(1)

    _log("info", f"{len(mp4_files)} fichier(s) à évaluer")

    # Charger les deux backends (une seule fois — C3D est lourd)
    _log("info", "Chargement backend mmaction2…")

    # Force mmaction2
    _cfg.C3D_BACKEND = "mmaction2"
    from starhe_plugin.ai.starhe_risk import _MMAction2Backend, _PyTorchBackend, STARHERiskModel

    # mmaction2 backend
    risk_mma = STARHERiskModel()
    assert risk_mma._active_backend == "mmaction2", \
        f"Fallback détecté : {risk_mma._active_backend} — mmaction2 doit être installé"

    _log("info", "Chargement backend PyTorch pur…")
    from starhe_plugin.config import DETERMINISTIC_INFERENCE
    device_pt = "cpu" if DETERMINISTIC_INFERENCE else "cpu"
    risk_pt_backend = _PyTorchBackend(device_pt, DETERMINISTIC_INFERENCE)

    # Wrapper minimal pour avoir la même interface predict()
    class _PTModel:
        LABELS = {0: "Risque faible", 1: "Risque élevé"}
        def __init__(self, backend):
            self._backend = backend
        def predict(self, frames):
            from starhe_plugin.config import RISK_THRESHOLD
            lo, hi = self._backend.predict(frames)
            cls = 1 if hi >= RISK_THRESHOLD else 0
            return {"risk_score": hi, "risk_label": self.LABELS[cls], "scores": [lo, hi]}

    risk_pt = _PTModel(risk_pt_backend)

    rows = []
    for i, path in enumerate(mp4_files, 1):
        _log("info", f"\n[{i}/{len(mp4_files)}]")
        rows.append(run_one(path, risk_mma, risk_pt))

    risk_mma.close()

    # Écriture CSV
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    _log("info", f"\n✓ CSV : {args.output}")

    # Résumé terminal
    ok  = [r for r in rows if not r["erreur"]]
    err = [r for r in rows if r["erreur"]]
    n_same  = sum(1 for r in ok if r["labels_identiques"] == "OUI")
    n_total = len(ok)

    print(f"\n{'─'*90}", file=sys.stderr)
    print(f"{'Fichier':<28} {'MMA score':>10}  {'MMA label':<16}  {'PT score':>10}  {'PT label':<16}  {'Δ':>8}  {'=?'}", file=sys.stderr)
    print(f"{'─'*90}", file=sys.stderr)
    for r in ok:
        print(
            f"{r['fichier']:<28} {float(r['mma_score_high']):>10.4f}  {r['mma_label']:<16}  "
            f"{float(r['pt_score_high']):>10.4f}  {r['pt_label']:<16}  "
            f"{r['delta_score']:>8}  {'✓' if r['labels_identiques']=='OUI' else '✗'}",
            file=sys.stderr,
        )
    if err:
        print("\nErreurs :", file=sys.stderr)
        for r in err: print(f"  {r['fichier']} : {r['erreur']}", file=sys.stderr)
    print(f"{'─'*90}", file=sys.stderr)
    print(f"Concordance labels mmaction2 vs pytorch : {n_same}/{n_total} ({100*n_same/n_total:.0f}%)", file=sys.stderr)


if __name__ == "__main__":
    main()
