#!/usr/bin/env python3
"""
compare_risk_original_vs_plugin.py — STARHE-RISK : modèle originel vs plugin
==============================================================================
Compare, sur le même dataset MP4 déjà préprocessé (prepUS), les scores produits
par :

  A) "Original" — pipeline mmaction2 RÉELLE (pas une réimplémentation) :
     les classes `SampleFrames`, `Resize`, `CenterCrop`, `FormatShape` sont
     importées directement depuis le package `mmaction` installé et exécutées
     telles quelles (mêmes hyperparamètres que `c3d_starhe.py` :
     clip_len=16, num_clips=10, test_mode=True, scale=(-1,128), crop_size=112).
     Le backbone C3D + tête I3DHead sont chargés depuis le checkpoint situé
     dans /Users/hugo/Desktop/STAGE/starhe_share/models/classification/.
     Seule différence avec le vrai pipeline d'entraînement : DecordInit/
     DecordDecode sont remplacés par une simple lecture cv2 (déjà validée
     bit-identique à Decord/PyAV — cf. README "Validation" du 22 juin 2026).

  B) "Plugin" — `STARHERiskModel` du projet, tel qu'il est actuellement sur
     disque (backend sélectionné par `C3D_BACKEND` dans config.py), appelé
     directement sans passer par pipeline.py (pas de DICOM, pas de prepUS,
     pas de MongoDB — uniquement l'inférence STARHE-RISK).

Objectif : détecter tout écart entre le modèle originel et l'implémentation
courante du plugin (utile après une modification du code de prétraitement/
inférence C3D).

Usage :
    python scripts/compare_risk_original_vs_plugin.py \\
        --input      /Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test \\
        --orig-ckpt  /Users/hugo/Desktop/STAGE/starhe_share/models/classification/best_acc_mean_cls_f1_epoch_14.pth \\
        --output     scripts/results/comparaison_risk_original_vs_plugin.csv
"""

import argparse
import csv
import os
import re
import sys
import time

import cv2
import numpy as np
import torch
import torch.nn.functional as F

# ── PYTHONPATH — plugin modules ────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MOD_PATH   = os.path.join(_SCRIPT_DIR, "..", "pythonCode", "modules")
if _MOD_PATH not in sys.path:
    sys.path.insert(0, _MOD_PATH)

from starhe_plugin.utils.go_print import set_log_sink


def _log(level: str, msg: str) -> None:
    print(f"[{level.upper():8s}] {msg}", file=sys.stderr, flush=True)


set_log_sink(_log)

from starhe_plugin.ai.models._c3d_runner import _load_model as _load_c3d_direct
from starhe_plugin.ai.starhe_risk import STARHERiskModel

# ── Default paths ─────────────────────────────────────────────────────────────
DEFAULT_INPUT = "/Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test"
DEFAULT_ORIG_CKPT = (
    "/Users/hugo/Desktop/STAGE/starhe_share/models/classification/"
    "best_acc_mean_cls_f1_epoch_14.pth"
)
DEFAULT_OUTPUT = os.path.join(_SCRIPT_DIR, "results", "comparaison_risk_original_vs_plugin.csv")

CSV_FIELDS = [
    "fichier",
    "id_patient",
    "n_frames",
    "original_score_high",
    "original_score_low",
    "original_label",
    "plugin_score_high",
    "plugin_score_low",
    "plugin_label",
    "delta_score_high",
    "abs_delta",
    "labels_identiques",
    "duree_original_s",
    "duree_plugin_s",
    "erreur",
]

# Reuses EXACTLY the same dict as the plugin to avoid any false positive
# from string comparison (accents, case…).
LABELS = STARHERiskModel.LABELS


def _patient_id(name: str) -> str:
    m = re.search(r"(\d{2}-\d{4})", name)
    return m.group(1) if m else name


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


# ══════════════════════════════════════════════════════════════════════════════
#  A) "original" pipeline — real mmaction2 classes (no reimplementation)
# ══════════════════════════════════════════════════════════════════════════════

class OriginalMMAction2Model:
    """C3D backbone + I3DHead loaded from the original checkpoint,
    prétraitement effectué avec les VRAIES classes mmaction2
    (SampleFrames, Resize, CenterCrop, FormatShape) — mêmes hyperparamètres
    as models/classification/c3d_starhe.py (training config)."""

    CLIP_LEN, NUM_CLIPS, RESIZE_SIZE, CROP_SIZE = 16, 10, 128, 112
    MEAN = np.array([104.0, 117.0, 128.0], dtype=np.float32).reshape(1, 3, 1, 1, 1)

    def __init__(self, ckpt_path: str, device: str = "cpu"):
        from mmaction.datasets.transforms import (
            SampleFrames, Resize, CenterCrop, FormatShape,
        )
        self._sample_frames = SampleFrames(
            clip_len=self.CLIP_LEN, frame_interval=1,
            num_clips=self.NUM_CLIPS, test_mode=True,
        )
        self._resize      = Resize(scale=(-1, self.RESIZE_SIZE))
        self._center_crop = CenterCrop(crop_size=self.CROP_SIZE)
        self._format_shape = FormatShape(input_format="NCTHW")

        self._device = device
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True, warn_only=True)
        self.backbone, self.cls_head = _load_c3d_direct(ckpt_path, device)

    def _preprocess(self, frames: np.ndarray) -> torch.Tensor:
        total_frames = len(frames)
        results = {"total_frames": total_frames, "start_index": 0}
        results = self._sample_frames.transform(results)
        results["imgs"]      = [frames[i] for i in results["frame_inds"]]
        results["img_shape"] = frames.shape[1:3]
        results["modality"]  = "RGB"

        results = self._resize.transform(results)
        results = self._center_crop.transform(results)
        results = self._format_shape.transform(results)

        imgs = results["imgs"]  # (NUM_CLIPS, C, T, H, W) uint8
        tensor = torch.from_numpy(imgs.astype(np.float32) - self.MEAN)
        return tensor

    @torch.no_grad()
    def predict(self, frames: np.ndarray) -> dict:
        tensor = self._preprocess(frames).to(self._device)
        feats  = self.backbone(tensor)
        logits = self.cls_head.fc_cls(self.cls_head.dropout(feats))
        probs  = F.softmax(logits, dim=1).mean(0)
        score_low, score_high = float(probs[0].item()), float(probs[1].item())
        pred_cls = 1 if score_high >= 0.5 else 0
        return {
            "risk_score": score_high,
            "risk_label": LABELS[pred_cls],
            "scores":     [score_low, score_high],
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",     "-i", default=DEFAULT_INPUT)
    parser.add_argument("--orig-ckpt", "-c", default=DEFAULT_ORIG_CKPT,
                        help="Checkpoint du modèle originel (starhe_share/models/classification)")
    parser.add_argument("--output",    "-o", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    mp4_files = sorted(
        os.path.join(args.input, f)
        for f in os.listdir(args.input)
        if f.lower().endswith(".mp4")
    )
    if not mp4_files:
        print(f"Aucun .mp4 dans : {args.input}", file=sys.stderr)
        sys.exit(1)
    _log("info", f"{len(mp4_files)} fichier(s) a evaluer depuis {args.input}")

    _log("info", f"Chargement modele ORIGINAL (mmaction2 reel) : {args.orig_ckpt}")
    model_original = OriginalMMAction2Model(args.orig_ckpt, device="cpu")

    _log("info", "Chargement modele PLUGIN (STARHERiskModel courant)…")
    model_plugin = STARHERiskModel(device="cpu")
    _log("info", f"  backend actif : {model_plugin._active_backend}")

    rows = []
    for idx, path in enumerate(mp4_files, 1):
        name = os.path.splitext(os.path.basename(path))[0]
        pid  = _patient_id(name)
        _log("info", f"[{idx}/{len(mp4_files)}] {name}")
        row = dict.fromkeys(CSV_FIELDS, "")
        row["fichier"]    = os.path.basename(path)
        row["id_patient"] = pid

        try:
            frames = read_mp4_frames(path)
            row["n_frames"] = len(frames)

            t0 = time.perf_counter()
            r_orig = model_original.predict(frames)
            d_orig = time.perf_counter() - t0

            t0 = time.perf_counter()
            r_plug = model_plugin.predict(frames)
            d_plug = time.perf_counter() - t0

            delta = r_orig["risk_score"] - r_plug["risk_score"]

            row["original_score_high"] = f"{r_orig['risk_score']:.6f}"
            row["original_score_low"]  = f"{r_orig['scores'][0]:.6f}"
            row["original_label"]      = r_orig["risk_label"]
            row["plugin_score_high"]   = f"{r_plug['risk_score']:.6f}"
            row["plugin_score_low"]    = f"{r_plug['scores'][0]:.6f}"
            row["plugin_label"]        = r_plug["risk_label"]
            row["delta_score_high"]    = f"{delta:+.6f}"
            row["abs_delta"]           = f"{abs(delta):.6f}"
            row["labels_identiques"]   = "OUI" if r_orig["risk_label"] == r_plug["risk_label"] else "NON"
            row["duree_original_s"]    = f"{d_orig:.2f}"
            row["duree_plugin_s"]      = f"{d_plug:.2f}"

            marker = "OK" if row["labels_identiques"] == "OUI" else "DIVERGENCE"
            _log("info",
                 f"  orig={r_orig['risk_score']:.4f} [{r_orig['risk_label']}]  "
                 f"plugin={r_plug['risk_score']:.4f} [{r_plug['risk_label']}]  "
                 f"delta={delta:+.4f}  {marker}")

        except Exception as exc:
            _log("error", f"  echec {name} : {exc}")
            row["erreur"] = str(exc)

        rows.append(row)

    model_plugin.close()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    ok  = [r for r in rows if not r["erreur"]]
    n_same  = sum(1 for r in ok if r["labels_identiques"] == "OUI")
    n_total = len(ok)
    deltas  = [abs(float(r["abs_delta"])) for r in ok if r["abs_delta"]]

    print(f"\n{'─'*90}", file=sys.stderr)
    print(f"{'Fichier':<20} {'Orig score':>10}  {'Orig label':<14}  {'Plugin score':>12}  {'Plugin label':<14}  {'|delta|':>8}", file=sys.stderr)
    print(f"{'─'*90}", file=sys.stderr)
    for r in ok:
        print(
            f"{r['fichier']:<20} {r['original_score_high']:>10}  {r['original_label']:<14}  "
            f"{r['plugin_score_high']:>12}  {r['plugin_label']:<14}  {r['abs_delta']:>8}"
            f"  {'✓' if r['labels_identiques']=='OUI' else '✗ DIVERGENCE'}",
            file=sys.stderr,
        )
    print(f"{'─'*90}", file=sys.stderr)
    if deltas:
        print(f"Concordance labels original vs plugin : {n_same}/{n_total} "
              f"({100*n_same/n_total:.0f}%)", file=sys.stderr)
        print(f"Delta score |max|  : {max(deltas):.6f}", file=sys.stderr)
        print(f"Delta score moyen  : {np.mean(deltas):.6f}", file=sys.stderr)
    print(f"\n✓ CSV ecrit : {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
