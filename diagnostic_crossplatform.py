"""
diagnostic_crossplatform.py
===========================
Exécute ce script sur Mac ET Windows avec le même fichier DICOM.
Compare les sorties ligne par ligne pour localiser l'étape où
les résultats divergent.

Usage :
    python diagnostic_crossplatform.py /chemin/vers/fichier.dcm

    Sur macOS  : ./run_tkinter.sh + ouvrir un terminal intégré, ou :
    cd pythonCode/modules && python ../../diagnostic_crossplatform.py /chemin/fichier.dcm
"""

import sys, os, hashlib, platform
import numpy as np

# ── Chemin DICOM ──────────────────────────────────────────────────────────────
if len(sys.argv) > 1:
    DCM_PATH = sys.argv[1]
else:
    DCM_PATH = "/Users/hugo/Desktop/STAGE/DATA/01-0003-D-G_Bmode.dcm"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pythonCode", "modules"))

# ── Helpers ───────────────────────────────────────────────────────────────────

def h(arr: np.ndarray) -> str:
    """SHA-256 hex (8 chars) d'un array numpy — suffisant pour détecter toute diff."""
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()[:16]

def sep(title=""):
    print(f"\n{'─'*60}")
    if title:
        print(f"  {title}")
    print('─'*60)

# ═══════════════════════════════════════════════════════════════════════════════
sep("0. ENVIRONNEMENT")
import torch, cv2
print(f"Python       : {sys.version.split()[0]}")
print(f"Platform     : {platform.machine()} | {platform.system()} {platform.release()}")
print(f"PyTorch      : {torch.__version__}")
print(f"NumPy        : {np.__version__}")
print(f"OpenCV       : {cv2.__version__}")
print(f"CPU threads  : {torch.get_num_threads()}")

try:
    from starhe_plugin.config import DETERMINISTIC_INFERENCE, INFERENCE_DEVICE
    print(f"DETERMINISTIC_INFERENCE : {DETERMINISTIC_INFERENCE}")
    print(f"INFERENCE_DEVICE        : {INFERENCE_DEVICE}")
except Exception as e:
    print(f"[ERR config] {e}")

# ═══════════════════════════════════════════════════════════════════════════════
sep("1. LECTURE DICOM + EXTRACTION FRAMES (reader.py)")

from starhe_plugin.dicom.reader import load_dicom, extract_frames, frame_to_uint8

ds          = load_dicom(DCM_PATH)
frames_raw  = extract_frames(ds)
print(f"frames_raw  shape : {frames_raw.shape}  dtype : {frames_raw.dtype}")
print(f"frames_raw  hash  : {h(frames_raw)}")
print(f"frames_raw  frame[0] sum : {int(frames_raw[0].sum())}")
# Vérifie que le fichier est identique (hash DICOM brut)
with open(DCM_PATH, "rb") as f_:
    raw_bytes = f_.read()
print(f"fichier DCM hash  : {hashlib.sha256(raw_bytes).hexdigest()[:16]}")

# ═══════════════════════════════════════════════════════════════════════════════
sep("2. NORMALISATION uint8 (frame_to_uint8)")

frames_uint8 = np.stack([frame_to_uint8(f) for f in frames_raw])
if frames_uint8.ndim == 3:
    frames_rgb = np.stack([frames_uint8] * 3, axis=-1)   # (T, H, W, 3)
else:
    frames_rgb = frames_uint8

print(f"frames_rgb  shape : {frames_rgb.shape}  dtype : {frames_rgb.dtype}")
print(f"frames_rgb  hash  : {h(frames_rgb)}")
print(f"frames_rgb  frame[0] sum : {int(frames_rgb[0].sum())}")
print(f"frames_rgb  min/max : {frames_rgb.min()}, {frames_rgb.max()}")

# ═══════════════════════════════════════════════════════════════════════════════
sep("3. SUPPRESSION BANDEAU (remove_pixel_burnin)")

from starhe_plugin.dicom.anonymizer import remove_pixel_burnin

frames_clean = remove_pixel_burnin(frames_rgb.copy())
print(f"frames_clean hash  : {h(frames_clean)}")
print(f"frames_clean frame[0] sum : {int(frames_clean[0].sum())}")
print(f"diff vs frames_rgb : {int((frames_clean.astype(int) - frames_rgb.astype(int)).sum())}")

# ═══════════════════════════════════════════════════════════════════════════════
sep("4. PREPROCESSING C3D — float32 vs float64 (premier clip)")

from starhe_plugin.ai.models.c3d import preprocess_clips

clips_f32 = preprocess_clips(frames_clean, use_double=False)
clips_f64 = preprocess_clips(frames_clean, use_double=True)
print(f"clips f32 shape : {clips_f32.shape}  dtype : {clips_f32.dtype}")
print(f"clips f64 shape : {clips_f64.shape}  dtype : {clips_f64.dtype}")
print(f"clips f32 clip[0] sum : {clips_f32[0].sum().item():.8f}")
print(f"clips f64 clip[0] sum : {clips_f64[0].sum().item():.8f}")
print(f"clips f32 hash : {h(clips_f32.numpy())}")
print(f"clips f64 hash : {h(clips_f64.numpy())}")
# Déterminisme : deux appels identiques ?
clips_f64b = preprocess_clips(frames_clean, use_double=True)
print(f"clips f64 déterministe (même machine) : {torch.equal(clips_f64, clips_f64b)}")

# ═══════════════════════════════════════════════════════════════════════════════
sep("5. PREPROCESSING RTMDet — float32 vs float64 (frame 0)")

# Importer _preprocess directement sans lancer le serveur mmdet
# On recrée la logique ici pour ne pas avoir besoin du modèle chargé
import torch.nn.functional as F

_INPUT_SIZE = 640
_PAD_VAL    = 114.0
_MEAN_det = torch.tensor([103.53, 116.28, 123.675])
_STD_det  = torch.tensor([ 57.375,  57.12,  58.395])

def preprocess_rtmdet(frame_bgr, use_double=False):
    orig_H, orig_W = frame_bgr.shape[:2]
    scale = min(_INPUT_SIZE / orig_H, _INPUT_SIZE / orig_W)
    new_H, new_W = int(round(orig_H * scale)), int(round(orig_W * scale))
    np_dtype  = np.float64 if use_double else np.float32
    tch_dtype = torch.float64 if use_double else torch.float32
    t = torch.from_numpy(
        np.ascontiguousarray(frame_bgr, dtype=np_dtype)
    ).permute(2, 0, 1).unsqueeze(0)
    resized = F.interpolate(t, size=(new_H, new_W), mode='bilinear', align_corners=False)
    resized = resized.squeeze(0).permute(1, 2, 0).numpy()
    canvas = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), _PAD_VAL, dtype=np_dtype)
    canvas[:new_H, :new_W] = resized
    tensor = torch.from_numpy(np.ascontiguousarray(canvas.transpose(2, 0, 1)))
    tensor = (tensor - _MEAN_det.to(tch_dtype).view(3, 1, 1)) / _STD_det.to(tch_dtype).view(3, 1, 1)
    return tensor.unsqueeze(0)

# Convertir frame 0 en BGR (comme le subprocess RTMDet reçoit)
import cv2 as _cv2
frame0_rgb = frames_clean[0]   # (H, W, 3) uint8 RGB
frame0_bgr = _cv2.cvtColor(frame0_rgb, _cv2.COLOR_RGB2BGR)

t_f32 = preprocess_rtmdet(frame0_bgr, use_double=False)
t_f64 = preprocess_rtmdet(frame0_bgr, use_double=True)
print(f"rtmdet f32 sum  : {t_f32.sum().item():.8f}")
print(f"rtmdet f64 sum  : {t_f64.sum().item():.8f}")
print(f"rtmdet f32 hash : {h(t_f32.numpy())}")
print(f"rtmdet f64 hash : {h(t_f64.numpy())}")
# Déterminisme
t_f64b = preprocess_rtmdet(frame0_bgr, use_double=True)
print(f"rtmdet f64 déterministe (même machine) : {torch.equal(t_f64, t_f64b)}")

# ═══════════════════════════════════════════════════════════════════════════════
sep("6. INFÉRENCE C3D (RISK) — résultat numérique complet")

try:
    from starhe_plugin.ai.starhe_risk import STARHERiskModel
    risk_model = STARHERiskModel()
    result = risk_model.predict(frames_clean)
    print(f"risk_score  : {result['risk_score']:.10f}  ({result['risk_score']*100:.4f} %)")
    print(f"risk_label  : {result['risk_label']}")
    print(f"scores raw  : {[f'{s:.10f}' for s in result['scores']]}")
except Exception as e:
    print(f"[ERR RISK] {e}")

# ═══════════════════════════════════════════════════════════════════════════════
sep("7. INFÉRENCE RTMDet (DETECT) — scores borderline (0.60–0.80)")

try:
    from starhe_plugin.ai.starhe_detect import STARHEDetectModel

    # score_thr bas pour voir tous les scores borderline autour de 0.70
    _LOW_THR = 0.60

    with STARHEDetectModel() as det_model:
        stride = 4
        frames_for_det = frames_clean
        n = len(frames_for_det)
        borderline = []
        total_above_070 = 0

        for i in range(0, n, stride):
            frame_rgb = frames_for_det[i]   # (H, W, 3) uint8 RGB — predict attend RGB
            dets = det_model.predict(frame_rgb, score_thr=_LOW_THR)
            for d in dets:
                sc = d["score"]
                if sc >= 0.70:
                    total_above_070 += 1
                if _LOW_THR <= sc < 0.75:
                    borderline.append((i, round(sc, 6)))

        print(f"Frames analysées (stride={stride})  : {len(range(0, n, stride))}/{n}")
        print(f"Détections ≥ 0.70                   : {total_above_070}")
        print(f"Scores borderline [0.60–0.75[ :")
        for frame_i, sc in sorted(borderline):
            marker = " ← BASCULE POSSIBLE" if 0.68 <= sc <= 0.72 else ""
            print(f"  frame {frame_i:4d}  score={sc:.6f}{marker}")

except Exception as e:
    import traceback
    print(f"[ERR DETECT] {e}")
    traceback.print_exc()

sep("FIN — compare ces lignes entre Mac et Windows")
print("Les premières lignes qui diffèrent indiquent l'étape source du problème.")
