# 🔬 STARHE Plugin — MEDomics Extension

> **ST**ratification du risque et détection précoce du **C**arcinome **H**épatocellulaire (**E**chographie)  
> Module d'analyse de ciné-clips échographiques intégré à la plateforme [MEDomics](https://github.com/MEDomics-UdeS/MEDomics).

---

## 📋 Description du Projet

Le **Plug-in STARHE** est une extension modulaire de la plateforme MEDomics permettant l'analyse automatisée de flux vidéo échographiques (ciné-clips DICOM) dans le cadre du dépistage du **carcinome hépatocellulaire (CHC)**.

Il repose sur deux modèles d'intelligence artificielle développés dans le cadre du projet STARHE :

| Modèle | Architecture | Rôle |
|---|---|---|
| **STARHE-RISK** | C3D (3D-CNN) | Stratification du risque (score 0–1 : faible / élevé) |
| **STARHE-DETECT** | DINO-DETR | Détection et localisation de lésions hépatiques |

Le pipeline complet gère l'ensemble du flux : lecture DICOM → extraction de frames → anonymisation → crop → inférence IA → persistance MongoDB.

---

## 🏗 Architecture & Stack

Le plug-in s'inscrit dans l'architecture full-stack de MEDomics :

```
┌─────────────────────────────────────────────────────────────────┐
│                        MEDomics Platform                        │
│                                                                 │
│  ┌────────────────┐    ┌──────────────────┐                     │
│  │  Frontend      │    │   Electron Shell  │                     │
│  │  React/Next.js │◄───│  (main process)   │                     │
│  └───────┬────────┘    └────────┬─────────┘                     │
│          │ HTTP/REST            │ IPC                           │
│  ┌───────▼────────────────────┐                                 │
│  │       Go Server (API)      │  ← blueprints STARHE            │
│  │  go_server/blueprints/     │                                 │
│  └───────┬────────────────────┘                                 │
│          │ subprocess / stdout JSON                             │
│  ┌───────▼────────────────────┐   ┌──────────────────────┐     │
│  │   Python Engine (STARHE)   │──►│  MongoDB (local)      │     │
│  │   pythonCode/modules/      │   │  db: medomics         │     │
│  │   starhe_plugin/           │   │  col: starhe_results  │     │
│  └────────────────────────────┘   └──────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

**Technologies utilisées :**
- 🖥 **Frontend** : React / Next.js (portage UI à venir)
- ⚡ **Shell** : Electron
- 🔀 **API** : Go Server (blueprints REST)
- 🐍 **Moteur d'inférence** : Python 3.10+ (pydicom, OpenCV, PyTorch)
- 🗄 **Base de données** : MongoDB (local, port 27017)
- 🔗 **Communication Go ↔ Python** : stdout JSON (`go_print`)

---

## 📁 Structure du Répertoire

```
f:\STAGE\PROJET\PLUGIN1-MEDomics\
│
├── README.md                          # Ce fichier
├── TODOLIST.md                        # Carnet de bord opérationnel
│
├── pythonCode/
│   └── modules/
│       └── starhe_plugin/             # 📦 Racine du plug-in Python
│           │
│           ├── __init__.py            # Hooks on_load / on_unload (MEDomics lifecycle)
│           ├── config.py              # Constantes, chemins, hyperparamètres
│           ├── pipeline.py            # Orchestrateur principal du flux de traitement
│           ├── requirements.txt       # Dépendances Python
│           │
│           ├── ai/                    # 🤖 Wrappers des modèles IA
│           │   ├── __init__.py
│           │   ├── starhe_risk.py     # Modèle C3D — classification du risque CHC
│           │   └── starhe_detect.py   # Modèle DINO-DETR — détection de lésions
│           │
│           ├── db/                    # 🗄 Couche de persistance MongoDB
│           │   ├── __init__.py
│           │   └── mongo_client.py    # CRUD : save_result, get_result, list_results
│           │
│           ├── dicom/                 # 🏥 Traitement des fichiers DICOM
│           │   ├── __init__.py
│           │   ├── reader.py          # Lecture .dcm, extraction de frames, normalisation
│           │   ├── crop.py            # Détection ROI + crop de la zone échographique
│           │   └── anonymizer.py      # Anonymisation / hachage des tags sensibles
│           │
│           ├── ui/                    # 🖼 Prototype de validation (Tkinter)
│           │   ├── __init__.py
│           │   └── prototype_tkinter.py  # GUI complète : navigation frames, IA, console
│           │
│           └── utils/                 # 🔧 Utilitaires
│               ├── __init__.py
│               └── go_print.py        # Protocole JSON stdout → Go Server
│
└── (à venir)
    ├── go_server/
    │   └── blueprints/
    │       └── starhe.go              # Routes REST exposant le pipeline Python
    └── renderer/
        └── src/
            └── components/
                └── starhe/            # Portage React de l'UI Tkinter
```

---

## ✨ Fonctionnalités Clés

### 🏥 Parsing & Anonymisation DICOM
- Lecture de fichiers `.dcm` (mono-frame et ciné-clips multi-frames) via `pydicom`
- Extraction des frames pixel en tableau NumPy, normalisation vers `uint8`
- Anonymisation des **15 tags DICOM sensibles** (PatientName, PatientID, StudyDate, UIDs…) en deux modes :
  - **`hash`** : remplacement par SHA-256 tronqué (16 chars) — traçabilité conservée
  - **`remove`** : suppression complète du tag

### ✂️ Preprocessing — Crop automatique
- Détection de la **zone d'intérêt (ROI)** par seuillage de luminosité, opérations morphologiques et analyse de contours (OpenCV)
- Suppression automatique du cadre et des annotations de la machine échographique
- Application cohérente du même ROI à toutes les frames d'un ciné-clip

### 🤖 Inférence IA
- **STARHE-RISK** : normalise un clip en `(16, 112, 112)` frames, passe par le modèle C3D, retourne un score de risque `[0.0–1.0]` et un label `low_risk` / `high_risk`
- **STARHE-DETECT** : redimensionne chaque frame à `800×800`, passe par DINO-DETR, retourne des bounding boxes avec score de confiance et label de lésion (seuil configurable : `0.45`)

### 🗄 Stockage des Résultats
- Persistance dans MongoDB : chemins de fichiers, nombre de frames, coordonnées ROI, score de risque, détections, mode d'anonymisation, horodatage
- API CRUD : `save_result`, `get_result`, `list_results`, `delete_result`

### 🔗 Communication Go ↔ Python
- Protocole `go_print` : émission de **lignes JSON préfixées** vers stdout
  - `go_print(level, message)` — logs info/warning/error
  - `go_progress(step, pct, detail)` — progression en temps réel
  - `go_result(data)` — résultat structuré final

---

## 🚀 Guide d'Exécution

### Prérequis
- Python 3.10+
- MongoDB (service local sur `localhost:27017`)
- Go 1.21+ (pour le serveur MEDomics)
- Node.js 18+ (pour le frontend)

### 1️⃣ Installer les dépendances Python

```bash
cd f:\STAGE\PROJET\PLUGIN1-MEDomics\pythonCode\modules\starhe_plugin
pip install -r requirements.txt
```

### 2️⃣ Placer les poids des modèles

```
pythonCode/modules/starhe_plugin/models/
├── starhe_risk_c3d.pth
└── starhe_detect_dino_detr.pth
```

### 3️⃣ Lancer le pipeline Python (test standalone)

```python
from starhe_plugin.pipeline import run_pipeline

results = run_pipeline(
    dicom_path="chemin/vers/votre_fichier.dcm",  # déposer le .dcm dans data/
    anonymize_mode="hash",   # ou "remove"
    run_risk=True,
    run_detect=True
)
print(results)
```

### 4️⃣ Lancer le prototype Tkinter (validation UI)

> ⚠️ **Important** : ne pas utiliser `python` directement — le terminal peut avoir le mauvais venv actif (Python 3.14, Tcl/Tk cassé).  
> Utiliser le script launcher à la racine qui appelle **toujours** le bon exécutable Python 3.13 :

```powershell
# Depuis la racine du projet (peu importe le venv actif)
cd F:\STAGE\PROJET\PLUGIN1-MEDomics
.\run_tkinter.ps1
```

### 5️⃣ Lancer le serveur Go (MEDomics — à venir)

```bash
# Depuis la racine du projet MEDomics forké
go run main.go
```

### 6️⃣ Lancer le frontend React (MEDomics — à venir)

```bash
npm run dev
```

---

## ⚙️ Configuration

Tous les paramètres configurables sont centralisés dans [`pythonCode/modules/starhe_plugin/config.py`](pythonCode/modules/starhe_plugin/config.py) :

| Paramètre | Valeur par défaut | Description |
|---|---|---|
| `CROP_BLACK_THRESHOLD` | `10` | Seuil luminosité pour détection fond noir |
| `CROP_MIN_CONTENT_RATIO` | `0.01` | Ratio min pixels utiles par ligne/colonne |
| `C3D_INPUT_DEPTH` | `16` | Nombre de frames pour C3D |
| `C3D_INPUT_HEIGHT/WIDTH` | `112` | Taille spatiale input C3D |
| `DINO_INPUT_SIZE` | `(800, 800)` | Taille input DINO-DETR |
| `DETECT_SCORE_THRESHOLD` | `0.45` | Score confiance min pour affichage détection |
| `MONGO_URI` | `mongodb://localhost:27017/` | URI MongoDB locale |

---

## 👥 Contributeurs

- **MEDomics Team** — Architecture plateforme
- **Projet STARHE** — Modèles IA (STARHE-RISK, STARHE-DETECT)

---

*Version du plug-in : `0.1.0` — Stack MEDomics : Electron / React / Go / Python / MongoDB*
