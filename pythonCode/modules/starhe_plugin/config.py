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

# ── Poids des modèles IA ──────────────────────────────────────────────────────
STARHE_RISK_WEIGHTS   = os.path.join(MODELS_DIR, "starhe_risk_c3d.pth")
STARHE_DETECT_WEIGHTS = os.path.join(MODELS_DIR, "starhe_detect_dino_detr.pth")

# ── Paramètres de pré-traitement DICOM ───────────────────────────────────────
# Seuil de luminosité (0–255) en dessous duquel un pixel est considéré comme
# appartenant au fond noir de l'échographe
CROP_BLACK_THRESHOLD = 10

# Pourcentage minimal de pixels non-noirs requis pour valider une ligne/colonne
# comme faisant partie de la zone utile
CROP_MIN_CONTENT_RATIO = 0.01

# Taille cible des clips pour le modèle C3D (T x H x W)
C3D_INPUT_DEPTH  = 16
C3D_INPUT_HEIGHT = 112
C3D_INPUT_WIDTH  = 112

# Taille cible pour DINO-DETR
DINO_INPUT_SIZE = (800, 800)

# Score de confiance minimum pour afficher une détection
DETECT_SCORE_THRESHOLD = 0.45

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
