"""
test_weasis_pipeline.py — Test of the Weasis-style pipeline
========================================================
Passes output.mp4 (generated from the Weasis PNGs via ffmpeg) directly to
prepUS.removeLayoutFile, then runs STARHE-RISK (C3D) on the result.

Key difference from the normal pipeline:
  Normal pipeline: DICOM → pydicom → cv2.VideoWriter (mp4v) → prepUS → C3D
  Weasis pipeline: DICOM → Weasis (PNG lossless) → ffmpeg (mp4v) → prepUS → C3D

This script skips the re-encoding by testing the ffmpeg output.mp4 directly.
"""

import json
import os
import shutil
import sys
import tempfile

import cv2
import numpy as np

# ── Paths ──────────────────────────────────────────────────────────────────────
PLUGIN_DIR = "/Users/hugo/Desktop/STAGE/PLUGIN1-MEDomics/pythonCode/modules"
MP4_PATH   = (
    "/Users/hugo/Desktop/UNKNOWN/Nov 30, 2022"
    "/[1] US  -- 139 instance(_-e8a4a5b6/output.mp4"
)

sys.path.insert(0, PLUGIN_DIR)

# ── 1. Direct call to removeLayoutFile on the ffmpeg MP4 ─────────────────────
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

# ── 3. Read video.mp4 (polar crop, grayscale) ────────────────────────────────
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
