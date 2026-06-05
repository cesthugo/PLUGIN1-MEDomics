"""
test_weasis_pipeline.py — Test du pipeline Weasis-style
========================================================
Passe output.mp4 (généré depuis les PNGs Weasis via ffmpeg) directement à
prepUS.removeLayoutFile, puis fait tourner STARHE-RISK (C3D) sur le résultat.

Différence clé avec la pipeline normale :
  Pipeline normale : DICOM → pydicom → cv2.VideoWriter (mp4v) → prepUS → C3D
  Pipeline Weasis  : DICOM → Weasis (PNG lossless) → ffmpeg (mp4v) → prepUS → C3D

Ce script saute la ré-encodage en testant directement l'output.mp4 ffmpeg.
"""

import json
import os
import shutil
import sys
import tempfile

import cv2
import numpy as np

# ── Chemins ────────────────────────────────────────────────────────────────────
PLUGIN_DIR = "/Users/hugo/Desktop/STAGE/PLUGIN1-MEDomics/pythonCode/modules"
MP4_PATH   = (
    "/Users/hugo/Desktop/UNKNOWN/Nov 30, 2022"
    "/[1] US  -- 139 instance(_-e8a4a5b6/output.mp4"
)

sys.path.insert(0, PLUGIN_DIR)

# ── 1. Appel direct de removeLayoutFile sur le MP4 ffmpeg ────────────────────
print(f"[1] removeLayoutFile sur : {os.path.basename(MP4_PATH)}")
from prepUS.cli import removeLayoutFile  # type: ignore

work_dir = tempfile.mkdtemp(prefix="test_weasis_")
out_dir  = os.path.join(work_dir, "out")

result = removeLayoutFile(
    input_file=MP4_PATH,
    output_dir=out_dir,
    thresh=-1.0,
    back_scan_conversion=True,   # nécessaire pour que video.mp4 soit écrit
    save_mask=False,
    save_cropped_mask=False,
    save_info=True,
)
print(f"    → removeLayoutFile retourné : {result}")

# ── 2. Lire info.json ─────────────────────────────────────────────────────────
info_path = os.path.join(out_dir, "info.json")
if os.path.exists(info_path):
    with open(info_path, encoding="utf-8") as fh:
        info = json.load(fh)
    print(f"[2] Crop ROI : {info.get('crop')}")
else:
    print("[2] info.json absent")
    info = {}

# ── 3. Lire video.mp4 (crop polaire, niveaux de gris) ────────────────────────
crop_mp4 = os.path.join(out_dir, "video.mp4")
cap = cv2.VideoCapture(crop_mp4)
frames_gray = []
while True:
    ret, frame = cap.read()
    if not ret:
        break
    frames_gray.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
cap.release()

if not frames_gray:
    print("[ERR] video.mp4 vide — prepUS a peut-être échoué")
    shutil.rmtree(work_dir, ignore_errors=True)
    sys.exit(1)

crop_only = np.stack(frames_gray)                                  # (T, H_c, W_c)
frames_rgb = np.stack([crop_only, crop_only, crop_only], axis=-1)  # (T, H_c, W_c, 3)
print(f"[3] crop_only shape : {crop_only.shape}  dtype={crop_only.dtype}")

shutil.rmtree(work_dir, ignore_errors=True)

# ── 4. STARHE-RISK (C3D) ──────────────────────────────────────────────────────
print("[4] Chargement STARHE-RISK…")
from starhe_plugin.ai.starhe_risk import STARHERiskModel

model  = STARHERiskModel()
result = model.predict(frames_rgb)

print()
print("=" * 50)
print(f"  RISK SCORE (Weasis pipeline) : {result['risk_score']:.4f}")
print(f"  Label                        : {result.get('risk_label', '?')}")
print(f"  Scores [low, high]           : {[round(s, 4) for s in result.get('scores', [])]}")
print("=" * 50)
