# 🔬 STARHE Plugin — MEDomics Extension

> **ST**ratification du risque et détection précoce du **C**arcinome **H**épatocellulaire (**E**chographie)  
> Module d'analyse de ciné-clips échographiques intégré à la plateforme [MEDomics](https://medomicslab.gitbook.io/medomics-docs).

*Version du plug-in : `0.1.0` — Stack MEDomics : Electron / React / Go / Python 3.13 / MongoDB*  
*Dernière mise à jour : **25 mars 2026***

---

## 📋 Description du Projet

Le **Plug-in STARHE** est une extension modulaire de la plateforme MEDomics permettant l'analyse automatisée de flux vidéo échographiques (ciné-clips DICOM) dans le cadre du dépistage du **carcinome hépatocellulaire (CHC)**.

Il repose sur deux modèles d'intelligence artificielle développés dans le cadre du projet STARHE :

| Modèle | Architecture | Rôle |
|---|---|---|
| **STARHE-RISK** | C3D (3D-CNN) | Stratification du risque (score 0–1 : faible / élevé) |
| **STARHE-DETECT** | DINO-DETR | Détection et localisation de lésions hépatiques |

Le pipeline complet gère l'ensemble du flux : lecture DICOM → extraction de frames → anonymisation → prétraitement prepUS (crop + backscan) → inférence IA → persistance MongoDB.

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
- 🐍 **Moteur d'inférence** : Python 3.13 (pydicom, OpenCV, PyTorch)
- 🧹 **Prétraitement** : [prepUS](https://github.com/MEDomics-UdeS/prepUS) — crop + scan conversion
- 🗄 **Base de données** : MongoDB (local, port 27017)
- 🔗 **Communication Go ↔ Python** : stdout JSON (`go_print`)

---

## 📁 Structure du Répertoire

```
f:\STAGE\PROJET\PLUGIN1-MEDomics\
│
├── README.md                          # Ce fichier
├── TODOLIST.md                        # Carnet de bord opérationnel
├── MEDomicsLab_LOGO.png               # Logo affiché dans l'UI prototype
├── run_tkinter.ps1                    # Lanceur du prototype (venv Python 3.13)
│
└── pythonCode/
    └── modules/
        └── starhe_plugin/             # 📦 Racine du plug-in Python
            │
            ├── __init__.py            # Hooks on_load / on_unload (MEDomics lifecycle)
            ├── config.py              # Constantes, chemins, hyperparamètres
            ├── pipeline.py            # Orchestrateur principal du flux de traitement
            ├── requirements.txt       # Dépendances Python
            │
            ├── ai/                    # 🤖 Wrappers des modèles IA (stubs)
            │   ├── __init__.py
            │   ├── starhe_risk.py     # Modèle C3D — classification du risque CHC
            │   └── starhe_detect.py   # Modèle DINO-DETR — détection de lésions
            │
            ├── db/                    # 🗄 Couche de persistance MongoDB
            │   ├── __init__.py
            │   └── mongo_client.py    # CRUD : save_result, get_result, list_results
            │
            ├── dicom/                 # 🏥 Traitement des fichiers DICOM
            │   ├── __init__.py
            │   ├── reader.py          # Lecture .dcm, extraction de frames, normalisation
            │   ├── anonymizer.py      # Anonymisation / hachage des tags sensibles
            │   ├── prepus_bridge.py   # ✅ CŒUR — intégration API prepUS (crop + backscan)
            │   └── crop.py            # Algo maison (fallback si prepUS indisponible)
            │
            ├── ui/                    # 🖼 Prototype de validation (Tkinter)
            │   ├── __init__.py
            │   └── prototype_tkinter.py  # GUI MEDomics-style : DICOM, prepUS, IA, console
            │
            └── utils/                 # 🔧 Utilitaires
                ├── __init__.py
                └── go_print.py        # Protocole JSON stdout → Go Server

# Dépendance externe vendorisée (incluse dans le dépôt)
third_party/prepUS/
    └── prepUS/                        # Package prepUS — copie locale, aucune dépendance machine
```

---

## ✨ Fonctionnalités Clés

### 🏥 Parsing, Anonymisation & Nettoyage DICOM
- Lecture de fichiers `.dcm` **et fichiers DICOM sans extension** (`A0000`, `IM-0001`…) via `pydicom` avec `force=True`
- Mono-frame et ciné-clips multi-frames supportés ; extraction en tableau NumPy, normalisation vers `uint8`
- Anonymisation des **15 tags DICOM sensibles** (PatientName, PatientID, StudyDate, UIDs…) en deux modes :
  - **`hash`** : remplacement par SHA-256 tronqué (16 chars) — traçabilité conservée
  - **`remove`** : suppression complète du tag
- **Suppression du bandeau imageur** (`remove_pixel_burnin`) — noircit automatiquement les lignes supérieures contenant les informations patient brûlées dans les pixels (PHI pixel burn-in) ; détection par analyse de luminosité, sans hauteur fixe codée en dur
- **Extraction du pixel spacing** pour calibration de la mesure : priorité `PixelSpacing` → `ImagerPixelSpacing` → `SequenceOfUltrasoundRegions` (PhysicalDeltaX/Y en cm)

### 🧹 Prétraitement — prepUS (`prepus_bridge.py`)
Intégration directe de l'API `prepUS.removeLayoutFile` :
1. Les frames DICOM sont exportées vers un MP4 temporaire (OpenCV)
2. `removeLayoutFile` détecte les pixels statiques (UI, texte, règles) par analyse temporelle
3. Le masque binaire est rogné → coordonnées de crop stockées dans `info.json`
4. **Toujours avec backscan activé** : production de `backscan_video.mp4` (512×512) **et** `video.mp4` (crop masqué) en une seule passe
5. La checkbox **Backscan (512×512)** dans l'UI bascule en temps réel entre les deux vues sans relancer le traitement
6. Le dossier temporaire est nettoyé automatiquement

### 🤖 Inférence IA
- **STARHE-RISK** : normalise un clip en `(16, 112, 112)` frames, passe par le modèle C3D, retourne un score de risque `[0.0–1.0]` et un label `Faible` / `Élevé`
- **STARHE-DETECT** : redimensionne chaque frame à `800×800`, passe par DINO-DETR, retourne des bounding boxes avec score de confiance et label de lésion (seuil configurable : `0.45`)
- ⚠️ Les deux modèles sont actuellement des **stubs** — les vrais poids `.pth` ne sont pas encore intégrés

### 🗄 Stockage des Résultats
- Persistance dans MongoDB : chemins de fichiers, nombre de frames, coordonnées ROI, score de risque, détections, mode d'anonymisation, horodatage
- API CRUD : `save_result`, `get_result`, `list_results`, `delete_result`

### 🖼 Interface Prototype (Tkinter)
- Thème **MEDomics v1.8.0** : sidebar `#151521`, fond principal `#f4f6fb`, bleu `#1565C0`
- Logo **MEDomicsLab_LOGO.png** intégré dans le header
- Chargement de fichiers DICOM `.dcm` **et fichiers sans extension** (ex. `A0000`, `IM-0001`) grâce à `force=True` dans pydicom
- Navigation frames avec scrollbar horizontale, boutons ◀/▶, et lecture automatique à vitesse configurable
- **Vitesse de lecture configurable** — champ FPS dans la sidebar, délai recalculé dynamiquement
- **Mode boucle** — checkbox activant la répétition infinie de la séquence
- **Bouton Revenir au début** — remet la lecture au frame 0
- Bouton **⚙ Pré-Traitement** — lance prepUS avec `back_scan_conversion=True` dans un thread dédié ; la checkbox **Backscan (512×512)** détermine le mode d'**affichage** sans relancer le traitement
- Badge de mode en temps réel sur la carte (`ORIGINAL` / `BACKSCAN 512×512` / `CROP + MASQUE`)
- **Menu contextuel clic droit** (7 options) sur le canvas :
  - **Pan / Zoom** — glisser pour déplacer, molette pour zoomer
  - **Outil de mesure** — clic-glisser, overlay jaune avec distance en **millimètres** calibrée depuis `SequenceOfUltrasoundRegions` ou `PixelSpacing`
  - **Défilement de séries** — molette pour naviguer entre les frames
  - **Contraste** / **Luminosité** — fenêtres flottantes avec curseur et bouton reset
  - **Réinitialiser la vue** — remet zoom/pan/contraste/luminosité à zéro
- En-têtes de section avec barre d'accent bleue (style MEDomics)
- Résultats colorés dynamiquement (vert risque faible, rouge risque élevé)
- Toggle thème clair / sombre
- Console de logs colorée intégrée

### 🔗 Communication Go ↔ Python
- Protocole `go_print` : émission de **lignes JSON préfixées** vers stdout
  - `go_print(level, message)` — logs info/warning/error
  - `go_progress(step, pct, detail)` — progression en temps réel
  - `go_result(data)` — résultat structuré final

---

## 🚀 Guide d'Exécution

### Prérequis
- Python 3.13 (venv dans `pythonCode/modules/starhe_plugin/.venv`)
- MongoDB (service local sur `localhost:27017`)
- Go 1.21+ (pour le serveur MEDomics)
- Node.js 18+ (pour le frontend)
- prepUS installé dans le venv : voir ci-dessous

### 1️⃣ Installer les dépendances Python

```powershell
cd pythonCode\modules\starhe_plugin
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# prepUS et ses dépendances (vendorisés dans third_party/)
# run_tkinter.ps1 s'en charge automatiquement, ou manuellement :
.venv\Scripts\pip install sonocrop --no-deps
.venv\Scripts\pip install third_party\prepUS --no-deps
```

### 2️⃣ Placer les poids des modèles *(non disponibles — stubs actifs)*

```
pythonCode/modules/starhe_plugin/models/
├── starhe_risk_c3d.pth
└── starhe_detect_dino_detr.pth
```

### 3️⃣ Lancer le prototype Tkinter

```powershell
# Depuis la racine du projet
.\run_tkinter.ps1
```

### 4️⃣ Lancer le pipeline Python (test standalone)

```python
from starhe_plugin.pipeline import run_pipeline

results = run_pipeline(
    dicom_path="F:\\STAGE\\DATA\\01-0009-F-Y_Bmode.dcm",
    anon_mode="hash",
    run_detection=True
)
print(results)
```

### 5️⃣ Lancer le serveur Go (MEDomics — à venir)

```bash
go run main.go
```

### 6️⃣ Lancer le frontend React (MEDomics — à venir)

```bash
npm run dev
```

---

## ⚙️ Configuration

Tous les paramètres configurables sont centralisés dans [`config.py`](pythonCode/modules/starhe_plugin/config.py) :

| Paramètre | Valeur par défaut | Description |
|---|---|---|
| `CROP_BLACK_THRESHOLD` | `10` | Seuil luminosité pour détection fond noir (fallback crop.py) |
| `C3D_INPUT_DEPTH` | `16` | Nombre de frames pour C3D |
| `C3D_INPUT_HEIGHT/WIDTH` | `112` | Taille spatiale input C3D |
| `DINO_INPUT_SIZE` | `(800, 800)` | Taille input DINO-DETR |
| `DETECT_SCORE_THRESHOLD` | `0.45` | Score confiance min pour affichage détection |
| `MONGO_URI` | `mongodb://localhost:27017/` | URI MongoDB locale |

---

*Version du plug-in : `0.1.0` — Stack MEDomics : Electron / React / Go / Python 3.13 / MongoDB — Dernière mise à jour : **25 mars 2026***
