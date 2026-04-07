# 📋 TODOLIST — Plug-in STARHE / MEDomics
> Carnet de bord opérationnel du projet.  
> Dernière mise à jour : **7 avril 2026**

---

## ✅ Tâches Accomplies

### 🍴 Mise en place du projet
- [x] **Fork du dépôt MEDomics** — Branche de développement créée
- [x] **Analyse de l'architecture MEDomics** — Stack (Electron / React / Go / Python / MongoDB), communication Go ↔ Python via stdout JSON
- [x] **Environnement Python 3.13** — venv dans `starhe_plugin/.venv`, résolution conflit Python 3.14/Tkinter
- [x] **`.gitignore`** — exclusion `*.exe`, `*.pth`, `__pycache__`, `.venv`, `temp/`, `*.egg-info`, `build/`

### 🏗 Architecture du plug-in Python
- [x] **`config.py`** — Centralisation de toutes les constantes (chemins, seuils, tags DICOM, paramètres MongoDB)
- [x] **`__init__.py` racine** — Hooks `on_load()` / `on_unload()` conformes à la philosophie MEDomics
- [x] **`requirements.txt`** — Dépendances Python complètes

### 🏥 Module DICOM (`dicom/`)
- [x] **`reader.py`** — Lecture `.dcm` et fichiers sans extension (`force=True`), extraction frames, normalisation `uint8`
- [x] **`anonymizer.py`** — Anonymisation 15 tags DICOM sensibles (modes `hash` et `remove`) + `remove_pixel_burnin()`
- [x] **`crop.py`** — Algo maison spatial + temporel (fallback si prepUS indisponible)
- [x] **`prepus_bridge.py`** — Intégration API prepUS : `preprocess_with_prepus()` — double sortie (backscan 512×512 + crop seul) en une passe

### 🧹 Intégration prepUS
- [x] **Installation** : `sonocrop --no-deps` + `prepUS --no-deps` + `fire` + `rich` dans le venv
- [x] **Correctif JSON** : `_NpEncoder` dans `prepUS/cli.py` pour les types numpy (`float32`, `int64`)
- [x] **Double sortie** : retour `(backscan_array, crop_only_array, info_dict)` en une seule passe

### 🤖 Module IA (`ai/`)
- [x] **`starhe_risk.py`** — Wrapper C3D : preprocessing `(16, 112, 112)`, inférence, score `[0–1]` + label risque
- [x] **`starhe_detect.py`** — Wrapper RTMDet/DINO : classe `STARHEDetectModel` avec :
  - [x] Subprocess **persistant** (mode serveur) — modèle chargé une seule fois
  - [x] Context manager `__enter__`/`__exit__` + `close()` propre
  - [x] Méthode `predict_batch(frames)` — N frames en une seule passe réseau
  - [x] Fallback one-shot en cas d'erreur serveur
- [x] **`ai/models/_rtmdet_runner.py`** — Runner RTMDet avec :
  - [x] Mode `--mode server` : boucle stdin/stdout JSON, signal `READY`, `__EXIT__`
  - [x] Protocole batch : `{"images": [...]}` → `[[dets], ...]`
  - [x] Patchs Python 3.13 : stubs mmcv._ext, NMSop, inspect.getmodule
- [x] **`config.py` seuils** : `DETECT_SCORE_THRESHOLD=0.70`, `DETECT_EVERY_N=4`, `DETECT_BATCH_SIZE=4`

### 🗄 Module Base de données (`db/`)
- [x] **`mongo_client.py`** — CRUD MongoDB : `save_result` (upsert), `find_by_file`, `get_result`, `list_results`, `delete_result`
- [x] **Port MongoDB** : `54017` (config.py + go_server/config.go)
- [x] **Cache automatique** : `find_by_file(path)` vérifié avant toute inférence ; `save_result` avec `replace_one(..., upsert=True)`
- [x] **Schéma** : `detections_per_frame` — liste de listes (une par frame), indexée sur `file_path`

### 🔀 Orchestration
- [x] **`pipeline.py`** — Orchestrateur DICOM → anonymisation → prepUS → STARHE-RISK → STARHE-DETECT (batch + stride) → MongoDB

### 🖼 Prototype UI Tkinter
- [x] **Interface MEDomics v1.8.0** — Sidebar `#151521`, fond `#f4f6fb`, bleu `#1565C0`, Segoe UI
- [x] **Navigation** — Boutons ◀/▶, scrollbar horizontale ttk, lecture automatique
- [x] **Vitesse de lecture** — Slider ×-multiplicateur style YouTube (0.25× à 3.0×), calibré depuis `FrameTime` DICOM
  - Logique : skip N frames par tick (×≥1) ou allongement d'intervalle (×<1)
- [x] **Frames détectées cliquables** — Après analyse, liste des numéros 1-based en bleu cliquable ; clic navigue directement vers ce frame
- [x] **Cache MongoDB** dans l'UI — si fichier déjà analysé, résultats restitués instantanément
- [x] **Sauvegarde MongoDB** après analyse — `save_result()` appelé en fin de thread
- [x] **Menu contextuel clic droit** (7 options) : Pan/Zoom, mesure mm, séries, contraste, luminosité, réinitialisation
- [x] **Outil de mesure en mm** — overlay jaune calibré depuis `SequenceOfUltrasoundRegions` / `PixelSpacing`
- [x] **Toggle thème clair/sombre**
- [x] **Badge de mode** sur la carte : `ORIGINAL` / `BACKSCAN 512×512` / `CROP + MASQUE`
- [x] **Anonymisation automatique** à l'import (15 tags + bandeau imageur noirci)
- [x] **Métadonnées affichées** : conservées (vert) + anonymisées originales (rouge)
- [x] **Sidebar scrollable**
- [x] **Bouton unique ⚙ Pré-Traitement** avec indicateur d'état
- [x] **Bouton 🗑 Réinitialiser l'analyse** (sidebar rouge) — efface le cache MongoDB du fichier courant et réinitialise entièrement l'UI
- [x] **Label Mode dans RÉSULTATS** — badge dynamique indiquant le mode d'affichage actif : `Backscan 512×512`, `Pré-traitement (crop)` ou `Original`
- [x] **Clic droit maintenu** → contraste (axe X) / luminosité (axe Y) en direct ; clic droit bref (<0,25 s) → menu contextuel 7 options
- [x] **Glisser gauche vertical** (mode normal) → défilement de frames (1 frame / 8 px)
- [x] **Mesures multiples simultanées** — plusieurs segments tracés en parallèle ; sélection par clic (contour orange), édition d'extrémité par glisser (point), déplacement du segment entier, suppression via Delete/BackSpace
- [x] **Raccourcis clavier** (18 bindings) — Espace (lecture), ←/→ (±1 frame), Shift+←/→ (±10 frames), Home/End, P/M/S (modes), Échap (déselect/reset), R (réinitialiser vue), C/L (contraste/luminosité), +/- (vitesse), B (boucle), Ctrl+Tab / Ctrl+Shift+Tab (onglets), Ctrl+W (fermer onglet)
- [x] **Système d'onglets multi-fichiers** — `askopenfilenames` pour charger N fichiers en une sélection, barre d'onglets en bas de la visionneuse, label = `StudyDate` formatée JJ/MM/AAAA (fallback : nom de fichier), sauvegarde/restauration complète de l'état par onglet (frames, zoom, mesures, contraste…), fermeture individuelle (×), navigation Ctrl+Tab
- [x] **Bug `delete_result()` MongoDB** corrigé — filtre par champ string `file_path` au lieu d'ObjectId

### 🔧 Séparation par mode d'affichage (7 avril)
- [x] **Bounding boxes par mode** — `_detections_by_mode` (dict : `"backscan"` / `"crop"` / `"original"` → `list[list[dict]]`). Quand l'utilisateur bascule entre modes, seules les détections du mode actif sont dessinées sur le canvas
- [x] **Panneau Résultats par mode** — `_results_by_mode` (dict → textes risque/détection par mode), méthode `_refresh_results_panel()` met à jour les labels Mode, Risque CHC, et Lésions selon le mode courant
- [x] **Cache MongoDB par mode** — Clé composite `(file_path, analysis_mode)` au lieu de `file_path` seul ; `find_by_file(path, analysis_mode=...)` filtre par mode ; un fichier peut avoir des résultats distincts par mode
- [x] **Sauvegarde/restauration onglets** — `_capture_tab_state()` / `_restore_tab_state()` intègrent `detections_by_mode` et `results_by_mode`
- [x] **Compatibilité macOS sélecteur fichiers** — Suppression du filtre `filetypes` sur Darwin (fichiers DICOM sans extension invisibles sinon)

### 🔗 Go Server
- [x] **`go_server/main.go`** — Endpoints : GET /health, POST /starhe/analyze (SSE), GET/DELETE /starhe/results
- [x] **`go_server/config.go`** — Port MongoDB `54017`, chemins venv Python configurables par var d'env
- [x] **`go_server/handlers.go`** — Streaming SSE `GO_PRINT|` depuis Python

---

## 🚧 Tâches en Cours

### 🐍 Backend Python
- [ ] **Tests du pipeline bout en bout** — Valider `run_pipeline()` avec un fichier `.dcm` réel sur données hépatiques

### 🖼 Prototype Tkinter
- [ ] **Validation flux complet avec Canon Aplio i700** — Charger `A0000` → suppression bandeau + calibration mm → prepUS → inférence IA → affichage résultats + cache MongoDB
- [ ] **Recueil de retours utilisateur** — Identifier les ajustements UX avant portage en React

---

## 📅 Roadmap — Prochaines Étapes

### 🔬 Phase 1 : Validation Backend (Court terme)

- [ ] **Écriture des tests unitaires**
  - `reader.py` : chargement, nombre de frames, shape des arrays
  - `anonymizer.py` : vérifier que les 15 tags sont bien effacés/hachés
  - `prepus_bridge.py` : valider crop + backscan sur un DICOM de référence
  - `mongo_client.py` : test round-trip save/find/delete
  - *Démarche : créer `pythonCode/modules/starhe_plugin/tests/` avec `pytest`*

- [ ] **Optimisation Phase 2 : GPU**
  - Configurer le runner RTMDet pour utiliser CUDA si disponible (`--device cuda`)
  - Gain estimé : ×10–20 sur la partie détection (RTX 30/40 : ~15–30ms/frame)

### 🔀 Phase 2 : Intégration Go Server (Moyen terme)

- [ ] **Gestionnaire de progression en temps réel**
  - Câbler les événements `go_progress()` de Python vers le frontend via SSE

- [ ] **Gestion des erreurs et timeouts**
  - Timeout configurable pour l'inférence IA
  - Codes d'erreur HTTP sémantiques avec messages JSON structurés

### ⚙ Phase 3 : Portage UI React (Long terme)

- [ ] **Composant `<DicomLoader />`** — Upload et validation d'un fichier `.dcm`
- [ ] **Composant `<FrameViewer />`** — Visualisation frames, navigation, toggle crop/backscan
- [ ] **Composant `<InferenceResults />`** — Score STARHE-RISK, bboxes, liste frames détectées cliquables
- [ ] **Composant `<AnalysisConsole />`** — Logs en temps réel (SSE)
- [ ] **Intégration dans le système de navigation MEDomics**

### 🧪 Phase 4 : Tests & Déploiement (Long terme)

- [ ] **Tests d'intégration bout en bout** — Frontend React → Go → Python → MongoDB
- [ ] **Documentation API Go** — Swagger / OpenAPI
- [ ] **Packaging du plug-in** — Compatibilité système d'extensions MEDomics

---

## 📝 Procédures Techniques Clés

### 🧹 Prétraitement prepUS
> `preprocess_with_prepus(frames, fps, thresh, back_scan_conversion, backscan_width, backscan_height)`
> 1. Export numpy → MP4 temporaire (OpenCV)
> 2. `removeLayoutFile(mp4, out_dir, ...)` — détection pixels statiques + masquage + crop
> 3. Toujours appelé avec `back_scan_conversion=True` → double sortie en une passe
> 4. Retourne `(backscan_array, crop_only_array, info_dict)` + nettoyage tmp
> ⚠️ prepUS doit être installé avec `--no-deps` pour éviter les conflits OpenCV

### 🐍 Subprocess persistant RTMDet
> 1. `STARHEDetectModel.__init__()` lance `_rtmdet_runner.py --mode server`
> 2. Attente du signal `[rtmdet_server] READY` sur stdout
> 3. Chaque lot de frames : `{"images": [...], "score_thr": 0.70}` via stdin → `[[dets], ...]` via stdout
> 4. `__EXIT__` ferme proprement le serveur
> 5. Fallback automatique vers one-shot si erreur

### 🗄 Cache MongoDB
> 1. Au lancement de l'analyse : `find_by_file(path, analysis_mode)` — si résultat trouvé pour ce mode, restitution immédiate
> 2. Après analyse : `save_result(file_path, ..., detections_per_frame=per_frame, analysis_mode=mode)` avec upsert
> 3. Clé de cache = couple `(file_path, analysis_mode)` — un même fichier peut avoir des résultats distincts pour chaque mode (original, crop, backscan)

### 🔗 Communication Go ↔ Python
> Lancer Python en subprocess depuis Go : `os/exec.Command("python", "-m", "starhe_plugin.pipeline", args...)`
> Chaque ligne stdout de Python est préfixée `GO_PRINT:` suivi d'un JSON.
> Parser côté Go avec `bufio.Scanner` + `json.Unmarshal` — relayer via SSE.

---

*🔖 Ce fichier est maintenu manuellement. Mettre à jour au fil des sprints.*
