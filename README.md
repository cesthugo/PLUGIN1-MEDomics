# STARHE Plugin — MEDomics

> **STARHE** = STratification du risque et détection du carcinome **H**épatocellulaire par **E**chographie.  
> Extension Python/Go de la plateforme [MEDomics](https://medomicslab.gitbook.io/medomics-docs).

*Version `0.1.0` — Dernière mise à jour : 7 avril 2026*

---

## Vue d'ensemble

Le plug-in analyse des ciné-clips DICOM d'échographie abdominale pour dépister le carcinome hépatocellulaire (CHC). Il s'intègre à MEDomics via un serveur Go qui orchestre l'exécution du pipeline Python et streame les résultats au frontend React via SSE (Server-Sent Events).

Deux modèles IA sont exploités :

| Modèle | Architecture | Tâche | Checkpoint |
|---|---|---|---|
| **STARHE-RISK** | C3D (3D-CNN, PyTorch pur) | Classification binaire : risque CHC faible / élevé | `models/best_acc_mean_cls_f1_epoch_14.pth` |
| **STARHE-DETECT** | RTMDet (mmdet) ou DINO-DETR | Détection et localisation de lésions hépatiques | `models/best_coco_bbox_mAP_50_iter_2100.pth` |

---

## Prérequis

| Outil | Version minimale | Notes |
|---|---|---|
| Python | 3.13 | tkinter inclus ; 3.14 incompatible (tkinter cassé). Sur macOS Homebrew : `brew install python@3.13 python-tk@3.13` |
| MongoDB | 4.x+ | Service local sur le port **54017** (non standard) |
| Go | 1.21+ | Requis uniquement pour le serveur REST |
| Node.js | 18+ | Requis uniquement pour le frontend MEDomics |
| CUDA (optionnel) | 11.8+ | Inférence GPU ; CPU utilisé si absent |

> **Port MongoDB 54017** : MEDomics utilise délibérément un port non standard pour éviter les conflits avec les instances MongoDB système. Ce port est codé dans `config.py` ET dans `go_server/config.go`.

---

## Installation et démarrage

### 1. Créer le venv Python 3.13

> **Toutes les commandes ci-dessous supposent que vous êtes dans le dossier racine du projet** (`PLUGIN1-MEDomics/`).

**Windows (PowerShell) :**
```powershell
py -3.13 -m venv pythonCode\modules\starhe_plugin\.venv
pythonCode\modules\starhe_plugin\.venv\Scripts\pip install -r pythonCode\modules\starhe_plugin\requirements.txt
```

**macOS / Linux :**
```bash
python3.13 -m venv pythonCode/modules/starhe_plugin/.venv
pythonCode/modules/starhe_plugin/.venv/bin/pip install -r pythonCode/modules/starhe_plugin/requirements.txt
```

> **macOS (Homebrew)** : Python 3.13 s'installe via `brew install python@3.13`. Homebrew **n'inclut pas tkinter par défaut** — il faut aussi lancer `brew install python-tk@3.13`, sinon l'UI Tkinter échouera avec `ModuleNotFoundError: No module named '_tkinter'`. Vérifier avec : `python3.13 -c "import tkinter"`.

### 2. Lancer le prototype Tkinter (développement)

> Se placer à la racine du projet (`PLUGIN1-MEDomics/`).

**Windows (PowerShell) :**
```powershell
.\run_tkinter.ps1
```

**macOS / Linux :**
```bash
./run_tkinter.sh
```

Le script `run_tkinter.sh` est **autonome** : il vérifie que Python 3.13 et tkinter sont présents sur le système, crée le venv et installe les dépendances si absent, installe prepUS, puis lance l'UI. Un nouvel utilisateur sur Mac n'a besoin que de deux prérequis système :

```bash
# Prérequis une seule fois
brew install python@3.13 python-tk@3.13
# Puis lancer le prototype depuis la racine du projet (tout le reste est automatique)
./run_tkinter.sh
```

<details>
<summary>Commandes manuelles équivalentes (macOS / Linux)</summary>

> Depuis la racine du projet (`PLUGIN1-MEDomics/`) :

```bash
PYTHON=pythonCode/modules/starhe_plugin/.venv/bin/python
PREPUS=third_party/prepUS
"$PYTHON" -c "import prepUS" 2>/dev/null || {
    "$PYTHON" -m pip install sonocrop --no-deps -q
    "$PYTHON" -m pip install "$PREPUS" --no-deps -q
}
cd pythonCode/modules
../../"$PYTHON" -m starhe_plugin.ui.prototype_tkinter
```

</details>

### 3. Lancer le serveur Go (intégration MEDomics)

> Depuis la racine du projet (`PLUGIN1-MEDomics/`) :

**Windows / macOS / Linux :**
```bash
cd go_server
go run .
# Écoute sur http://localhost:8080 (PORT modifiable via variable d'environnement)
```

Les chemins Python sont détectés **automatiquement** par `config.go` à partir du dossier `go_server/` (chemin relatif `../pythonCode/modules/…`). Aucune variable d'environnement n'est nécessaire si le venv a été créé à l'étape 1 et que le serveur est lancé depuis `go_server/`.

Variables d'environnement du serveur Go :

| Variable | Défaut | Description |
|---|---|---|
| `PORT` | `8080` | Port HTTP du serveur |
| `STARHE_PYTHON_EXE` | chemin absolu dans `config.go` | Python 3.13 du venv |
| `STARHE_PYTHON_PATH` | chemin absolu dans `config.go` | Dossier racine des modules Python |
| `MONGO_URI` | `mongodb://localhost:54017/` | URI MongoDB |
| `MONGO_DB` | `medomics` | Nom de la base |
| `MONGO_COLL` | `starhe_results` | Nom de la collection |

---

## Architecture

```
MEDomics Frontend (React)
        │ HTTP / SSE
        ▼
  Go Server (port 8080)
  go_server/main.go      → routing HTTP
  go_server/handlers.go  → logique, subprocess Python, SSE streaming
  go_server/config.go    → variables d'environnement
        │ subprocess os/exec  (stdout pipe, ligne par ligne)
        ▼
  Python Engine
  starhe_plugin/pipeline.py  → orchestrateur principal
        │
        ├── dicom/reader.py        → lecture DICOM (pydicom)
        ├── dicom/anonymizer.py    → anonymisation tags
        ├── dicom/prepus_bridge.py → prétraitement prepUS
        ├── ai/starhe_risk.py      → STARHE-RISK (C3D, PyTorch)
        ├── ai/starhe_detect.py    → STARHE-DETECT (RTMDet subprocess serveur)
        │       └── ai/models/_rtmdet_runner.py  (subprocess secondaire)
        ├── db/mongo_client.py     → persistance MongoDB (pymongo)
        └── utils/go_print.py      → protocole stdout vers Go
```

### Protocole Go ↔ Python (`go_print`)

Chaque ligne de sortie Python respecte le format :

```
GO_PRINT|<niveau>|<message JSON>
```

Niveaux : `info`, `warning`, `error`, `progress`, `result`.

Le serveur Go parse chaque ligne avec `bufio.Scanner` et la relaie en SSE au frontend :

```
data: {"level":"progress","message":"Chargement DICOM…","data":{"step":1,"total":6}}
data: {"level":"result","message":"Pipeline terminé","data":{...}}
data: [DONE]
```

En mode UI Tkinter, le sink peut être redirigé vers un callback Python via `set_log_sink()` (voir `utils/go_print.py`) — les lignes n'atteignent pas stdout.

---

## Pipeline d'analyse (`pipeline.py`)

```
run_pipeline(dicom_path, anon_mode, run_detection, back_scan_conversion, ...)
```

Étapes dans l'ordre :

1. **Chargement DICOM** — `load_dicom()` avec `pydicom force=True` (supporte les fichiers sans extension).
2. **Anonymisation** — mode `"hash"` (SHA-256 tronqué) ou `"remove"`. Les 16 tags DICOM sensibles sont définis dans `config.DICOM_SENSITIVE_TAGS`. L'anonymisation est réversible côté UI (les valeurs originales sont sauvegardées en mémoire avant anonymisation).
3. **Extraction des frames** — `extract_frames()` retourne `(T, H, W)` ou `(T, H, W, 3)` en `uint8`.
4. **Prétraitement prepUS** — voir section dédiée ci-dessous.
5. **STARHE-RISK** — inférence C3D sur le clip complet.
6. **STARHE-DETECT** — inférence RTMDet frame par frame (avec sous-échantillonnage temporel).
7. **Sauvegarde MongoDB** — upsert sur `file_path`.

---

## Prétraitement prepUS (`dicom/prepus_bridge.py`)

prepUS est le preprocesseur d'images ultrasonores de MEDomics. Il est **vendorisé** dans `third_party/prepUS/` pour s'affranchir d'une dépendance externe.

### Ce que fait prepUS

- Détecte et supprime les éléments statiques de l'interface de l'échographe (texte, règles, bordures) par analyse de la variabilité temporelle des pixels.
- Crop le cône US pour supprimer les marges noires.
- Effectue une conversion scan inverse (backscan) : reconstruction de l'image dans un espace cartésien 512×512, ce qui corrige la distorsion du secteur de l'ultrason.

### Appel dans le code

```python
backscan_frames, crop_only_frames, info = preprocess_with_prepus(
    frames_rgb,                 # (T, H, W, 3) uint8 RGB
    back_scan_conversion=True,
    backscan_width=512,
    backscan_height=512,
)
```

Retourne un tuple `(backscan, crop_only, info_dict)` :
- `backscan` : `(T, 512, 512)` uint8 gris — utilisé pour l'inférence IA
- `crop_only` : `(T, H_crop, W_crop)` uint8 gris — utilisé pour la visualisation
- `info_dict` : clés `crop` (xmin/ymin/xmax/ymax), paramètres backscan

### Implémentation interne

1. Export des frames numpy → MP4 temporaire (OpenCV `VideoWriter`)
2. Appel `prepUS.cli.removeLayoutFile(mp4, out_dir, back_scan_conversion=True, ...)`
3. Lecture de `out_dir/backscan_video.mp4` → numpy
4. Lecture de `out_dir/video.mp4` (crop sans backscan) → numpy
5. Lecture de `out_dir/infos.json` → dict ROI
6. Nettoyage du dossier temporaire

> **Attention** : prepUS doit être installé avec `--no-deps` pour éviter les conflits avec la version OpenCV du venv. Le script `run_tkinter.ps1` gère cela automatiquement.

---

## Modèle STARHE-RISK (C3D)

### Architecture

C3D est un réseau convolutif 3D (spatiotemporel) défini dans `ai/models/c3d.py` en PyTorch pur — **sans dépendance mmaction2/mmcv** à l'exécution.

```
Entrée : (N, 3, 16, 112, 112)  — N clips, 3 canaux, 16 frames, 112×112
  conv1a → pool1
  conv2a → pool2
  conv3a → conv3b → pool3
  conv4a → conv4b → pool4
  conv5a → conv5b → pool5
  flatten → fc6(4096) → relu → dropout
            fc7(4096) → relu
  tête I3DHead : fc_cls(2) → softmax
Sortie : (N, 2)  — proba [risque_faible, risque_élevé]
```

### Pourquoi PyTorch pur sans mmaction2

Le checkpoint `.pth` a été entraîné avec mmaction2 (framework mmcv). Pour éviter les conflits de dépendances (mmcv incompatible Python 3.13), les noms des sous-modules (`backbone.conv1a.conv.weight`, `cls_head.fc_cls.weight`, etc.) sont **reproduits exactement** dans `c3d.py`. Le checkpoint se charge donc directement avec `torch.load` sans remise en correspondance des clés.

### Prétraitement d'un clip

```python
clips = preprocess_clips(frames)  # retourne (10, 3, 16, 112, 112)
```

- **10 clips** échantillonnés uniformément sur toute la durée (`NUM_CLIPS=10`)
- Chaque clip : 16 frames consécutives (`clip_len=16`)
- Resize → 128px (petit côté), center crop → 112×112
- Normalisation : `mean=[104, 117, 128]`, `std=[1, 1, 1]` (valeurs BGR, pas de division par 255)

### Inférence

```python
logits = model(clips)           # (10, 2)
probs  = softmax(logits, dim=1) # (10, 2)
avg    = probs.mean(dim=0)      # (2,)  — moyenne des 10 clips
risk_score = avg[1]             # probabilité classe "risque élevé"
```

Seuil d'affichage : aucun seuil appliqué, le score brut [0–1] est retourné.

---

## Modèle STARHE-DETECT (RTMDet)

### Problème : mmcv incompatible Python 3.13

mmdet/mmcv utilise des extensions C compilées (`mmcv._ext`) et des métadonnées de frame Python 2 incompatibles avec Python 3.13. La solution adoptée est un **subprocess isolé** qui exécute le runner RTMDet dans un contexte où les patches nécessaires sont appliqués.

### Architecture subprocess persistant

```
starhe_detect.py (processus principal)
        │
        │  os.Popen([python, _rtmdet_runner.py, --mode server, ...])
        ▼
    _rtmdet_runner.py (subprocess)
        │ applique 3 patches AVANT tout import mmcv :
        │   1. stub mmcv._ext (remplace l'extension C absente)
        │   2. stub tqdm (facultatif, évite une ImportError)
        │   3. patch inspect.getmodule (Python 3.13 / mmengine compat)
        │
        │ charge le modèle RTMDet (428 MB) UNE SEULE FOIS
        │ émet "READY" sur stdout
        │
        │ boucle stdin/stdout JSON
        ▼
    {"type":"batch","images":["base64...", ...], "score_thr": 0.70}
        │
    [[{"bbox":[x0,y0,x1,y1],"score":0.87,"label":"tumor"}], [...], ...]
```

### Séquence d'initialisation

1. `STARHEDetectModel.__init__()` appelle `_start_server()`
2. `_start_server()` lance le subprocess avec `--mode server`
3. Attente bloquante de la ligne `[rtmdet_server] READY` sur stdout
4. Toute autre ligne = échec → `RuntimeError` avec les 2000 derniers caractères de stderr

### Envoi d'un batch de frames

```python
# Dans predict_batch(frames) :
payload = {
    "type":      "batch",
    "images":    [base64(png(frame)) for frame in frames],
    "score_thr": score_thr,
}
proc.stdin.write(json.dumps(payload) + "\n")
proc.stdin.flush()
response = json.loads(proc.stdout.readline())
# response = [[det, ...], [det, ...], ...]  — une liste par frame
```

### Sous-échantillonnage temporel

Dans `pipeline.py`, seule 1 frame sur `DETECT_EVERY_N=4` est envoyée au modèle. Les 3 frames intermédiaires héritent des mêmes détections :

```python
for i in range(0, n_frames, stride):
    dets = detect_model.predict(frames[i])
    for j in range(i, min(i + stride, n_frames)):
        detections_per_frame[j] = dets
```

Gain pratique : ×4 sur le temps d'inférence, négligeable sur la précision (les lésions bougent peu d'une frame à l'autre).

### Backend DINO (alternatif)

Défini dans `ai/models/_dino_runner.py`. Pas de mode serveur — chaque frame lance un subprocess séparé (lent, à n'utiliser qu'en développement). Sélectionnable via `DETECT_BACKEND = "dino"` dans `config.py`.

---

## Base de données MongoDB

### Connexion

Port local `54017` (non standard, configuré dans `config.py` et `go_server/config.go`). Chaque appel `_get_collection()` ouvre une connexion avec timeout 3s — pas de pool global côté Python (pymongo gère son propre pool).

### Schéma d'un document

```json
{
  "_id"                  : "<ObjectId>",
  "file_path"            : "/chemin/absolu/fichier.dcm",
  "processed_at"         : "2026-04-01T14:22:11Z",
  "num_frames"           : 180,
  "roi"                  : [x0, y0, x1, y1],
  "risk"                 : {"score": 0.82, "label": "Risque élevé"},
  "detections_per_frame" : [
    [],
    [{"bbox": [120, 80, 200, 160], "score": 0.91, "label": "tumor"}],
    []
  ],
  "anon_mode"            : "hash",
  "analysis_mode"        : "backscan"
}
```

- `detections_per_frame` est une **liste de listes** indexée sur les frames, longueur = `num_frames`.
- La clé de cache est le couple `(file_path, analysis_mode)` — un document par fichier **et par mode** d'analyse (`original`, `crop`, `backscan`). Sensible au déplacement/renommage du fichier.
- `replace_one({file_path: ..., analysis_mode: ...}, doc, upsert=True)` : un document par combinaison fichier + mode.

### Opérations disponibles (`db/mongo_client.py`)

```python
save_result(file_path, num_frames, roi, risk, detections_per_frame, anon_mode, analysis_mode)
find_by_file(file_path, analysis_mode=None)  # → dict | None  (filtre optionnel par mode)
get_result(result_id)     # → dict | None  (par ObjectId string)
list_results(limit=100)   # → list[dict]
delete_result(file_path)  # → bool
```

---

## Serveur Go (`go_server/`)

### Endpoints

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/health` | Healthcheck |
| `POST` | `/starhe/analyze` | Lance pipeline.py et streame via SSE |
| `GET` | `/starhe/results` | Liste les résultats (paramètre `?limit=N`) |
| `GET` | `/starhe/results/{id}` | Un résultat par ObjectId |
| `DELETE` | `/starhe/results/{id}` | Supprime un résultat |

### `POST /starhe/analyze`

Corps JSON :
```json
{
  "dicom_path"           : "/chemin/absolu/fichier.dcm",
  "anon_mode"            : "hash",
  "run_detection"        : true,
  "back_scan_conversion" : true,
  "backscan_width"       : 512,
  "backscan_height"      : 512
}
```

Le handler lance `python -m starhe_plugin.pipeline` en subprocess, lit chaque ligne `GO_PRINT|...` et la relaie en SSE. Le flux se termine par `data: [DONE]`.

### CORS

Le middleware `withCORS` dans `main.go` ajoute les headers `Access-Control-Allow-*` pour tous les endpoints — nécessaire pour que le frontend React (Electron) puisse appeler l'API.

---

## Interface prototype Tkinter (`ui/prototype_tkinter.py`)

Le prototype sert à valider le pipeline et l'UX avant le portage React. C'est un fichier unique d'environ 2500 lignes.

### Points techniques non évidents

**Subprocess persistant RTMDet** : côté UI, `STARHEDetectModel` est utilisé exactement comme dans `pipeline.py`, dans un thread `threading.Thread` pour ne pas bloquer l'interface.

**Onglets multi-fichiers** : chaque onglet stocke un `dict` d'état complet (~30 clés : frames brutes, frames prepUS, index courant, mesures, zoom, contraste, résultats IA par mode, métadonnées, etc.). La méthode `_save_tab_state()` copie les variables `self._xxx` dans `self._tabs[i]`, et `_restore_tab_state(i)` fait l'inverse. Aucune donnée n'est rechargée depuis le disque lors d'un changement d'onglet.

**Résultats par mode d'affichage** : les détections et résultats sont stockés dans des dicts indexés par mode (`_detections_by_mode` et `_results_by_mode`, clés : `"backscan"`, `"crop"`, `"original"`). Quand l'utilisateur bascule entre les modes (toggle crop/backscan), seuls les bounding boxes et résultats correspondant au mode actif sont affichés. La méthode `_refresh_results_panel()` met à jour les labels Mode, Risque, et Lésions en conséquence.

**Mesures en mm** : la calibration s'effectue dans l'ordre de priorité suivant dans les métadonnées DICOM :
1. `SequenceOfUltrasoundRegions` (tag `(0018,6011)`) — physicalDeltaX/Y en cm
2. `PixelSpacing` (tag `(0028,0030)`) — en mm
3. `ImagerPixelSpacing` (tag `(0018,1164)`) — en mm

La valeur `pixel_spacing` (mm/px) est stockée dans l'état de l'onglet et utilisée par `_draw_measure_overlay()` pour afficher la distance en mm.

**Boucle de lecture** : la méthode `_tick()` est appelée via `self.after(delay_ms, self._tick)`. Le délai est calculé depuis `FrameTime` DICOM (en ms) divisé par `_speed_mult`. Pour les vitesses ≥1, des frames sont sautées (`_skip_n`) au lieu de diminuer le délai (limité à ~15ms par `after`).

**go_print côté UI** : à l'initialisation, `set_log_sink(lambda level, msg: self._append_log(msg))` redirige tous les messages vers la console de l'interface. Le sink est réinitialisé à `None` à la fermeture.

**Zoom et pan** : toutes les coordonnées canvas sont recalculées à chaque `_refresh_canvas()` en appliquant la transformation affine `(x * zoom + pan_x, y * zoom + pan_y)`. Les images sont redimensionnées via `PIL.Image.resize` avec `LANCZOS`.

**Anonymisation à l'import** : les valeurs originales sont sauvegardées dans `original_sensitive` (liste de tuples `(nom_tag, valeur)`) avant anonymisation. Elles sont affichées en rouge dans le panneau métadonnées. Les valeurs anonymisées sont dans `kept_metadata`.

### Raccourcis clavier

Un guard `_kb_guard()` vérifie que le focus n'est pas sur un widget de texte (`tk.Entry`, `tk.Text`, `scrolledtext.ScrolledText`) avant d'exécuter le raccourci — évite les interférences avec la saisie utilisateur.

---

## Compatibilité Python 3.13

Python 3.13 a introduit plusieurs changements incompatibles avec mmcv/mmdet. Voici les patches appliqués dans `_rtmdet_runner.py` **avant tout import mmcv** :

### 1. Stub `mmcv._ext`

mmcv tente d'importer une extension C compilée `mmcv._ext` (`NMSop`, etc.). Cette extension n'existe pas dans les versions récentes ou avec des builds incompatibles. Le stub remplace le module par un objet Python dont chaque attribut lève une `RuntimeError` uniquement si appelé :

```python
class _CExtStub(types.ModuleType):
    def __getattr__(self, name):
        def _unavailable(*a, **kw):
            raise RuntimeError(f"mmcv._ext.{name}: C-extension absente.")
        return _unavailable
sys.modules["mmcv._ext"] = _CExtStub("mmcv._ext")
```

L'inférence RTMDet n'utilise pas en pratique les fonctions NMS de l'extension (PyTorch fournit les siennes).

### 2. Patch `inspect.getmodule`

mmengine (dépendance de mmdet) appelle `inspect.getmodule()` sur des objets de frame Python. En Python 3.13, cela peut lever `AttributeError` ou `OSError` dans certains contextes. Le patch enveloppe l'appel original dans un try/except et retourne `None` en cas d'échec (comportement tolerable pour mmengine).

### 3. Stub `tqdm`

tqdm n'est pas dans les dépendances mmdet. Si absent, mmdet lève une `ImportError` à l'import. Le stub injecte un module minimal où `tqdm.tqdm(iterable)` retourne l'itérable tel quel.

---

## Structure complète du projet

```
PLUGIN1-MEDomics/
│
├── run_tkinter.ps1                   # Lanceur UI prototype Windows (installe prepUS auto)
├── run_tkinter.sh                    # Lanceur UI prototype macOS/Linux (installe prepUS auto)
├── README.md                         # Ce fichier
├── READMEUtilisateur.md              # Guide utilisateur de l'interface Tkinter
├── TODOLIST.md                       # Carnet de bord / roadmap
├── MEDomicsLab_LOGO.png              # Logo affiché dans l'UI
│
├── go_server/
│   ├── main.go                       # Routing HTTP + init MongoDB
│   ├── config.go                     # Variables d'environnement avec valeurs par défaut
│   └── handlers.go                   # Handlers REST + SSE streaming
│
├── third_party/
│   └── prepUS/                       # Package prepUS vendorisé (pip install --no-deps)
│
└── pythonCode/modules/starhe_plugin/
    │
    ├── .venv/                        # Environnement virtuel Python 3.13 (non versionné)
    ├── __init__.py                   # Hooks on_load() / on_unload() (cycle de vie MEDomics)
    ├── config.py                     # Toutes les constantes, chemins, hyperparamètres
    ├── pipeline.py                   # Orchestrateur principal (point d'entrée Go)
    ├── requirements.txt              # Dépendances Python
    │
    ├── ai/
    │   ├── starhe_risk.py            # Wrapper C3D : chargement + inférence
    │   ├── starhe_detect.py          # Wrapper RTMDet/DINO : subprocess serveur
    │   └── models/
    │       ├── c3d.py                # Architecture C3D en PyTorch pur (sans mmaction2)
    │       ├── _rtmdet_runner.py     # Runner RTMDet (mode image + mode serveur)
    │       ├── _dino_runner.py       # Runner DINO-DETR (mode image uniquement)
    │       ├── rtmdet.py             # Stubs RTMDet pour chargement config mmdet
    │       └── dino.py               # Stubs DINO-DETR
    │
    ├── db/
    │   └── mongo_client.py           # CRUD MongoDB (save/find/list/delete)
    │
    ├── dicom/
    │   ├── reader.py                 # Chargement DICOM, extraction frames, uint8
    │   ├── anonymizer.py             # Anonymisation tags + suppression bandeau imageur
    │   ├── prepus_bridge.py          # Intégration prepUS (export MP4 → frames numpy)
    │   └── crop.py                   # Algo de crop maison (fallback si prepUS indisponible)
    │
    ├── ui/
    │   └── prototype_tkinter.py      # Interface prototype (~2500 lignes)
    │
    └── utils/
        └── go_print.py               # Protocole stdout Go ↔ Python + set_log_sink()
```

---

## Configuration (`config.py`)

Tous les paramètres sont dans un seul fichier. Les chemins sont relatifs au projet — aucune adaptation nécessaire sur une nouvelle machine :

```python
DATA_DIR   = os.environ.get("STARHE_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))  # Dossier des fichiers DICOM
MODELS_DIR = os.path.join(BASE_DIR, "models")   # Checkpoints IA (non versionnés)
```

`DATA_DIR` pointe par défaut vers `data/` à la racine du projet. Surchargeable via la variable d'environnement `STARHE_DATA_DIR`.

Paramètres IA :

| Paramètre | Valeur | Effet |
|---|---|---|
| `DETECT_BACKEND` | `"rtmdet"` | Changer en `"dino"` pour tester DINO-DETR |
| `DETECT_SCORE_THRESHOLD` | `0.70` | Seuil de confiance minimum, affecte l'affichage et le cache |
| `DETECT_EVERY_N` | `4` | Sous-échantillonnage temporel (1 = toutes les frames) |
| `DETECT_BATCH_SIZE` | `4` | Taille des lots envoyés au subprocess RTMDet |

---

## Limitations connues et points d'attention

- **Clé de cache MongoDB = chemin absolu** : si le fichier DICOM est déplacé ou renommé, l'analyse est relancée même si elle a déjà été effectuée.
- **Changement d'onglet pendant une analyse** : l'analyse tourne dans un thread séparé et continue même si l'onglet source est fermé. Les résultats sont perdus si l'onglet est fermé avant la fin.
- **prepUS et backscan** : le backscan ne fonctionne que sur des images sectorielles (mode B standard). Les images linéaires (vaisseaux superficiels) peuvent produire un backscan dégradé — utiliser `back_scan_conversion=False` dans ce cas.
- **GPU** : STARHE-RISK passe automatiquement sur CUDA si disponible. STARHE-DETECT (RTMDet en subprocess) utilise CPU par défaut ; ajouter `--device cuda` dans le cmd de `_start_server()` pour activer le GPU.

---

## Autres documents

- [READMEUtilisateur.md](READMEUtilisateur.md) — Guide d'utilisation de l'interface Tkinter
- [TODOLIST.md](TODOLIST.md) — Carnet de bord, tâches accomplies et roadmap
