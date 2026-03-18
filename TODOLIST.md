# 📋 TODOLIST — Plug-in STARHE / MEDomics
> Carnet de bord opérationnel du projet.  
> Dernière mise à jour : **18 mars 2026**

---

## ✅ Tâches Accomplies

### 🍴 Mise en place du projet
- [x] **Fork du dépôt MEDomics** — Dépôt principal forké, branche de développement `feature/starhe-plugin` créée
- [x] **Analyse de l'architecture MEDomics** — Étude du stack (Electron / React / Go / Python / MongoDB), compréhension du système de communication Go ↔ Python via stdout JSON, repérage des points d'intégration (`go_server`, `renderer/`)
- [x] **Résolution des problèmes d'accès** — Contournement des blocages antivirus sur le disque `F:` (exclusions Windows Defender), résolution des conflits de `PATH` pour Python et Go sous Windows
- [x] **Environnement Python 3.13** — Création du venv dans `starhe_plugin/.venv`, résolution du conflit Python 3.14/Tkinter

### 🏗 Architecture du plug-in Python
- [x] **Définition de la structure de répertoires** — Création de `pythonCode/modules/starhe_plugin/` avec les sous-modules `ai/`, `db/`, `dicom/`, `ui/`, `utils/`
- [x] **`config.py`** — Centralisation de toutes les constantes (chemins, seuils, tags DICOM, paramètres MongoDB)
- [x] **`__init__.py` racine** — Hooks de cycle de vie `on_load()` / `on_unload()` conformes à la philosophie MEDomics
- [x] **`requirements.txt`** — Dépendances Python complètes avec section prepUS

### 🏥 Module DICOM (`dicom/`)
- [x] **`reader.py`** — Lecture `.dcm`, extraction frames mono/multi-frames, normalisation `uint8`, détection ciné-clips
- [x] **`anonymizer.py`** — Anonymisation de 15 tags DICOM sensibles (modes `hash` SHA-256 et `remove`), fonctions `anonymize()` et `anonymize_file()`
- [x] **`crop.py`** — Algo maison spatial + temporel — fallback si prepUS indisponible
- [x] **`scan_conversion.py` supprimé** — Backscan maison par transformée de Hough — supersédé par prepUS et retiré du dépôt
- [x] **`prepus_bridge.py`** — ✅ **Intégration API prepUS** : `preprocess_with_prepus()` — crop + backscan via `removeLayoutFile`, retourne `(backscan_array, crop_only_array, info_dict)`
- [x] **`dicom/__init__.py` nettoyé** — Imports `find_fov_geometry`, `scan_convert_frame`, `scan_convert_clip` retirés (plus de dépendance à `scan_conversion`)

### 🧹 Intégration prepUS
- [x] **Installation** : `sonocrop --no-deps` + `prepUS --no-deps` + `fire` + `rich` dans le venv
- [x] **Correctif JSON** : ajout de `_NpEncoder` dans `prepUS/cli.py` pour les types numpy (`float32`, `int64`)
- [x] **Gestion backscan off** : reconstruction du crop depuis `info.json` quand `back_scan_conversion=False` (prepUS ne sauvegarde pas de vidéo dans ce cas)
- [x] **Double sortie** : `prepus_bridge` retourne les deux arrays (backscan 512×512 + crop seul) en une seule passe

### 🤖 Module IA (`ai/`)
- [x] **`starhe_risk.py`** — Wrapper C3D : preprocessing `(16, 112, 112)`, inférence, retour score `[0–1]` + label risque *(stub — poids non disponibles)*
- [x] **`starhe_detect.py`** — Wrapper DINO-DETR : preprocessing `800×800`, inférence, retour bounding boxes filtrées *(stub — poids non disponibles)*

### 🗄 Module Base de données (`db/`)
- [x] **`mongo_client.py`** — CRUD MongoDB complet : `save_result`, `get_result`, `list_results`, `delete_result`

### 🔧 Module Utilitaires (`utils/`)
- [x] **`go_print.py`** — Protocole JSON stdout : `go_print()`, `go_progress()`, `go_result()`

### 🔀 Orchestration
- [x] **`pipeline.py`** — Orchestrateur complet DICOM → frames → anonymisation → prétraitement prepUS (crop + backscan) → STARHE-RISK → STARHE-DETECT → MongoDB

### 🖼 Prototype UI Tkinter
- [x] **Interface MEDomics v1.8.0** — Sidebar `#151521`, fond `#f4f6fb`, bleu `#1565C0`, Segoe UI
- [x] **Logo MEDomicsLab_LOGO.png** intégré dans le header (PNG avec gestion transparence)
- [x] **Navigation** — Boutons ◀/▶, lecture automatique ~22 fps, scrollbar horizontale ttk
- [x] **Toggle thème clair/sombre** (bouton footer sidebar, sidebar toujours sombre)
- [x] **Bouton unique ⚙ Pré-Traitement** — remplace les deux anciens boutons (✂ Crop + 🧼 prepUS) ; toujours `back_scan_conversion=True`, la checkbox contrôle l'affichage
- [x] **Badge de mode** sur l'en-tête de la carte (`ORIGINAL` / `BACKSCAN 512×512` / `CROP + MASQUE`)
- [x] **En-têtes de section** avec barre d'accent bleue gauche (style MEDomics) et texte en gras
- [x] **Résultats colorés dynamiquement** — vert risque faible, rouge risque élevé, orange/vert lésions
- [x] **Ombre portée simulée** sur la carte visionneuse DICOM + bordure subtile
- [x] **Indicateur d'état** du pré-traitement (en cours / terminé / erreur) sous le bouton
- [x] **Compteur de frames** navigation en gros caractères blancs
- [x] **Checkbox renommée** `Afficher résultat pré-traitement` (plus claire qu'`image rognée`)
- [x] **Sidebar scrollable** — Canvas + Scrollbar, affichage correct même en petite fenêtre

---

## 🚧 Tâches en Cours

### 🐍 Backend Python
- [ ] **Tests du pipeline bout en bout** — Valider `run_pipeline()` avec un fichier `.dcm` réel sur données hépatiques

### 🖼 Prototype Tkinter
- [ ] **Validation flux complet** — Charger un DICOM → prepUS crop+backscan → inférence IA (stub) → affichage résultats
- [ ] **Recueil de retours utilisateur** — Identifier les ajustements UX avant portage en React

---

## 📅 Roadmap — Prochaines Étapes

### 🔬 Phase 1 : Validation Backend (Court terme)

- [ ] **Intégration des poids des modèles IA**
  - Placer `starhe_risk_c3d.pth` et `starhe_detect_dino_detr.pth` dans `pythonCode/modules/starhe_plugin/models/`
  - Valider l'inférence C3D et DINO-DETR sur des données réelles prepUS-traitées
  - 📝 *Démarche : utiliser `torch.load()` avec `map_location='cpu'` pour les environnements sans GPU*

- [ ] **Écriture des tests unitaires**
  - Tester `reader.py` : chargement, nombre de frames, shape des arrays
  - Tester `anonymizer.py` : vérifier que les 15 tags sont bien effacés/hachés
  - Tester `prepus_bridge.py` : valider le crop + backscan sur un DICOM de référence
  - 📝 *Démarche : créer `pythonCode/modules/starhe_plugin/tests/` avec `pytest`*

### 🔀 Phase 2 : Intégration Go Server (Moyen terme)

- [ ] **Création des routes REST dans `go_server`**
  - Créer `go_server/blueprints/starhe.go` avec les endpoints :
    - `POST /starhe/analyze` — Lancer `pipeline.py` sur un fichier DICOM
    - `GET  /starhe/results` — Lister les analyses MongoDB
    - `GET  /starhe/results/:id` — Récupérer une analyse par ID
    - `DELETE /starhe/results/:id` — Supprimer une analyse
  - 📝 *Démarche : utiliser `os/exec` en Go pour lancer Python en subprocess, streamer stdout JSON via WebSocket ou SSE vers le frontend*

- [ ] **Gestionnaire de progression en temps réel**
  - Câbler les événements `go_progress()` de Python vers le frontend via Server-Sent Events (SSE)

- [ ] **Gestion des erreurs et timeouts**
  - Implémenter un timeout configurable pour l'inférence IA
  - Retourner des codes d'erreur HTTP sémantiques (400, 422, 500) avec messages JSON structurés

### ⚛️ Phase 3 : Portage UI React (Long terme)

- [ ] **Portage de l'interface Tkinter vers React/JSX**
  - Composant `<DicomLoader />` — Upload et validation d'un fichier `.dcm`
  - Composant `<FrameViewer />` — Visualisation des frames avec navigation, toggle crop/backscan
  - Composant `<AnonymizationPanel />` — Sélection du mode (hash / remove) et confirmation
  - Composant `<InferenceResults />` — Score STARHE-RISK et bounding boxes DINO-DETR
  - Composant `<AnalysisConsole />` — Logs en temps réel (équivalent console Tkinter)
  - 📝 *Démarche : s'inspirer du style MEDomics v1.8.0 déjà identifié dans le prototype Tkinter*

- [ ] **Intégration dans le système de navigation MEDomics**
  - Enregistrer le plug-in dans le menu latéral de MEDomics
  - Respecter le système de routing Next.js existant

### 🧪 Phase 4 : Tests & Déploiement (Long terme)

- [ ] **Tests d'intégration bout en bout**
  - Pipeline complet : frontend React → Go Server → Python → MongoDB → retour résultats
  - ⚠️ *Attention : utiliser uniquement des DICOMs anonymisés ou synthétiques, jamais de données patient réelles en dev*

- [ ] **Documentation des routes API Go** — Swagger / OpenAPI

- [ ] **Packaging du plug-in**
  - Vérifier la compatibilité avec le système d'extensions de MEDomics
  - Documenter la procédure d'installation du plug-in

---

## 📝 Procédures Techniques Clés

### 🧹 Prétraitement prepUS (pipeline principal)
> `preprocess_with_prepus(frames, fps, thresh, back_scan_conversion, backscan_width, backscan_height)`  
> 1. Export numpy → MP4 temporaire (OpenCV)  
> 2. `removeLayoutFile(mp4, out_dir, ...)` — détection pixels statiques + masquage + crop  
> 3. Lecture `backscan_video.mp4` et/ou `video.mp4` depuis `out_dir`  
> 4. Toujours appelé avec `back_scan_conversion=True` → les deux sorties sont disponibles en une passe  
> 5. Retourne `(backscan_array, crop_only_array, info_dict)` — nettoyage du dossier temporaire  
> ⚠️ prepUS doit être installé avec `--no-deps` pour éviter les conflits OpenCV

### 🏥 Anonymisation DICOM
> Utiliser `pydicom` pour itérer sur les tags DICOM définis dans `config.DICOM_SENSITIVE_TAGS`.  
> Mode `hash` : remplacer la valeur par `sha256(valeur_originale)[:16]` pour conserver la traçabilité interne.  
> Mode `remove` : appeler `del ds[tag]` après vérification de présence.  
> Sauvegarder avec `ds.save_as(output_path)` — ne jamais écraser le fichier original.

### 🔀 Communication Go ↔ Python
> Lancer Python en subprocess depuis Go : `cmd := exec.Command("python", "-m", "starhe_plugin.pipeline", args...)`.  
> Chaque ligne stdout de Python est préfixée `GO_PRINT:` suivi d'un JSON.  
> Parser côté Go avec `bufio.Scanner` + `json.Unmarshal`.  
> Relayer vers le frontend via SSE ou WebSocket en temps réel.

### 🤖 Chargement des modèles IA
> Instancier le modèle une seule fois au démarrage du serveur (singleton) pour éviter les rechargements coûteux.  
> Utiliser `torch.load(path, map_location=torch.device('cpu'))` en l'absence de GPU.  
> Passer en mode évaluation : `model.eval()` + `torch.no_grad()` lors de l'inférence.

### 🗄 Stockage MongoDB
> Connexion via `pymongo.MongoClient(MONGO_URI)` avec gestion d'exception `ServerSelectionTimeoutError`.  
> Chaque résultat est un document JSON avec : `dicom_path`, `frame_count`, `roi`, `risk_score`, `detections[]`, `anonymization_mode`, `created_at` (ISO 8601).  
> Indexer sur `dicom_path` et `created_at` pour des requêtes performantes.

---

*🔖 Ce fichier est maintenu manuellement. Mettre à jour au fil des sprints.*
