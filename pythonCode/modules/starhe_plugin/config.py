"""
config.py — Central configuration of the STARHE plug-in
========================================================
All constants, paths and hyperparameters are
centralized here to ease maintenance.
"""

import os

# ── Base paths ────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))

# Repository root (3 levels above starhe_plugin/ → PLUGIN1-MEDomics/)
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))

# DICOM files directory (local working data)
# Configurable via the STARHE_DATA_DIR environment variable;
# default: "data/" directory at the project root.
DATA_DIR     = os.environ.get("STARHE_DATA_DIR",
                              os.path.join(PROJECT_ROOT, "data"))
MODELS_DIR   = os.path.join(BASE_DIR, "models")
TEMP_DIR     = os.path.join(BASE_DIR, "temp")

# Directory of `.pth` weights downloaded at runtime (Electron Phase 4).
# In dev mode: not set → uses MODELS_DIR (the .pth files sit next to the configs).
# In packaged mode: Electron sets STARHE_WEIGHTS_DIR to
#                   `app.getPath('userData')/models/` (downloaded at first launch).
# The `.py` configs (rtmdet_starhe.py, etc.) always remain in MODELS_DIR
# (versioned, bundled by PyInstaller via spec datas).
WEIGHTS_DIR  = os.environ.get("STARHE_WEIGHTS_DIR") or MODELS_DIR

# Vendored `starhe` Python package (copied into ai/vendor/ — self-contained)
VENDOR_DIR   = os.path.join(BASE_DIR, "ai", "vendor")

# Automatically create the directories if they do not exist
for _d in (MODELS_DIR, TEMP_DIR, WEIGHTS_DIR):
    os.makedirs(_d, exist_ok=True)

# ── STARHE models (local artifacts — self-contained, no external dependency) ──

# Classification (STARHE-RISK) — C3D
STARHE_RISK_CHECKPOINT = os.path.join(WEIGHTS_DIR, "best_acc_mean_cls_f1_epoch_14.pth")

# C3D backend for STARHE-RISK.
# "mmaction2" : _c3d_runner.py subprocess using mmaction2's C3D and I3DHead
#               classes directly (without the mmengine registry). Requires
#               mmaction2==1.2.0 installed with --no-deps in the venv.
#               Bit-identical results to "pytorch" on the same tensors.
# "pytorch"   : local C3DRecognizer (c3d.py), validated bit-identical to mmaction2,
#               no mmaction2 dependency. Automatic fallback if mmaction2
#               is missing or the subprocess fails.
C3D_BACKEND: str = os.environ.get("C3D_BACKEND", "mmaction2")

# Detection (STARHE-DETECT) — active model: "rtmdet" | "dino"
DETECT_BACKEND = "rtmdet"

# Detection — RTMDet (default)
STARHE_DETECT_CONFIG     = os.path.join(MODELS_DIR,  "rtmdet_starhe.py")
STARHE_DETECT_CHECKPOINT = os.path.join(WEIGHTS_DIR, "best_coco_bbox_mAP_50_iter_2100.pth")

# Detection — DINO-DETR (optional)
# The config inherits from _base_/ via relative paths → configs/ structure preserved
STARHE_DINO_CONFIG     = os.path.join(MODELS_DIR,  "configs", "custom", "dino_starhe.py")
STARHE_DINO_CHECKPOINT = os.path.join(WEIGHTS_DIR, "best_coco_bbox_mAP_50_iter_2100.pth")

# Root to add to sys.path for `import starhe` (vendored package)
# Contains: vendor/starhe/__init__.py
STARHE_SHARE_ROOT = VENDOR_DIR

# Minimum confidence score to display a detection
DETECT_SCORE_THRESHOLD = 0.70

# DETECT temporal subsampling: 1 frame analyzed out of every N
# The N-1 intermediate frames inherit the detections of the analyzed frame
# 1 = every frame (disabled), 4 = ×4 speedup (recommended)
DETECT_EVERY_N = 4

# RTMDet batch inference size.
# "auto" = detect hardware (VRAM/RAM) and compute optimal batch size.
# integer = fixed batch size (e.g. 4); set to 1 to disable batching.
DETECT_BATCH_SIZE = "auto"

# Device used for all AI inference (RISK + DETECT).
# "auto"  = GPU if available (cuda → mps → cpu) — best performance, slight
#            cross-platform variance due to different FP32 hardware/BLAS.
# "cpu"   = force CPU on all platforms — maximizes cross-platform
#            reproducibility (MKL vs Accelerate still differ by ~1e-5 per op,
#            but far less than GPU vs GPU).
# "cuda"  = force CUDA (raises if unavailable)
# "mps"   = force Apple Silicon GPU (raises if unavailable)
INFERENCE_DEVICE = "auto"

# ── Cross-platform reproducibility ───────────────────────────────────────────
# When True, both models (RISK and DETECT) are forced onto CPU in
# float64.  Float64 reduces the BLAS rounding error (MKL↔Accelerate) from ~1e-4
# (float32) to ~1e-13 (float64), making scores bit-identical between
# Windows and macOS for the same DICOM file.
#
# RISK  : "30.1% mac" vs "29.9% windows" → source: BLAS MKL↔Accelerate
#         (float32 accumulation differ by ~0.002).  Float64 → identical.
# DETECT: "48 frames mac" vs "44 frames windows" → MAIN source:
#         Mac uses MPS (Apple Silicon GPU), Windows uses CPU → completely
#         different arithmetic → borderline scores flip around 0.70.
#         Float64 on CPU → identical on both platforms.
#
# Cost: ~2–3× slower on CPU.  Disable (False) for fast production runs.
#
# ⚠️  Set to False to reproduce Jérémy's native environment (Linux + GPU,
#     float32): forcing CPU/float64 MOVES AWAY from his distribution. Switch back
#     to True for bit-exact reproducibility across OSes.
DETERMINISTIC_INFERENCE: bool = True

# ── MP4 roundtrip bypass in prepUS ───────────────────────────────────────────
# `cv2.VideoWriter(mp4v)` produces a bitstream that depends on the FFmpeg binary
# linked to OpenCV (macOS ARM Homebrew ≠ Linux ≠ Windows). The standard pipeline
# writes `input.mp4` then reads back `video.mp4`, which makes the C3D crops
# non-portable across OSes for the SAME input DICOM.
#
# True  : 100% numpy prepUS computation (preprocess_with_prepus_inmem). Output
#         bit-identical cross-platform. Slight deviation vs the training
#         distribution (which saw crops with mp4v artifacts).
# False : historical pipeline (preprocess_with_prepus) — reproduces exactly
#         Jérémy's training path on the same platform.
#
# ⚠️  Set to False to reproduce Jérémy: the mp4v roundtrip is what the models
#     saw during training. Switch back to True for cross-OS portability.
PREPUS_BYPASS_MP4: bool = True

# ── DICOM decoding via weasis-dcm2png ────────────────────────────────────────
# `pydicom.pixel_array` applies neither the DICOM's Modality LUT nor its VOI LUT,
# whereas Jérémy's training pipeline went through Weasis (LUTs
# applied) → PNG → ffmpeg → prepUS. Enabling this flag reproduces the Weasis
# phase (LUTs) to reduce the divergence from the training distribution.
#
# True  : DICOM → java -jar weasis-dcm2png → PNG → numpy. Requires Java on
#         the PATH + the vendored JAR (third_party/weasis-dcm2png/dist/).
#         Automatic fallback to pydicom if Java/JAR is missing or if weasis
#         fails (e.g. JPEG 2000 not supported by the current JAR).
# False : direct pydicom via extract_frames(ds) — historical behavior,
#         no LUT applied, no Java subprocess.
USE_WEASIS_EXPORT: bool = True

# ── STARHE-RISK decision threshold ───────────────────────────────────────────
# Minimum probability (class 1 = high risk) to classify a patient
# as "High risk".
#
# 0.50 = argmax behavior (mmaction2 default / Analysis A during training)
# 0.60 = reduces Supersonic false positives at the cost of lower sensitivity
#
# Calibration on this test set (47 patients):
#   Threshold 0.50 → Sens=90.9%  Spec=52.0%  Acc=70.2%  F1=0.741
#   Threshold 0.60 → Sens=77.3%  Spec=64.0%  Acc=70.2%  F1=0.708
#   C3D ref        → Sens=77.3%  Spec=72.0%  Acc=74.5%
RISK_THRESHOLD: float = 0.50

# ── DICOM preprocessing parameters ───────────────────────────────────────────
CROP_BLACK_THRESHOLD   = 10
CROP_MIN_CONTENT_RATIO = 0.01

# ── MongoDB ───────────────────────────────────────────────────────────────────
# Overridable via environment variables (consistent with go_server/config.go)
MONGO_URI        = os.environ.get("MONGO_URI",  "mongodb://localhost:54017/")
MONGO_DB_NAME    = os.environ.get("MONGO_DB",   "medomics")
MONGO_COLLECTION = os.environ.get("MONGO_COLL", "starhe_results")

# ── DICOM tags to anonymize ───────────────────────────────────────────────────
# (group, element) per the DICOM PS3.15 Annex E standard
DICOM_SENSITIVE_TAGS = [
    (0x0010, 0x0010),  # PatientName
    (0x0010, 0x0020),  # PatientID
    (0x0010, 0x0030),  # PatientBirthDate
    (0x0010, 0x0040),  # PatientSex
    (0x0010, 0x1010),  # PatientAge
    (0x0008, 0x0020),  # StudyDate
    (0x0008, 0x0030),  # StudyTime
    (0x0008, 0x0090),  # ReferringPhysicianName
    (0x0008, 0x1030),  # StudyDescription
    (0x0008, 0x103E),  # SeriesDescription
    (0x0020, 0x000D),  # StudyInstanceUID
    (0x0020, 0x000E),  # SeriesInstanceUID
    (0x0008, 0x0018),  # SOPInstanceUID
    (0x0032, 0x1032),  # RequestingPhysician
    (0x0040, 0xA124),  # UID
]
