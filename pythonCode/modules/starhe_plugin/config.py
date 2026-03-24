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

# data/ est à la racine du dépôt, là où l'utilisateur dépose ses fichiers .dcm
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")
MODELS_DIR   = os.path.join(BASE_DIR, "models")
TEMP_DIR     = os.path.join(BASE_DIR, "temp")

# Création automatique des dossiers s'ils n'existent pas
for _d in (DATA_DIR, MODELS_DIR, TEMP_DIR):
    os.makedirs(_d, exist_ok=True)

# ── Modèles STARHE (artefacts entraînés — chemin local machine) ───────────────
# Répertoire racine du dépôt starhe partagé (contient le package Python `starhe`)
STARHE_SHARE_ROOT  = r"F:\STAGE\starhe_share\starhe_share"
# Sous-dossier models/
STARHE_MODELS_ROOT = os.path.join(STARHE_SHARE_ROOT, "models")

# Classification (STARHE-RISK) — C3D via mmaction2
STARHE_RISK_CONFIG     = os.path.join(STARHE_MODELS_ROOT, "classification", "c3d_starhe.py")
STARHE_RISK_CHECKPOINT = os.path.join(STARHE_MODELS_ROOT, "classification", "best_acc_mean_cls_f1_epoch_14.pth")

# Détection (STARHE-DETECT) — RTMDet via mmdet
STARHE_DETECT_CONFIG     = os.path.join(STARHE_MODELS_ROOT, "det", "bs_4", "rtmdet_starhe.py")
STARHE_DETECT_CHECKPOINT = os.path.join(STARHE_MODELS_ROOT, "det", "bs_4", "best_coco_bbox_mAP_50_iter_2100.pth")

# Score de confiance minimum pour afficher une détection
DETECT_SCORE_THRESHOLD = 0.45

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
