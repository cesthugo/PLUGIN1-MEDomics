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
DATA_DIR     = r"F:\STAGE\DATA"
MODELS_DIR   = os.path.join(BASE_DIR, "models")
TEMP_DIR     = os.path.join(BASE_DIR, "temp")

# Package Python `starhe` vendorisé (copié dans ai/vendor/ — autonome)
VENDOR_DIR   = os.path.join(BASE_DIR, "ai", "vendor")

# Création automatique des dossiers s'ils n'existent pas
for _d in (DATA_DIR, MODELS_DIR, TEMP_DIR):
    os.makedirs(_d, exist_ok=True)

# ── Modèles STARHE (artefacts locaux — autonomes, sans dépendance externe) ────

# Classification (STARHE-RISK) — C3D PyTorch pur
STARHE_RISK_CONFIG     = os.path.join(MODELS_DIR, "c3d_starhe.py")
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

# ── Paramètres de pré-traitement DICOM ───────────────────────────────────────
CROP_BLACK_THRESHOLD   = 10
CROP_MIN_CONTENT_RATIO = 0.01

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI        = "mongodb://localhost:27017/"
MONGO_DB_NAME    = "medomics"
MONGO_COLLECTION = "starhe_results"

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
