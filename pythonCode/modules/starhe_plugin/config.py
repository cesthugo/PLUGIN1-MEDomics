"""
config.py — Configuration centrale du plug-in STARHE
======================================================
Toutes les constantes, chemins et hyperparamètres sont
centralisés ici pour faciliter la maintenance.
"""

import os

# ── Chemins de base ───────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))

# Racine du dépôt (3 niveaux au-dessus de starhe_plugin/ → PLUGIN1-MEDomics/)
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))

# Dossier des fichiers DICOM (données locales de travail)
# Configurable via variable d'environnement STARHE_DATA_DIR ;
# par défaut : dossier "data/" à la racine du projet.
DATA_DIR     = os.environ.get("STARHE_DATA_DIR",
                              os.path.join(PROJECT_ROOT, "data"))
MODELS_DIR   = os.path.join(BASE_DIR, "models")
TEMP_DIR     = os.path.join(BASE_DIR, "temp")

# Package Python `starhe` vendorisé (copié dans ai/vendor/ — autonome)
VENDOR_DIR   = os.path.join(BASE_DIR, "ai", "vendor")

# Création automatique des dossiers s'ils n'existent pas
for _d in (MODELS_DIR, TEMP_DIR):
    os.makedirs(_d, exist_ok=True)

# ── Modèles STARHE (artefacts locaux — autonomes, sans dépendance externe) ────

# Classification (STARHE-RISK) — C3D PyTorch pur
STARHE_RISK_CHECKPOINT = os.path.join(MODELS_DIR, "best_acc_mean_cls_f1_epoch_14.pth")

# Détection (STARHE-DETECT) — modèle actif : "rtmdet" | "dino"
DETECT_BACKEND = "rtmdet"

# Détection — RTMDet (défaut)
STARHE_DETECT_CONFIG     = os.path.join(MODELS_DIR, "rtmdet_starhe.py")
STARHE_DETECT_CHECKPOINT = os.path.join(MODELS_DIR, "best_coco_bbox_mAP_50_iter_2100.pth")

# Détection — DINO-DETR (optionnel)
# Le config hérite de _base_/ via chemins relatifs → structure configs/ maintenue
STARHE_DINO_CONFIG     = os.path.join(MODELS_DIR, "configs", "custom", "dino_starhe.py")
STARHE_DINO_CHECKPOINT = os.path.join(MODELS_DIR, "best_coco_bbox_mAP_50_iter_2100.pth")

# Racine à ajouter au sys.path pour `import starhe` (package vendorisé)
# Contient : vendor/starhe/__init__.py
STARHE_SHARE_ROOT = VENDOR_DIR

# Score de confiance minimum pour afficher une détection
DETECT_SCORE_THRESHOLD = 0.70

# Échantillonnage temporel DETECT : 1 frame analysée toutes les N
# Les N-1 frames intermédiaires héritent des détections de la frame analysée
# 1 = toutes les frames (désactivé), 4 = gain ×4 (recommandé)
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

# ── Reproductibilité cross-plateforme ────────────────────────────────────────
# Lorsque True, les deux modèles (RISK et DETECT) sont forcés sur CPU en
# float64.  Float64 réduit l'erreur d'arrondi BLAS (MKL↔Accelerate) de ~1e-4
# (float32) à ~1e-13 (float64), rendant les scores identiques bit-à-bit entre
# Windows et macOS pour un même fichier DICOM.
#
# RISK  : "30.1% mac" vs "29.9% windows" → source : BLAS MKL↔Accelerate
#         (float32 accumulation differ by ~0.002).  Float64 → identique.
# DETECT: "48 frames mac" vs "44 frames windows" → source PRINCIPALE :
#         Mac utilise MPS (Apple Silicon GPU), Windows utilise CPU → arithmétique
#         complètement différente → scores borderline basculent autour de 0.70.
#         Float64 sur CPU → identique sur les deux plateformes.
#
# Coût : ~2–3× plus lent sur CPU.  Désactiver (False) pour la prod rapide.
DETERMINISTIC_INFERENCE: bool = True

# ── Bypass roundtrip MP4 dans prepUS ─────────────────────────────────────────
# `cv2.VideoWriter(mp4v)` produit un bitstream dépendant du binaire FFmpeg lié
# à OpenCV (macOS ARM Homebrew ≠ Linux ≠ Windows). Le pipeline standard écrit
# `input.mp4` puis relit `video.mp4`, ce qui rend les crops C3D non-portables
# entre OS pour le MÊME DICOM d'entrée.
#
# True  : calcul prepUS 100 % numpy (preprocess_with_prepus_inmem). Sortie
#         identique bit-à-bit cross-plateforme. Léger écart vs distribution
#         d'entraînement (qui a vu des crops avec artefacts mp4v).
# False : pipeline historique (preprocess_with_prepus) — reproduit exactement
#         le chemin d'entraînement de Jérémy sur la même plateforme.
PREPUS_BYPASS_MP4: bool = False

# ── Seuil de décision STARHE-RISK ────────────────────────────────────────────
# Probabilité minimale (classe 1 = risque élevé) pour qualifier un patient
# de « Risque élevé ».
#
# 0.50 = comportement argmax (défaut mmaction2 / Analyse A en entraînement)
# 0.60 = réduit les faux positifs Supersonic au prix d'une sensibilité moindre
#
# Calibration sur ce jeu de test (47 patients) :
#   Seuil 0.50 → Sens=90.9%  Spec=52.0%  Acc=70.2%  F1=0.741
#   Seuil 0.60 → Sens=77.3%  Spec=64.0%  Acc=70.2%  F1=0.708
#   Réf C3D    → Sens=77.3%  Spec=72.0%  Acc=74.5%
RISK_THRESHOLD: float = 0.50

# ── Paramètres de pré-traitement DICOM ───────────────────────────────────────
CROP_BLACK_THRESHOLD   = 10
CROP_MIN_CONTENT_RATIO = 0.01

# ── MongoDB ───────────────────────────────────────────────────────────────────
# Surchargeable via variables d'environnement (cohérent avec go_server/config.go)
MONGO_URI        = os.environ.get("MONGO_URI",  "mongodb://localhost:54017/")
MONGO_DB_NAME    = os.environ.get("MONGO_DB",   "medomics")
MONGO_COLLECTION = os.environ.get("MONGO_COLL", "starhe_results")

# ── Tags DICOM à anonymiser ───────────────────────────────────────────────────
# (groupe, élément) selon le standard DICOM PS3.15 Annexe E
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
