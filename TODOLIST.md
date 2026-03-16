# 📋 TODOLIST — Plug-in STARHE / MEDomics
> Carnet de bord opérationnel du projet.  
> Dernière mise à jour : **16 mars 2026**

---

## ✅ Tâches Accomplies

### 🍴 Mise en place du projet
- [x] **Fork du dépôt MEDomics** — Dépôt principal forké, branche de développement `feature/starhe-plugin` créée
- [x] **Analyse de l'architecture MEDomics** — Étude du stack (Electron / React / Go / Python / MongoDB), compréhension du système de communication Go ↔ Python via stdout JSON, repérage des points d'intégration (`go_server`, `renderer/`)
- [x] **Résolution des problèmes d'accès** — Contournement des blocages antivirus sur le disque `F:` (exclusions Windows Defender), résolution des conflits de `PATH` pour Python et Go sous Windows

### 🏗 Architecture du plug-in Python
- [x] **Définition de la structure de répertoires** — Création de `pythonCode/modules/starhe_plugin/` avec les sous-modules `ai/`, `db/`, `dicom/`, `ui/`, `utils/`
- [x] **`config.py`** — Centralisation de toutes les constantes (chemins, seuils, tags DICOM, paramètres MongoDB)
- [x] **`__init__.py` racine** — Hooks de cycle de vie `on_load()` / `on_unload()` conformes à la philosophie MEDomics
- [x] **`requirements.txt`** — Dépendances Python figées (`pydicom`, `opencv-python-headless`, `torch`, `pymongo`, `Pillow`, `numpy`)

### 🏥 Module DICOM (`dicom/`)
- [x] **`reader.py`** — Lecture `.dcm`, extraction frames mono/multi-frames, normalisation `uint8`, détection ciné-clips
- [x] **`anonymizer.py`** — Anonymisation de 15 tags DICOM sensibles (modes `hash` SHA-256 et `remove`), fonctions `anonymize()` et `anonymize_file()`
- [x] **`crop.py`** — Détection ROI par seuillage + morphologie + analyse de contours (OpenCV), application cohérente sur toute la séquence

### 🤖 Module IA (`ai/`)
- [x] **`starhe_risk.py`** — Wrapper C3D : preprocessing `(16, 112, 112)`, inférence, retour score `[0–1]` + label risque
- [x] **`starhe_detect.py`** — Wrapper DINO-DETR : preprocessing `800×800`, inférence, retour bounding boxes filtrées par score de confiance

### 🗄 Module Base de données (`db/`)
- [x] **`mongo_client.py`** — CRUD MongoDB complet : `save_result`, `get_result`, `list_results`, `delete_result`

### 🔧 Module Utilitaires (`utils/`)
- [x] **`go_print.py`** — Protocole JSON stdout : `go_print()`, `go_progress()`, `go_result()`

### 🔀 Orchestration
- [x] **`pipeline.py`** — Orchestrateur principal : chaîne DICOM → frames → anonymisation → crop → STARHE-RISK → STARHE-DETECT → MongoDB

### 🖼 Prototype UI
- [x] **`ui/prototype_tkinter.py`** — Prototype Tkinter complet (thème sombre Catppuccin) : chargement DICOM, navigation frames, visualisation crop, anonymisation, inférence IA, console de logs

---

## 🚧 Tâches en Cours

### 🐍 Backend Python
- [ ] **Tests des modules DICOM** — Valider `reader.py`, `crop.py` et `anonymizer.py` avec de vrais fichiers `.dcm` (ciné-clips d'écho hépatique)
- [ ] **Fine-tuning de l'algorithme de crop** — Ajuster `CROP_BLACK_THRESHOLD` et `CROP_MIN_CONTENT_RATIO` selon les résultats sur données réelles

### 🖼 Prototype Tkinter
- [ ] **Validation du flux utilisateur complet** — Exécuter `prototype_tkinter.py` de bout en bout avec un fichier DICOM réel et vérifier chaque étape (chargement → crop → inférence → affichage résultats)
- [ ] **Recueil de retours utilisateur** — Identifier les ajustements UX avant portage en React

---

## 📅 Roadmap — Prochaines Étapes

### 🔬 Phase 1 : Validation Backend (Court terme)

- [ ] **Intégration des poids des modèles IA**
  - Placer `starhe_risk_c3d.pth` et `starhe_detect_dino_detr.pth` dans `pythonCode/modules/starhe_plugin/models/`
  - Valider l'inférence C3D et DINO-DETR sur des séquences de test
  - 📝 *Démarche : utiliser `torch.load()` avec `map_location='cpu'` pour les environnements sans GPU*

- [ ] **Tests de bout en bout avec fichiers DICOM réels**
  - Assembler un jeu de données de test (ciné-clips `.dcm` d'échographies hépatiques)
  - Exécuter `pipeline.run_pipeline()` sur chaque fichier, vérifier les résultats en base MongoDB
  - 📝 *Démarche : utiliser `pytest` + fixtures de fichiers DICOM anonymisés synthétiques pour les tests unitaires*

- [ ] **Écriture des tests unitaires**
  - Tester `reader.py` : chargement, nombre de frames, shape des arrays
  - Tester `anonymizer.py` : vérifier que les 15 tags sont bien effacés/hachés
  - Tester `crop.py` : valider que le ROI détecté est non-nul et contient la zone utile
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
  - 📝 *Démarche : parser chaque ligne stdout préfixée `GO_PRINT:` côté Go et la relayer au client connecté*

- [ ] **Gestion des erreurs et timeouts**
  - Implémenter un timeout configurable pour l'inférence IA
  - Retourner des codes d'erreur HTTP sémantiques (400, 422, 500) avec messages JSON structurés

### ⚛️ Phase 3 : Portage UI React (Long terme)

- [ ] **Portage de l'interface Tkinter vers React/JSX**
  - Composant `<DicomLoader />` — Upload et validation d'un fichier `.dcm`
  - Composant `<FrameViewer />` — Visualisation des frames avec navigation et toggle crop
  - Composant `<AnonymizationPanel />` — Sélection du mode (hash / remove) et confirmation
  - Composant `<InferenceResults />` — Affichage du score STARHE-RISK et des bounding boxes DINO-DETR
  - Composant `<AnalysisConsole />` — Logs en temps réel (équivalent console Tkinter)
  - 📝 *Démarche : s'inspirer du style et des patterns des composants existants dans `renderer/src/` de MEDomics*

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

### 🏥 Anonymisation DICOM
> Utiliser `pydicom` pour itérer sur les tags DICOM définis dans `config.DICOM_SENSITIVE_TAGS`.  
> Mode `hash` : remplacer la valeur par `sha256(valeur_originale)[:16]` pour conserver la traçabilité interne.  
> Mode `remove` : appeler `del ds[tag]` après vérification de présence.  
> Sauvegarder avec `ds.save_as(output_path)` — ne jamais écraser le fichier original.

### ✂️ Crop automatique (ROI)
> Convertir la frame en niveaux de gris (`cv2.cvtColor`).  
> Appliquer un seuillage binaire (`cv2.threshold`, seuil = `CROP_BLACK_THRESHOLD`).  
> Utiliser `cv2.morphologyEx` (fermeture morphologique) pour combler les trous.  
> Trouver le plus grand contour avec `cv2.findContours` → ce contour est la zone utile.  
> Extraire le bounding rect (`cv2.boundingRect`) et l'appliquer sur toutes les frames.

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
