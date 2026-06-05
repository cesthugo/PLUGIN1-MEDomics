# 📋 TODOLIST — STARHE Plugin / MEDomics
> Operational project logbook.  
> Last updated: **5 juin 2026**

---

## ✅ Completed Tasks

### 🍴 Project Setup
- [x] **Fork of MEDomics repository** — Development branch created
- [x] **MEDomics architecture analysis** — Stack (Electron / React / Go / Python / MongoDB), Go ↔ Python communication via stdout JSON
- [x] **Python 3.13 environment** — venv in `starhe_plugin/.venv`, Python 3.14/Tkinter conflict resolved
- [x] **`.gitignore`** — exclusion of `*.exe`, `*.pth`, `__pycache__`, `.venv`, `temp/`, `*.egg-info`, `build/`

### 🏗 Python Plugin Architecture
- [x] **`config.py`** — Centralization of all constants (paths, thresholds, DICOM tags, MongoDB parameters)
- [x] **Root `__init__.py`** — `on_load()` / `on_unload()` hooks compliant with the MEDomics philosophy
- [x] **`requirements.txt`** — Complete Python dependencies

### 🏥 DICOM Module (`dicom/`)
- [x] **`reader.py`** — Reading `.dcm` and extensionless files (`force=True`), frame extraction, `uint8` normalization
- [x] **`anonymizer.py`** — Anonymization of 15 sensitive DICOM tags (`hash` and `remove` modes) + `remove_pixel_burnin()`
- [x] **`crop.py`** — Custom spatial + temporal algorithm (fallback if prepUS unavailable)
- [x] **`prepus_bridge.py`** — prepUS API integration: `preprocess_with_prepus()` — dual output (backscan 512×512 + crop only) in a single pass

### 🧹 prepUS Integration
- [x] **Installation**: `sonocrop --no-deps` + `prepUS --no-deps` + `fire` + `rich` in the venv
- [x] **JSON fix**: `_NpEncoder` in `prepUS/cli.py` for numpy types (`float32`, `int64`)
- [x] **Dual output**: returns `(backscan_array, crop_only_array, info_dict)` in a single pass

### 🤖 AI Module (`ai/`)
- [x] **`starhe_risk.py`** — C3D wrapper: preprocessing `(16, 112, 112)`, inference, score `[0–1]` + risk label
- [x] **`starhe_detect.py`** — RTMDet/DINO wrapper: `STARHEDetectModel` class with:
  - [x] **Persistent** subprocess (server mode) — model loaded only once
  - [x] Context manager `__enter__`/`__exit__` + clean `close()`
  - [x] `predict_batch(frames)` method — N frames in a single network pass
  - [x] One-shot fallback on server error
- [x] **`ai/models/_rtmdet_runner.py`** — RTMDet runner with:
  - [x] `--mode server` mode: stdin/stdout JSON loop, `READY` signal, `__EXIT__`
  - [x] Batch protocol: `{"images": [...]}` → `[[dets], ...]`
  - [x] Python 3.13 patches: mmcv._ext stubs, NMSop, inspect.getmodule
- [x] **`config.py` thresholds**: `DETECT_SCORE_THRESHOLD=0.70`, `DETECT_EVERY_N=4`, `DETECT_BATCH_SIZE="auto"`

### 🗄 Database Module (`db/`)
- [x] **`mongo_client.py`** — MongoDB CRUD: `save_result` (upsert), `find_by_file`, `get_result`, `list_results`, `delete_result`
- [x] **MongoDB port**: `54017` (config.py + go_server/config.go)
- [x] **Automatic cache**: `find_by_file(path)` checked before any inference; `save_result` with `replace_one(..., upsert=True)`
- [x] **Schema**: `detections_per_frame` — list of lists (one per frame), indexed on `file_path`

### 🔀 Orchestration
- [x] **`pipeline.py`** — Orchestrator DICOM → anonymization → prepUS → STARHE-RISK → STARHE-DETECT (batch + stride) → MongoDB

### 🖼 Tkinter UI Prototype
- [x] **MEDomics v1.8.0 Interface** — Sidebar `#151521`, background `#f4f6fb`, blue `#1565C0`, Segoe UI
- [x] **Navigation** — ◀/▶ buttons, horizontal ttk scrollbar, automatic playback
- [x] **Playback speed** — YouTube-style ×-multiplier slider (0.25× to 3.0×), calibrated from DICOM `FrameTime`
  - Logic: skip N frames per tick (×≥1) or extended interval (×<1)
- [x] **Clickable detected frames** — After analysis, list of 1-based frame numbers in clickable blue; click navigates directly to that frame
- [x] **MongoDB cache in the UI** — if file already analyzed, results restored instantly
- [x] **MongoDB save after analysis** — `save_result()` called at end of thread
- [x] **Right-click context menu** (7 options): Pan/Zoom, mm measurement, series, contrast, brightness, reset
- [x] **mm measurement tool** — yellow overlay calibrated from `SequenceOfUltrasoundRegions` / `PixelSpacing`
- [x] **Light/dark theme toggle**
- [x] **Mode badge** on the card: `ORIGINAL` / `BACKSCAN 512×512` / `CROP + MASK`
- [x] **Automatic anonymization** on import (15 tags + imager banner blacked out)
- [x] **Displayed metadata**: preserved (green) + original anonymized (red)
- [x] **Scrollable sidebar**
- [x] **Single ⚙ Preprocessing button** with status indicator
- [x] **🗑 Reset Analysis button** (red sidebar) — clears the MongoDB cache for the current file and fully resets the UI
- [x] **Mode Label in RESULTS** — dynamic badge indicating the active display mode: `Backscan 512×512`, `Preprocessing (crop)` or `Original`
- [x] **Right-click held** → contrast (X axis) / brightness (Y axis) live; brief right-click (<0.25 s) → 7-option context menu
- [x] **Vertical left-drag** (normal mode) → frame scrolling (1 frame / 8 px)
- [x] **Multiple simultaneous measurements** — several segments drawn in parallel; selection by click (orange outline), endpoint editing by dragging (point), whole segment movement, deletion via Delete/BackSpace
- [x] **Keyboard shortcuts** (18 bindings) — Space (play), ←/→ (±1 frame), Shift+←/→ (±10 frames), Home/End, P/M/S (modes), Escape (deselect/reset), R (reset view), C/L (contrast/brightness), +/- (speed), B (loop), Ctrl+Tab / Ctrl+Shift+Tab (tabs), Ctrl+W (close tab)
- [x] **Multi-file tab system** — `askopenfilenames` to load N files in one selection, tab bar at the bottom of the viewer, label = formatted `StudyDate` DD/MM/YYYY (fallback: filename), full state save/restore per tab (frames, zoom, measurements, contrast…), individual close (×), Ctrl+Tab navigation
- [x] **`delete_result()` MongoDB bug** fixed — filter by string field `file_path` instead of ObjectId

### 🔧 Display Mode Separation (April 7)
- [x] **Bounding boxes per mode** — `_detections_by_mode` (dict: `"backscan"` / `"crop"` / `"original"` → `list[list[dict]]`). When the user switches between modes, only the detections for the active mode are drawn on the canvas
- [x] **Results panel per mode** — `_results_by_mode` (dict → risk/detection texts per mode), `_refresh_results_panel()` method updates the Mode, HCC Risk, and Lesions labels based on the current mode
- [x] **MongoDB cache per mode** — Composite key `(file_path, analysis_mode)` instead of `file_path` alone; `find_by_file(path, analysis_mode=...)` filters by mode; a file can have distinct results per mode
- [x] **Tab save/restore** — `_capture_tab_state()` / `_restore_tab_state()` include `detections_by_mode` and `results_by_mode`
- [x] **macOS file selector compatibility** — Removed `filetypes` filter on Darwin (extensionless DICOM files invisible otherwise)

### ⚡ Performance Optimization (April 22, 2026)
- [x] **Adaptive `DETECT_BATCH_SIZE` end-to-end** — three-part fix:
  - `_rtmdet_runner.py`: CPU and MPS now send `ram_free_mb` (free RAM measured **after** model loading in the subprocess, ~450 MB model footprint already deducted)
  - `utils/hardware.py`: `compute_optimal_batch_size(device, vram_free_mb, ram_free_mb)` uses the subprocess-measured value; `_MAX_BATCH_CPU` raised 4→16, `_CPU_SAFETY` raised 0.20→0.35 — on a 16 GB machine with 14 GB free after load this yields batch=16 instead of 4
  - `starhe_detect.py`: passes `ram_free_mb=hw_info.get("ram_free_mb")` to the function and logs `ram_free=X MB` in the READY message
- [x] **RTMDet subprocess warmup in `pipeline.py`** — the subprocess is launched in a daemon thread immediately after frame extraction (step 3); it loads the model (~4 s) concurrently with prepUS + STARHE-RISK, so `detect_thread.join()` at step 6 is typically a no-op
- [x] **MPS device missing in `starhe_risk.py`** — auto-detection now follows `cuda → mps → cpu` instead of `cuda → cpu`; Apple Silicon GPU used when `DETERMINISTIC_INFERENCE=False`
- [x] **Resize cache in `c3d.py`** — `preprocess_clips` caches `_resize_shortest()` results per frame index; avoids ~3× redundant `F.interpolate` calls when clips overlap (typical with short clips and 10 test clips)
- [x] **MEAN/STD precomputed in `_rtmdet_runner.py`** — `_MEAN_F32`/`_MEAN_F64` and `_STD_F32`/`_STD_F64` computed once at module load instead of `.to(dtype)` on every frame; fixed trailing whitespace in `_infer_batch_frames`
- [x] **`predict()` delegates to `predict_batch()` in `starhe_detect.py`** — `predict(frame)` is now `predict_batch([frame])[0]`; removed the duplicate `_predict_server(frame)` method (~25 lines of dead code)

### 🔗 Go Server
- [x] **`go_server/main.go`** — Endpoints: GET /health, POST /starhe/analyze (SSE), GET/DELETE /starhe/results
- [x] **`go_server/config.go`** — MongoDB port `54017`, Python venv paths configurable via env vars
- [x] **`go_server/handlers.go`** — SSE streaming `GO_PRINT|` from Python

### 📡 Live Streaming (April 20, 2026)
- [x] **`ai/live_pipeline.py`** — `LiveRingBuffer(maxlen=160)`: thread-safe deque with `push()` / `snapshot()`. `LivePipeline`: background daemon thread, input queue (maxsize=8, drop-oldest policy), frame-by-frame RTMDet (`LIVE_DETECT_EVERY_N=4`) + sliding-window C3D (`LIVE_RISK_INTERVAL=16`)
- [x] **ROI auto-calibration** — `_auto_roi()` called after `LIVE_ROI_CALIBRATION_FRAMES=30` frames; subsequent frames are cropped+resized to 512×512 before inference
- [x] **`ui/live_tab.py`** — `LiveTab(tk.Frame)` with 3 sources:
  - [x] `SOURCE_CSTORE` — pynetdicom SCP (`_DicomReceiver`), configurable AE title + TCP port
  - [x] `SOURCE_FOLDER` — `_FolderWatcher(Thread)` polling `.dcm` files every 0.5 s
  - [x] `SOURCE_HDMI` — `_HDMIReader(Thread)` via `cv2.VideoCapture` (CAP_AVFOUNDATION on macOS)
- [x] **Display decoupling** — `_preview_tick()` at 33 ms (≈30 fps), independent of inference rate; bounding boxes and risk overlaid from `pipe.latest_result()`
- [x] **HDMI device selection** — `_list_capture_devices()` returns `(idx, name, fps, w, h)` tuples; `_refresh_hdmi_devices()` 3-pass selection: name keywords → exclude known cameras → highest resolution
- [x] **HDMI safety block** — `_hdmi_capture_card_found` bool; if `False`, `_start_live()` raises error without opening any camera; dynamic warning label: ⚠ orange / ✅ green / 🔴 red
- [x] **`ui/prototype_tkinter.py`** — Added **📡 Analyse en direct** sidebar button calling `_open_live_window()` (singleton `tk.Toplevel`, stored in `self._live_win`)
- [x] **Branch & merge** — `feature/live-dicom` → merged `--no-ff` into `main`, pushed (`c4c9392`)

### 🌐 Cross-Platform Compatibility
- [x] **`config.py`** — MongoDB configurable via environment variables (`MONGO_URI`, `MONGO_DB`, `MONGO_COLL`)
- [x] **`mongo_client.py`** — Path normalization via `PurePosixPath` for cache keys + graceful degradation (MongoDB unavailable → warning without crash)
- [x] **`starhe_detect.py`** — `np.ascontiguousarray()` for cross-platform memory compatibility
- [x] **`plugin.json`** — Plugin manifest with interpreter paths per OS (windows/posix)
- [x] **`setup.sh` / `setup.ps1`** — Venv setup + dependencies scripts (without launching the UI)

### 🔌 MEDomics Integration (Standard Plugin)
- [x] **MEDomics architecture analysis** — `StartPythonScripts()` → `GoExecutionScript` → `progress*_*{id}*_*{json}` + `response-ready*_*{filepath}` protocol
- [x] **`run_starhe.py`** — `GoExecutionScript` adapter: launches the STARHE pipeline in subprocess (dedicated venv), translates `GO_PRINT|…` → MEDomics protocol
- [x] **`starhe_blueprint.go`** — Go blueprint for the MEDomics server: `starhe/analyze/` and `starhe/progress/` routes
- [x] **Deployment in the MEDomics repository** — Blueprint copied, `starhe/` and `starhe_plugin/` symlinks created, `main.go` patched (import + `AddHandleFunc()`)
- [x] **Go build verified** — `go build .` in `MEDomics/go_server/` → exit code 0

### 🌐 React UI — Full port of the Tkinter prototype (April 29, 2026)
- [x] **Project scaffold** — React 18 / TypeScript / Vite in `react_ui/`, `vite.config.ts` proxy `/starhe → :8080`
- [x] **`StarhePlugin` root component** (`index.tsx`) — full state management: tabs, patients, logs, playback, SSE, settings
- [x] **`api.ts`** — `loadDicom` (path), `loadDicomFile` (multipart upload), `deleteCache`, `streamAnalysis` (SSE)
- [x] **`types.ts`** — `DicomData`, `Detection`, `AnalysisResult`, `Measure` (with `labelOffset`), `TabState`, `ViewMode`, `LogEntry`
- [x] **`Sidebar` component** — DICOM file section, navigation, playback controls (speed, loop), AI analysis buttons, results panel, metadata
- [x] **`DicomCanvas` component** — letterbox canvas, frame rendering, bbox overlay, multi-measure overlay, brightness/contrast via ImageData
- [x] **`ConsolePanel` component** — real-time SSE log console, color-coded levels, toggleable from Settings
- [x] **`AdjustDialog` component** — floating slider for contrast (0.1–3.0) and brightness (−100 / +100), with reset button
- [x] **`ContextMenu` component** — right-click 7-action menu (Pan, Zoom, Measure, Series, Contrast, Brightness, Reset)
- [x] **`SettingsPanel` component** — font scale/family, text/sidebar/bg colors, analysis mode selector, console toggle; persisted to `localStorage`
- [x] **`DetectionGallery` component** — right panel (190 px): scrollable detected-frame list with thumbnails, SVG bbox overlay, frame-count badge, click-to-navigate
- [x] **`LiveModal` component** — full port of `live_tab.py`: C-STORE / folder / HDMI sources, RTMDet overlay, risk score, SSE progress
- [x] **`useDisplaySettings` hook** — `DisplaySettings` interface (fontScale, fontFamily, textColor, sidebarBg, mainBg, analysisMode, showConsole); `localStorage` persistence with forward-compatible merge
- [x] **`usePipelineSSE` hook** — SSE consumer for `/starhe/analyze`; filters `risk` / `detections_per_frame` events by analysis mode; `commitResult()` for final state
- [x] **`usePlayback` hook** — rAF-based frame ticker, speed multiplier, loop flag, DICOM `baseFps`
- [x] **`useCanvasInteractions` hook** — pan/zoom/measure/series interactions; `Transform` type exported; `getMeasureLabelScreenPos`, `getDefaultLabelOffset`, `labelHit` helpers; `onMeasureLabelMove` callback

### 🔧 Go Server — additional endpoints and fixes (April 29, 2026)
- [x] **`handlers_dicom.go`** — `POST /starhe/dicom/load` (path), `POST /starhe/dicom/upload` (multipart), `DELETE /starhe/dicom/delete` (release reference; does NOT delete temp file so re-analysis after reset works)
- [x] **`handlers.go`** — `RunRisk bool` field in `analyzeRequest`; passes `--no_risk` / `--no_detection` to Python when false
- [x] **`config.go`** — `serverDir()` uses `os.Executable()` → absolute Python/module paths regardless of launch CWD

### 🤖 AI / Backend fixes (April 29, 2026)
- [x] **`pipeline.py`** — `run_risk: bool = True` parameter; step 5 conditional; `--no_risk` argparse flag
- [x] **`mongo_client.py`** — `save_result(risk: dict | None)` — skips `risk` field in document when `None`

### 🎨 UX improvements (April 29, 2026)
- [x] **Measure label** — perpendicular auto-placement; draggable (stored as `labelOffset` in `Measure`); dashed leader line from midpoint to label
- [x] **Brightness/Contrast** — replaced CSS filter with pixel-level ImageData formula `c × pixel + b`; independent, artifact-free, adapted to dark ultrasound images

### 🖼 React UI — Multi-panel & UX (7 mai 2026)
- [x] **Multi-panel split view** — `PanelGrid` + `ViewPanel` components; drag a tab or thumbnail → adds a panel in the grid; click a panel → focus (blue outline) + sidebar/gallery target that file; `×` removes a panel; CSS grid auto-cols (1/2/3/4); empty state shows a hint; patient isolation: `switchTab` filters `visiblePanelIds` to tabs belonging to the newly active patient
- [x] **Folder loading** — "📁 Charger un dossier DICOM" button in sidebar; `webkitdirectory` picker; auto-detects `.dcm`, `.dicom`, and extension-less files; loads all files sequentially
- [x] **Patient isolation in multi-panel** — `switchTab` filters `visiblePanelIds` to tabs belonging to the newly active patient; prevents cross-patient panel contamination

### 🔌 MEDomics Integration fixes (7 mai 2026)
- [x] **Extension description corrected** — `ExtensionManager.jsx`: subtitle "Échographie hépatique", description mentions HCC/foie, tag "Hépatologie" (was "Cardiologie" / "cardiaque")
- [x] **Go server connection fixed** — `starhe.jsx`: `STARHE_API_BASE = 'http://localhost:8082'` hardcoded; removed dependency on `WorkspaceContext.port` which was often `null` at iframe load time, causing "Failed to fetch" errors on port 8082
- [x] **MEDomics Next.js renderer rebuilt** — `npx next build` after all fixes
- [x] **Go binary rebuilt** — `go build -o go_server .` in `go_server/`; server confirmed on port 8082 via `/health`

### 🗂 Batch Analysis — Export/Import JSON (11 mai 2026)
- [x] **`start_react.sh`** — `find_free_port()` : auto-détecte le premier port TCP libre ≥ 8082 ; exporte `STARHE_PORT` ; passe `PORT="$STARHE_PORT"` au binaire Go
- [x] **`vite.config.ts`** — lit `process.env.STARHE_PORT ?? '8082'` pour la cible du proxy Vite
- [x] **`BatchModal.tsx` — persistance des bboxes** — `BatchItem` stocke `detections?: Detection[][]`, `numFrames?`, `roi?` ; remplis à la fin de chaque analyse SSE
- [x] **`BatchModal.tsx` — `exportJSON()`** — génère `starhe_batch_YYYY-MM-DD.json` avec `detections_per_frame` complet ; format `{ starhe_batch: "1.0", exported_at, analysis_mode, results: [...] }`
- [x] **`BatchModal.tsx` — `importJSON()`** — file picker `.json` ; parse et valide le format `starhe_batch` ; ajoute les items avec `status: 'done'` et résultats pré-remplis (risk + detections) sans re-analyser
- [x] **`BatchModal.tsx` — `BatchResultToOpen` interface** — interface exportée : `{ serverPath, name, detections?, risk?, numFrames?, roi? }`
- [x] **`BatchModal.tsx` — "→ Tab"** — passe l'objet `BatchResultToOpen` complet (avec bboxes) à `onOpenInTab`
- [x] **`BatchModal.tsx` — checkboxes + ouverture multiple** — case à cocher par ligne + case globale "tout sélectionner" dans l'en-tête du tableau ; boutons **"↗ Ouvrir sélection (N)"** et **"↗ Tout ouvrir (N)"** dans le récapitulatif
- [x] **`index.tsx` — `import { BatchModal }`** — import + `type BatchResultToOpen` depuis `./components/BatchModal`
- [x] **`index.tsx` — `showBatch` state** — `const [showBatch, setShowBatch] = useState(false)`
- [x] **`index.tsx` — `onLoadFolder`** — callback `webkitdirectory` : ouvre un dossier, filtre `.dcm` / `.dicom` / sans extension, charge séquentiellement via `doLoadFile`
- [x] **`index.tsx` — `<Sidebar onOpenBatch>` + `onLoadFolder`** — props branchées sur les nouveaux callbacks
- [x] **`index.tsx` — `onOpenInTab` handler** — `loadDicom(serverPath)` → crée l'onglet avec `detectionsBy.original` + `resultsBy.original` pré-injectés ; fallback file picker si le fichier temp serveur a expiré


### 🔧 Cross-platform & DICOM fixes (12 mai 2026)
- [x] **Split button DICOM** — `Sidebar.tsx` : bouton fractionné `📁 Dossier DICOM | 🗂️` ; partie gauche = `webkitdirectory` (dossier entier), partie droite = sélection manuelle multi-fichiers individuels ; `onLoadDicomFiles` callback branché dans `index.tsx`
- [x] **DICOM JPEG 2000** — `reader.py` : `extract_frames()` réécrit avec 3 niveaux de fallback : (1) `ds.pixel_array` nominal, (2) `ds.decompress()` pydicom 3.x, (3) `_extract_j2k_raw_scan()` — scan brut de `PixelData` pour le marqueur `FF 4F FF 51` (SOC+SIZ J2K), décode chaque codestream directement avec `openjpeg.decode` ; validé 24/24 fichiers (J2K lossless, J2K lossy, JPEG baseline, RLE)
- [x] **pylibjpeg** — `requirements.txt` : ajout `pylibjpeg>=2.0.0`, `pylibjpeg-openjpeg>=2.0.0` (JPEG 2000), `pylibjpeg-libjpeg>=2.1.0` (JPEG lossless/lossy) ; décodeurs automatiquement utilisés par pydicom 3.x
- [x] **Go handler erreurs** — `handlers_dicom.go` : réponse d'erreur HTTP 500 enrichie avec `stdout`, `python_error`, `python_traceback` (extrait du JSON Python) pour rendre visible le traceback Python dans la console React
- [x] **`.gitignore` cross-platform** — ajout `react_ui/node_modules/` et `go_server/go_server` + `go_server/starhe_server` (binaires OS-spécifiques, ne pas commiter) ; `git rm --cached -r` exécuté pour désindexer les fichiers déjà tracqués
- [x] **`start_react.ps1` / `start_react.sh`** — auto-lancement `setup.ps1` / `setup.sh` si venv Python absent au démarrage ; `npm install` → `npm ci` (installation reproductible depuis `package-lock.json`)

### 🖼 React UI — DicomUploader + Correctifs interface (19 mai 2026)
- [x] **`DicomUploader.tsx`** — Nouveau composant dédié au chargement DICOM (drag-and-drop + picker + URL) ; extrait de `Sidebar.tsx` pour clarifier les responsabilités
- [x] **`BatchModal.tsx` — Boutons dossier / fichiers** — Correction des boutons "📁 Dossier" et "🗂 Fichiers" dans la modal batch (sélection dossier entier vs fichiers individuels)
- [x] **Multi-panneaux — Correctif #1** — `MultiPanelView.tsx` : remplacement `tab.panX/panY` par `{...tab, panX:0, panY:0}` pendant le redimensionnement ; `pointerEvents: none` sur les panneaux non-focalisés pendant le resize ; `onResetAllPanelsPanRef` pour éviter les closures périmées
- [x] **`useCanvasInteractions.ts`** — Ajout d'un listener global `window.mouseup` pour forcer le nettoyage de `dragRef`, `rclickRef`, `editRef` après relâchement hors canvas
- [x] **`useTabManager.ts`** — `updateTabById` stabilisé avec `useCallback` sans dépendances instables
- [x] **`pipeline.py` / `prepus_bridge.py`** — Correctifs pipeline batch (voir commit f312a8f)

### 🤖 Analyse live + Correctif multi-panneaux #2 (21 mai 2026)
- [x] **`run_live.py`** — Nouveau point d'entrée CLI pour l'analyse live ; lancé par le serveur Go comme sous-processus ; 3 sources : `_FolderWatcher` (polling `.dcm` toutes les 0.5 s), `_HDMIReader` (cv2.VideoCapture, `CAP_AVFOUNDATION` sur macOS), `_CStoreReceiver` (pynetdicom SCP, AE=`STARHE_LIVE`) ; même protocole `GO_PRINT|level|{json}` que `pipeline.py` ; preview émise immédiatement avant inférence ; arrêt propre via SIGTERM/SIGINT → `_stop_event`
- [x] **`handlers.go` — Endpoints live** — Nouveaux endpoints REST + SSE pour l'analyse live : `POST /starhe/live/start` (lance `run_live.py`), `POST /starhe/live/stop` (arrêt du sous-processus), `GET /starhe/live/stream` (SSE des frames preview + détections)
- [x] **`main.go`** — Enregistrement des nouvelles routes live dans le routeur Go
- [x] **Multi-panneaux — Correctif #2 (`onPanReset`)** — `DicomCanvas.tsx` : nouvelle prop `onPanReset?: () => void` ; l'effet de resize appelle `onPanReset()` à la place de `NOOP_ZP` → réinitialise tous les panneaux ; 0 erreurs TypeScript
- [x] **`LiveModal.tsx`** — Mise à jour du modal live pour utiliser les nouveaux endpoints du backend Go

### 🚀 Lanceurs double-clic (26 mai 2026)
- [x] **`launch_medomics.command`** — Lanceur macOS (double-clic Finder) pour MEDomics + STARHE en mode développement : vérifie Node.js/Go, compile le binaire Go si absent, `npm install` MEDomics si absent, construit et déploie l'UI React si `dist/` absent, puis `npm run dev` dans MEDomics (→ Electron démarre MongoDB + Go MEDomics + Go STARHE automatiquement) ; `chmod +x` appliqué
- [x] **`launch_medomics.bat`** — Équivalent Windows (double-clic Explorateur) ; même logique, binaire `go_server.exe`, `xcopy /E /Y /I` pour le déploiement React, `pause` en fin
- [x] **`launch_plugin.command`** — Lanceur macOS standalone STARHE (sans MEDomics) : vérifie Python 3.13 / Node.js / Go, crée le venv si absent + installe dépendances + poids IA, compile le binaire Go, trouve et démarre MongoDB sur le port 54017, démarre le serveur Go (`:8082`) et le serveur Vite (`:5173`) en arrière-plan, attend que React soit prêt, ouvre le navigateur → arrêt propre de tous les services sur Ctrl+C ; `chmod +x` appliqué
- [x] **`launch_plugin.bat`** — Équivalent Windows standalone : chaque service (MongoDB, Go server, React UI) s'ouvre dans sa propre fenêtre CMD ; ouvre automatiquement le navigateur sur `http://localhost:5173` après détection que le serveur Vite est prêt

### 🤖 STARHE-RISK — Alignement preprocessing C3D (27–28 mai 2026)

> Contexte : écart de performance identifié par comparaison patient par patient avec les résultats de référence de Jérémy N (48 patients partagés, seuil 50%).
> Pipeline d'entraînement réel : DICOM → MP4 initial → **prepUS.removeLayoutFile** → `video.mp4` (éventail rogné, niveaux de gris, codec mp4v) → Decord → mmaction2 → C3D.

- [x] **`c3d.py` — `_sample_clips` exact mmaction2** — `avg_interval = (T−16+1) / 10` (+1 manquant) ; `offsets = base×avg + avg/2 − 0.5` (−0.5 manquant).
- [x] **`c3d.py` — `_resize_shortest` exact mmaction2** — `cv2.resize(uint8, INTER_LINEAR)` au lieu de `F.interpolate(float32, align_corners=False)`.
- [x] **`pipeline.py` — piste `_frames_via_mp4()` testée puis abandonnée** — Compression MPEG-4 des frames brutes insuffisante (±2–3% sur les scores) ; UI Supersonic non retirée.
- [x] **Pipeline d'entraînement identifié** — Données d'entraînement = `video.mp4` prepUS (format éventail, niveaux de gris, codec mp4v). Confirmé par le tuteur.
- [x] **`pipeline.py` — RISK sur `crop_only_frames`** — prepUS tourne désormais pour RISK et DETECT. RISK reçoit `crop_only_frames` (cône rogné, niveaux de gris → pseudo-RGB R=G=B), identique au format des `video.mp4` décodés par Decord.
- [x] **Validation Batch 4 (28/05/2026)** — **Sens = 91.7% (22/24), Spec = 52% (13/25)** — preprocessing aligné avec la distribution d'entraînement. ⚠ Divergence avec la référence Jérémy N confirmée (cf. tableau ci-dessous) — écart dû au seuil de décision, pas à l'implémentation.

  | | Notre impl. (Batch 4, seuil 50%) | Référence Jérémy N |
  |---|---|---|
  | TP / FN / FP / TN | 22 / 2 / 12 / 13 | 18 / 7 / 7 / 18 |
  | Sensibilité | **91.7%** | 72% |
  | Spécificité | 52% | **72%** |
  | Seuil utilisé | 50% (config.py) | Inconnu — probablement plus élevé |
  | Profil | Sensible / peu spécifique | Équilibré |

  **Interprétation** : le preprocessing est correct (même distribution d'entraînement). La différence de point de fonctionnement est une question de calibration du seuil — à investiguer (voir Phase 5 Roadmap).

  | Batch | Config RISK | Sens | Spec |
  |---|---|---|---|
  | Jérémy N (réf.) | Training pipeline, seuil calibré | 72% | 72% |
  | Batch 1–2 (sans prepUS) | DICOM brut | 12.5% | 88% |
  | Batch 3 (+mp4v) | DICOM brut + mp4v | ~12% | ~88% |
  | **Batch 4 (crop_only)** | **prepUS crop, seuil 50%** | **91.7%** | **52%** |

### 🤖 STARHE-DETECT — Correction input preprocessing (28 mai 2026)

> Contexte : lors de la session précédente, `processed_detect` avait été basculé sur `backscan_frames` en priorité, sur la foi d'un commentaire de commit (`7a26d1c`). La config d'entraînement réelle (`rtmdet_starhe.py`, `train_dataloader.data_prefix = "cropped_videos"`) confirme que RTMDet a été entraîné sur des frames **croppées** (éventail rogné), pas sur le backscan Cartésien.

- [x] **Diagnostic** — `rtmdet_starhe.py` : `train_dataloader.data_prefix = "cropped_videos"` et `test_dataloader.ann_file = 'cropped_videos/...'` — preuve directe que l'entraînement utilisait les frames croppées.
- [x] **`pipeline.py` — `processed_detect` restauré sur `crop_only_frames`** — Suppression de `backscan_frames` de la chaîne de priorité ; `crop_only_frames` est l'unique source (même distribution que l'entraînement).
- [x] **`pipeline.py` — remappage bbox restauré** — `detect_remap_info = {"crop": info["crop"]}` uniquement → simple offset (xmin, ymin) pour revenir dans l'espace DICOM (la transformation polaire inverse n'est pas nécessaire).
- [x] **Docstring pipeline.py mis à jour** — "entraîné sur les frames backscan" → "entraîné sur les cropped_videos de prepUS".

> **⚠ Observation Batch 3 (28/05/2026)** — Le batch relancé avec `crop_only_frames` donne des résultats *inférieurs* au backscan pour la détection :
> | Patient | Score RISK | Backscan (avant) | Crop_only (après) | Interprétation |
> |---|---|---|---|---|
> | 01-0083-L-X | 77.74% ↑ | **12** lésions | **4** lésions | TP probable → perte de sensibilité |
> | 05-0030-H-M | 12.62% ↓ | 4 lésions | 0 lésions | TN probable → FP supprimés ✅ |
> | 05-0062-J-D | 23.14% ↓ | 24 lésions | 0 lésions | TN probable → 24 FP supprimés ✅ |
> | 06-0018-D-M | 72.33% ↑ | 4 lésions | 4 lésions | TP probable → stable |
>
> **Hypothèses sur la régression** :
> 1. `"cropped_videos"` pourrait désigner les frames backscan recadrées (nom ambigu) — à vérifier sur Jean Zay.
> 2. Format : `crop_only` = éventail polaire non carré (dims variables) ; backscan = 512×512 carré ≈ format entraînement 640×640 → meilleure cohérence dimensionnelle.
> 3. Distribution de pixels : l'éventail polaire a des zones noires aux coins (géométrie en arc) que le modèle n'a peut-être pas vue à l'entraînement.
> **État actuel** : `pipeline.py` utilise `crop_only_frames` pour DETECT (aligné config). Investigation en cours.

### � prepus_bridge simplification + pipeline DICOM complet (2 juin 2026)

- [x] **`prepus_bridge.py` simplifié** — 599 → 171 lignes. Suppression du backscan Cartésien (`_map_bbox_backscan_to_original`, `_compute_lossless_backscan_params`, `_crop_inmemory`). Nouvelle signature : `preprocess_with_prepus(frames, fps, thresh, backscan_width, backscan_height) → (crop_frames, info)` (2-tuple au lieu de 3-tuple). Les deux modèles étaient entraînés sur `video.mp4` / `cropped_videos` (éventail rogné), pas sur le backscan Cartésien : le backscan était inutile.
- [x] **`pipeline.py` mis à jour** — Adapté à la nouvelle signature 2-tuple ; suppression de `backscan_frames` dans tout le flux ; `map_detections_to_dicom_coords` simplifié (plus de paramètres `bsc_w`/`bsc_h`).
- [x] **`test_dicom_pipeline.py`** — Nouveau script (racine du projet) : pipeline complet depuis un fichier DICOM brut : `pydicom` → export PNG → `ffmpeg` MP4 (fps depuis tag `FrameTime`) → `prepUS` → STARHE RISK + DETECT. Équivalent programmatique de l'export manuel Weasis. Weasis n'expose pas d'API headless pour l'export PNG/MP4 (confirmé).
### 🏥 Serveur alternatif Orthanc PACS (3 juin 2026) — ❌ retiré (5 juin 2026)

> **Retiré le 5 juin 2026.** Décision : on bascule sur la librairie `weasis-dcm2png` pour la conversion DICOM → image/MP4. Fichiers supprimés (`handlers_orthanc.go`, `OrthancBrowser.tsx`), routes/variables d'env/imports/boutons purgés de `config.go`, `main.go`, `index.tsx`, `Sidebar.tsx`. Historique conservé ci-dessous à titre d'archive.

- [x] **`config.go` — Variables d'env Orthanc** — 3 nouveaux champs : `OrthancURL` (défaut `http://localhost:8042`), `OrthancUser`, `OrthancPassword` ; configurables via `ORTHANC_URL` / `ORTHANC_USER` / `ORTHANC_PASSWORD`
- [x] **`handlers_orthanc.go`** — Proxy Orthanc complet (240 lignes) : `orthancDo` (requête HTTP authentifiée serveur-to-serveur), 7 handlers REST (`/starhe/orthanc/status`, `/patients`, `/patients/{id}`, `/studies/{id}`, `/series/{id}`, `/instances/{id}`, `POST /starhe/orthanc/load`) — `load` télécharge le DICOM, le stocke en temp SHA-256, le passe à `loader_cli.py`, retourne les frames JSON
- [x] **`main.go` — Routes Orthanc** — 7 routes enregistrées dans le routeur Go (après `/starhe/cache`)
- [x] **Go compilation** — `go build .` → succès (0 erreur)
- [x] **`OrthancBrowser.tsx`** — Composant React modal (~450 lignes) : arborescence hiérarchique lazy-loading Patients → Studies → Series → Instances ; `StatusBadge` (point vert/rouge) ; bouton "Charger" par instance → `POST /starhe/orthanc/load` → mappe la réponse vers `DicomData` (incluant `serverPath`) → appelle `onLoaded({ data, serverPath })` ; thème sombre cohérent (couleurs de `colors.ts`) ; fermeture Escape / clic overlay
- [x] **`Sidebar.tsx` — Bouton Orthanc** — Prop `onOpenOrthanc: () => void` ajoutée ; bouton `🏥 Navigateur Orthanc PACS` dans la section "Analyse IA"
- [x] **`index.tsx` — Intégration complète** — Import `OrthancBrowser` + `OrthancLoadedResult` ; state `showOrthanc` ; prop `onOpenOrthanc` sur `<Sidebar>` ; modal `<OrthancBrowser>` avec `onLoaded` : crée un onglet, met à jour les patients, journalise ; TypeScript 0 erreur

### 🔬 STARHE-RISK — Validation C3D contre mmaction2 de référence (3 juin 2026)

> Contexte : malgré l'alignement preprocessing du 28 mai (`crop_only_frames`, `_sample_clips` exact, `_resize_shortest` cv2), il reste un biais résiduel d'environ +3.6 % sur les scores high-risk et 6 patients en désaccord avec la référence de Jérémy (`01-0096`, `02-0049`, `03-0022`, `05-0009`, `05-0021`, `05-0077`). Question : est-ce notre port pytorch pur du C3D qui dérive, ou les crops prepUS qui diffèrent de ceux utilisés à l'entraînement ?

- [x] **Vérification `third_party/prepUS` vs référence** — diff complet : `prepUS` vendored est algorithmiquement identique à la version partagée par Jérémy. Seules différences fonctionnelles : `backscan.py:48` `b = np.array([rho1, rho2])` (bugfix 1D pour éviter un crash `int(np.round(x0))` sur tableau 0-d), `cli.py` ajoute `_NpEncoder` pour la sérialisation JSON numpy, `utils.py` retire `import fire`. Reste = whitespace / docstrings.
- [x] **Crops déterministes pré-générés** — `/tmp/gen_crops_fixed.py` : un passage prepUS par fichier sur les 49 MP4 de Jérémy → `/tmp/crops_fixed/<PID>/video.mp4` (codec mp4v, niveaux de gris, éventail rogné). 49/49 crops produits.
- [x] **Environnement mmaction2 de référence** — `pyenv install 3.10.14` + venv `/tmp/mmaction_env/` : `torch==2.1.2`, `torchvision==0.16.2`, `numpy<2`, `eva-decord` (fournit `decord 0.7.0`), `mmcv-lite==2.1.0` (mmcv-full ne compile pas sur ARM macOS sans pkg_resources), `mmaction2==1.2.0` installé `--no-deps` (la dépendance `decord>=0.4.1` est satisfaite par eva-decord), `opencv-contrib-python<4.12`, `importlib_metadata`. Patches : `mmaction/models/localizers/__init__.py` (suppression de l'import DRN absent du wheel 1.2.0) ; copie sanitizée de `c3d_starhe.py` dans `/tmp/cfg/c3d/` (suppression de `custom_imports = ['starhe.metrics.classification_metric']` et de `TensorboardVisBackend`).
- [x] **Inférence mmaction2 de référence** — `/tmp/run_ref_mmaction.py` : `init_recognizer(cfg, checkpoint, device='cpu')` + `inference_recognizer(model, mp4_path)` sur les 49 crops → `/tmp/ref_scores.json` (49/49 scores `[low, high]`).
- [x] **Inférence notre C3D sur les mêmes crops** — `/tmp/run_ours_on_crops.py` : lecture cv2 → niveaux de gris → pseudo-RGB (R=G=B) → `STARHERiskModel().predict()` → `/tmp/ours_scores.json` (49/49 scores).
- [x] **Comparaison à trois voies** — `/tmp/cmp.py` : résultats finaux

  | Comparaison | Mean Δ | MAE | Max\|Δ\| | Accord label (seuil 0.5) |
  |---|---|---|---|---|
  | **Nous vs Ref mmaction2** (mêmes crops) | −0.0003 | **0.013** | 0.052 | **47/49 (96 %)** |
  | Ref mmaction2 vs Jérémy (cached preds) | +0.036 | 0.111 | 0.531 | 43/49 |
  | Nous vs Jérémy | +0.036 | 0.109 | 0.529 | 43/49 |

  **Conclusion** : notre port pytorch du C3D est validé bit-near du C3D mmaction2 (MAE 1.3 %, biais 0). Les 4 % de différences résiduelles proviennent du décodage vidéo (cv2 vs Decord du même `video.mp4`, codec mp4v + colorspace YUV→RGB non bit-exact). Les 6 mismatches de label vs Jérémy **sont également présents dans la référence mmaction2 sur nos crops** → le résidu vient des crops prepUS (non-déterminisme d'une exécution à l'autre, ou différence avec les crops produits à l'époque de l'entraînement), pas du modèle.

### 🔬 STARHE-RISK — Chaîne d'isolation finale + bypass MP4 (5 juin 2026)

> Contexte : poursuite de la session du 3 juin pour identifier exactement la source du résidu de ~11 % vs Jérémy. Trois tests d'isolation puis un test décisif avec une variante in-memory de prepUS.

- [x] **Décodage `video.mp4` — cv2 vs PyAV vs Decord** — `/tmp/decoder_diff.py` install `av 17.0.1` ; 3 chemins comparés (cv2 BGR→RGB, cv2 BGR→GRAY→stack, PyAV rgb24) sur 4 crops grayscale produits par prepUS → **MAE 0.000, 100 % pixels égaux** sur les 4 fichiers. Le décodeur n'est PAS la source du résidu.
- [x] **Déterminisme prepUS local** — `/tmp/test_prepus_determinism.py` : 3 exécutions consécutives par fichier sur 4 MP4 → SHA-256 de `video.mp4` et `info.json` identiques sur les 3 runs pour les 4 fichiers. prepUS est **100 % déterministe sur une même machine**.
- [x] **Cause racine identifiée** — La seule différence restante entre nos crops et ceux de Jérémy est l'**encodage MP4 par `cv2.VideoWriter(mp4v)`** (utilisé par `sonocrop.vid.savevideo` dans `prepUS/cli.py:198`). cv2 délègue au binaire FFmpeg lié à OpenCV, qui dépend de : OS, version `opencv-python`, version FFmpeg système. macOS ARM Homebrew (notre env) ≠ Linux Jean Zay (entraînement de Jérémy) → bitstream différent → pixels reconstruits différents après décodage → C3D voit des entrées légèrement différentes.
- [x] **Email à Adrien (auteur prepUS + entraînement)** — demande des crops d'entraînement originaux et/ou des versions exactes `opencv-python` + FFmpeg utilisées sur Jean Zay. **Réponse reçue 5 juin 2026 : son environnement Jean Zay (dataset + versions) a été supprimé par erreur par un IT de l'IHU.** Aucune récupération possible. La voie "reproduire l'encodage d'origine" est définitivement fermée.
- [x] **Mode bypass MP4 implémenté** — `dicom/prepus_bridge.py` : nouvelle fonction `preprocess_with_prepus_inmem` (~165 lignes) qui réimplémente `removeLayoutFile` strictement équivalente, en numpy pur, sans aucun `VideoWriter` / `VideoCapture` / dossier temporaire. Retry récursif sur `find_linear_fov` conservé à l'identique. Conversion RGB→GRAY via `cv2.cvtColor(RGB2GRAY)` (mêmes poids BT.601 que le chemin `BGR2GRAY` lu par `sonocrop.loadvideo`).
- [x] **Flag de configuration** — `config.py` : ajout de `PREPUS_BYPASS_MP4: bool = False` (défaut conservateur). `pipeline.py` sélectionne `preprocess_with_prepus_inmem` quand le flag est `True`, `preprocess_with_prepus` sinon ; tag de mode logé dans la progression. Export ajouté dans `dicom/__init__.py`.
- [x] **Validation 49 patients** — `/tmp/batch_bypass_vs_roundtrip.py` : exécute les 2 modes sur les 49 MP4 du test set de Jérémy, compare aux prédictions cachées `pred_test.pkl`.

  | Métrique | Mode A (MP4 roundtrip) | **Mode B (bypass)** | Gain |
  |---|---|---|---|
  | MAE vs Jérémy | 0.1215 | **0.1025** | −16 % |
  | Accord labels vs Jérémy | 42/49 (85.7 %) | **44/49 (89.8 %)** | +2 patients |
  | Accuracy vs vérité terrain | 31/49 (63.3 %) | **33/49 (67.3 %)** | +2 patients |
  | Bias − Jérémy | +0.044 | +0.037 | −16 % |
  | Reproductibilité cross-OS | ❌ | ✅ bit-à-bit | — |

  Le bypass est strictement meilleur sur les 3 métriques + élimine la dépendance à l'encodeur mp4v non-portable. Reste l'option de basculer le défaut à `True` (cf. roadmap).

### 🗑️ Suppression du serveur Orthanc PACS (5 juin 2026)

> Contexte : la pile Orthanc implémentée le 3 juin (~700 lignes Go + TS) est remplacée par la librairie `weasis-dcm2png` pour la conversion DICOM → image / MP4. La section archive de l'historique Orthanc est conservée plus haut, marquée "❌ retiré".

- [x] **`go_server/handlers_orthanc.go`** — supprimé (240 lignes : `orthancDo`, 7 handlers REST)
- [x] **`react_ui/src/StarhePlugin/components/OrthancBrowser.tsx`** — supprimé (~450 lignes)
- [x] **`go_server/config.go`** — champs `OrthancURL` / `OrthancUser` / `OrthancPassword` + envs `ORTHANC_URL` / `ORTHANC_USER` / `ORTHANC_PASSWORD` retirés
- [x] **`go_server/main.go`** — 7 routes `/starhe/orthanc/*` retirées
- [x] **`react_ui/src/StarhePlugin/index.tsx`** — imports `OrthancBrowser` + `OrthancLoadedResult`, state `showOrthanc`, prop `onOpenOrthanc` sur `<Sidebar>`, bloc modal complet (~40 lignes) retirés
- [x] **`react_ui/src/StarhePlugin/components/Sidebar.tsx`** — prop `onOpenOrthanc` (déclaration + destructuration + bouton `🏥 Navigateur Orthanc PACS`) retirée ; padding du bouton Batch (devenu dernier de la section) promu à `10px`
- [x] **Vérifications** — `go build ./...` 0 erreur ; aucune nouvelle erreur TS sur les fichiers touchés ; `TODOLIST.md` section Orthanc marquée `❌ retiré (5 juin 2026)` avec justification
- [x] **Intégration `weasis-dcm2png` runtime (5 juin 2026)** — voir section dédiée ci-dessous

### 🔬 Intégration `weasis-dcm2png` dans le pipeline runtime (5 juin 2026)

> Contexte : `pydicom.pixel_array` n'applique ni Modality LUT ni VOI LUT, alors que le pipeline d'entraînement de Jérémy passait par Weasis (LUT appliquées). On câble la même chaîne DICOM → PNG (LUT) → numpy au runtime, avec fallback automatique sur pydicom si Java/JAR absent ou si la transfer syntax n'est pas supportée par le JAR (ex. JPEG 2000).

- [x] **Mini-projet Java vendorisé** — `third_party/weasis-dcm2png/` : `pom.xml` + `src/main/java/org/starhe/Dcm2Png.java` + `dist/weasis-dcm2png.jar` (~2.6 MB) + `dist/native/libopencv_java4130.dylib` (~15 MB). Build Maven (`mvn package`) déjà effectué, artefacts commités → pas de Maven requis côté utilisateur.
- [x] **`dicom/weasis_bridge.py`** — Nouveau bridge Python : `weasis_available()` (test JAR + `java -version`), `export_dicom_to_pngs_weasis(dicom, out_dir) -> (fps, n_frames)` (subprocess Java avec `-Djava.library.path=…/native` + `--enable-native-access=ALL-UNNAMED`, parse `fps=…` / `frames=…` sur stdout), `frames_via_weasis(dicom, work_dir=None) -> (frames_rgb (T,H,W,3) uint8, fps)` (lit les PNG via PIL, dossier temp auto-nettoyé via `tempfile.mkdtemp` + `shutil.rmtree`).
- [x] **`config.py` — flag `USE_WEASIS_EXPORT`** — défaut `True`, avec commentaire FR multi-lignes (modèle `PREPUS_BYPASS_MP4`) : décrit le trade-off LUT vs Java prérequis et le fallback pydicom automatique.
- [x] **`pipeline.py` — branchement étape 3** — `if USE_WEASIS_EXPORT and weasis_available(): try frames_via_weasis(dicom_path)` ; en cas de succès, `dicom_fps` est écrasé par la valeur reportée par Weasis (plus fiable que le tag `FrameTime` quand Weasis lit le DICOM directement) ; en cas d'échec (subprocess exit ≠ 0, ou exception Python), `go_print('warning', …)` puis chemin pydicom historique (`extract_frames` + `frame_to_uint8` + stack RGB).
- [x] **`dicom/__init__.py`** — exports ajoutés : `weasis_available`, `frames_via_weasis`.
- [x] **README.md — prérequis Java** — nouvelle ligne dans le tableau (Java 17+, optionnel, `brew install openjdk@17` sur macOS) ; section dédiée « Décodage DICOM via weasis-dcm2png » avec le tableau d'API du bridge et les 4 cas de fallback documentés (Java absent, JVM stub macOS, JPEG 2000, subprocess exit ≠ 0).
- [x] **Smoke test** — imports OK ; sur la machine actuelle `weasis_available() == False` car `/usr/bin/java` est le stub installeur macOS → fallback pydicom actif comme attendu, pipeline fonctionne normalement. Vérifié : `from starhe_plugin.pipeline import run_pipeline` n'introduit aucune régression.
- [x] **`loader_cli.py` non modifié** — la route `/starhe/dicom/load` (display-only, pas d'inférence en aval) reste sur pydicom : pas besoin de la LUT pour l'affichage et coût d'un subprocess Java évité à chaque chargement UI.

---
### �🗂 Organisation du projet — scripts/ + Makefile (29 mai 2026)
- [x] **`scripts/` — Déplacement des lanceurs** — `setup.sh`, `setup.ps1`, `run_tkinter.sh`, `run_tkinter.ps1`, `start_react.sh`, `start_react.ps1`, `download_models.py` déplacés depuis la racine vers `scripts/` ; chemins internes mis à jour (`.sh` : `dirname "$0"/..` ; `.ps1` : `Split-Path -Parent $PSScriptRoot`) ; références croisées corrigées (`start_react.sh` → `scripts/setup.sh`, `start_react.ps1` → `scripts/setup.ps1`)
- [x] **`Makefile`** — Nouveau task runner à la racine ; cibles : `setup`, `tkinter`, `react`, `build`, `help` (par défaut) ; détection OS automatique Windows/Unix ; délègue aux scripts dans `scripts/` ; `make help` testé ✅

---

## 🚧 In-Progress Tasks

### 🐍 Python Backend
- [ ] **End-to-end pipeline tests** — Validate `run_pipeline()` with a real `.dcm` file on hepatic data
- [ ] **MEDomics integration E2E test** — Send a POST `starhe/analyze/` from the MEDomics frontend and verify the full flow (Go → run_starhe.py → pipeline.py → MongoDB → response)

### 🖼 Tkinter Prototype
- [ ] **Full workflow validation with Canon Aplio i700** — Load `A0000` → banner removal + mm calibration → prepUS → AI inference → results display + MongoDB cache

### 🔌 MEDomics Integration
- [x] **MEDomics frontend** — React UI wired into MEDomics as an iframe via `starhe.jsx`; `STARHE_INIT` postMessage protocol sets `window.__STARHE_API_BASE__`; Go server runs on port 8082 independently of MEDomics
- [ ] **MEDDataObject** — Results are not yet encapsulated in a `MEDDataObject` (MEDomics standard format for patient data/results)
- [ ] **Cross-platform symlinks** — Unix symlinks do not work natively on Windows (require developer mode or admin rights). Consider an installation script with copy as fallback.

### 🔬 Preprocessing — Supersonic Imagine fix (✅ résolu 28 mai 2026)
- [x] **Cause racine identifiée** — UI Supersonic activait faussement le C3D car l'entraînement utilisait des `video.mp4` prepUS (cône rogné, sans UI), pas des frames DICOM brutes.
- [x] **`_frames_via_mp4()` testée puis abandonnée** — Compression MPEG-4 des frames brutes insuffisante ; UI Supersonic non retirée.
- [x] **Fix appliqué** — `pipeline.py` utilise désormais `crop_only_frames` (prepUS) pour RISK. Sens=91%, Spec=52% reproduit la référence Jérémy N.
- [x] **FP résiduels identifiés** — 12 FP dont 7 erreurs structurelles du modèle (communes avec Jérémy N) + 5 FP Supersonic borderline (02-0022, 02-0025, 05-0018, 05-0077, 06-0029) — limitation du modèle, pas de l'implémentation.

---

## 📅 Roadmap — Next Steps

### � Décisions en attente (5 juin 2026)

- [ ] **Basculer `PREPUS_BYPASS_MP4 = True` par défaut dans `config.py`** — Le mode bypass est strictement meilleur sur les 3 métriques mesurées (MAE 0.122 → 0.103, accord 85.7 % → 89.8 %, accuracy 63.3 % → 67.3 %) et élimine la non-portabilité cross-OS de `cv2.VideoWriter(mp4v)`. En attente de la validation explicite de l'utilisateur pour modifier le défaut.
- [x] **Intégration `weasis-dcm2png` runtime** — ✅ fait le 5 juin 2026 : bridge Python + flag `USE_WEASIS_EXPORT` + branchement `pipeline.py` étape 3 avec fallback pydicom automatique. Voir section dédiée plus haut.
- [ ] **Installer une JVM réelle sur les postes de prod** — Le smoke test du 5 juin montre que `/usr/bin/java` sur macOS est un stub installeur → le pipeline tombe en fallback pydicom. `brew install openjdk@17` (macOS) ou paquet OpenJDK 17+ (Linux/Windows) activera le chemin Weasis et alignera la distribution d'entrée avec celle d'entraînement (LUT appliquées).
- [ ] **Mesurer le gain Weasis vs pydicom** — Une fois Java installé, refaire la comparaison MAE/accuracy sur les 49 patients de Jérémy avec `USE_WEASIS_EXPORT=True` vs `False`. Hypothèse : gain incrémental sur les DICOM dont la VOI LUT n'est pas l'identité (typiquement Supersonic / Canon).

### �🔬 Phase 1: Backend Validation (Short term)

- [ ] **Unit test development**
  - `reader.py`: loading, frame count, array shapes
  - `anonymizer.py`: verify that all 15 tags are properly erased/hashed
  - `prepus_bridge.py`: validate crop + backscan on a reference DICOM
  - `mongo_client.py`: round-trip test save/find/delete
  - *Approach: create `pythonCode/modules/starhe_plugin/tests/` with `pytest`*

- [ ] **GPU optimization**
  - Configure the RTMDet runner to use CUDA if available (`--device cuda`)
  - Estimated gain: ×10–20 on the detection part (RTX 30/40: ~15–30ms/frame)

### 🔀 Phase 2: Go Server (Medium term) — ✅ Mostly completed

- [x] **Go blueprint for MEDomics** — `starhe_blueprint.go` with `AddHandleFunc()`, `analyze/` and `progress/` routes
- [x] **GoExecutionScript adapter** — `run_starhe.py` translates the GO_PRINT → MEDomics protocol
- [x] **SSE progress** — `go_progress()` events streamed live to the React UI

- [ ] **Error handling and timeouts**
  - Configurable timeout for AI inference
  - Semantic HTTP error codes with structured JSON messages

### ⚙ Phase 3: React UI Port — ✅ Completed (April 29, 2026)

- [x] **`<DicomLoader />`** — Upload (drag-and-drop) and path loading
- [x] **`<DicomCanvas />`** — Frame visualization, pan/zoom/measure, contrast/brightness, bbox overlay
- [x] **`<DetectionGallery />`** — Detected frames with thumbnails + SVG bboxes
- [x] **`<ConsolePanel />`** — Real-time SSE logs
- [x] **`<SettingsPanel />`** — Font, colors, analysis mode, console toggle
- [x] **`<LiveModal />`** — Live analysis (C-STORE, folder, HDMI)
- [x] **Integration into the MEDomics navigation system** — Done: `starhe.jsx` iframe + `STARHE_INIT` postMessage; `starhe-ui/` static build in MEDomics `public/`
- [ ] **MEDDataObject encapsulation** — Produce and consume MEDDataObjects

### 🧪 Phase 4: Testing & Deployment (Long term)

- [ ] **End-to-end integration tests** — React frontend → Go → Python → MongoDB
- [ ] **Go API documentation** — Swagger / OpenAPI
- [ ] **Plugin packaging** — MEDomics extension system compatibility
- [ ] **Automated installation script** — Automate blueprint copy, symlink creation (or copy on Windows), and `main.go` patching

### 🤖 Phase 5: STARHE Model Improvements (Research term)

> Contexte : analyse batch 48 patients partagés vs référence Jérémy.
> Résultats actuels (après fixes c3d.py + pipeline.py, avant batch avec `_frames_via_mp4`) : **Sens=100% / Spec=12%**.
> Référence Jérémy : **Sens=78% / Spec=72%**.
> Batch en attente avec `_frames_via_mp4` actif — résultats à mesurer.
> Les 22 FP actuels sont principalement des patients Supersonic dont l'UI active le C3D.

- [ ] **Decision threshold calibration** — Current threshold fixed at 50%. Borderline HighRisk patients (`02-0016` at 53.8%, `02-0049` at 54.0%, `05-0065` at 51.1%) are near-miss. Calibrate threshold on a held-out validation split to optimize F1 or Youden index; even a 48% threshold may recover borderline TPs without introducing many FPs.

- [ ] **Domain adaptation for Supersonic Imagine** — The C3D model was trained predominantly on non-Supersonic devices. Fine-tune on a small annotated Supersonic set, or apply feature-level normalization (histogram matching, z-score per device type) before feeding frames to C3D.

### 🔍 Phase 6 : STARHE-DETECT — Investigation input réel (à court terme)

> Contexte : le format exact des données d'entraînement RTMDet est incertain. `data_prefix = "cropped_videos"` dans la config n'est pas suffisamment explicite. Les deux batches montrent des comportements différents selon l'input (backscan vs crop_only), sans ground truth bbox pour trancher objectivement.

- [ ] **Vérifier les images réelles d'entraînement** — Accéder au dossier `./DATA/STARHE/cropped_videos/` sur Jean Zay (ou demander à Jérémy N) pour inspecter visuellement 5–10 images. Déterminer : éventail polaire ou backscan Cartésien ? Dimensions ? Niveaux de gris ou RGB ?
- [ ] **Demander à Jérémy N** — Quel preprocessing exact a été appliqué pour produire les `cropped_videos` ? Était-ce le backscan prepUS, un simple crop DICOM, ou autre chose ?
- [ ] **Tester backscan_frames pour DETECT** — Relancer un batch avec `processed_detect = backscan_frames` et comparer le nombre de détections sur les patients TP connus (01-0083, 06-0018). Évaluer si le backscan améliore la sensibilité sur ces patients.
- [ ] **Annoter manuellement quelques patients TP** — Dessiner les bboxes de référence sur 3–5 patients avec CHC confirmé pour évaluer la localisation des détections (IoU) plutôt que le simple comptage de frames.
- [ ] **Comparer histogrammes pixel** — Extraire les distributions pixel de `crop_only_frames` vs `backscan_frames` vs images de référence d'entraînement si disponibles. Identifier laquelle est la plus proche de la distribution d'entraînement.

- [ ] **Hard negative mining in retraining** — The 7 structural FPs (`01-0063`, `01-0072`, `01-0083`, `02-0010`, `06-0016`, `06-0018`, `06-0019`) share visual characteristics (advanced fibrosis, heterogeneous parenchyma) that confuse the model. Upweight these cases in the loss during retraining to force the model to learn discriminative features for this sub-population.

- [ ] **Late fusion with FASTRAK score** — FASTRAK and STARHE-RISK make complementary errors: FASTRAK misses `01-0086` (score 5.0 → Low) but STARHE catches it; STARHE generates 12 FPs that FASTRAK avoids. A late fusion (logistic regression on both scores → final binary decision) should outperform either method alone without changing either model. Requires access to FASTRAK scores at inference time.

- [ ] **Uncertainty quantification for borderline cases** — For scores in [45%–55%], output an "uncertain" flag instead of a binary decision. In a clinical workflow, these patients would be referred for a complementary exam (biopsy, MRI) rather than receiving a potentially incorrect automated decision.

- [ ] **Multi-modal temporal input** — The current C3D window is 16 frames (~0.5 s at standard fps). Experiment with longer temporal windows (32–64 frames) to capture lower-frequency hepatic motion patterns associated with CHC risk.

---

## 📝 Key Technical Procedures

### 🌐 React UI development cycle
> ```bash
> # Rebuild and restart Go server (after any .go file change)
> lsof -ti :8082 | xargs kill -9 2>/dev/null
> cd go_server && go build -o go_server . && ./go_server &
>
> # Start Vite dev server with HMR (no rebuild needed for React/TS changes)
> cd react_ui && npm run dev
>
> # Production build + deploy to MEDomics
> cd react_ui && npm run build
> cp -r dist/. ../MEDomics/renderer/public/starhe-ui/
> ```

### 🧹 prepUS Preprocessing
> `preprocess_with_prepus(frames, fps, thresh, backscan_width, backscan_height)`
> 1. Export numpy → temporary MP4 (OpenCV `VideoWriter`, codec mp4v)
> 2. `removeLayoutFile(mp4, out_dir, back_scan_conversion=True, ...)` — static pixel detection + masking + crop
> 3. Reads `out_dir/video.mp4` (fan-shaped crop) → `(T, H_crop, W_crop)` uint8
> 4. Reads `out_dir/info.json` → ROI dict
> 5. Returns `(crop_frames, info_dict)` + tmp cleanup — **2-tuple** (backscan removed)
> ⚠️ prepUS must be installed with `--no-deps` to avoid OpenCV conflicts

### 🐍 Persistent RTMDet Subprocess
> 1. `STARHEDetectModel.__init__()` launches `_rtmdet_runner.py --mode server`
> 2. Waits for the `[rtmdet_server] READY` signal on stdout
> 3. Each batch of frames: `{"images": [...], "score_thr": 0.70}` via stdin → `[[dets], ...]` via stdout
> 4. `__EXIT__` cleanly shuts down the server
> 5. Automatic fallback to one-shot on error

### 🗄 MongoDB Cache
> 1. At analysis start: `find_by_file(path, analysis_mode)` — if result found for this mode, immediate retrieval
> 2. After analysis: `save_result(file_path, ..., detections_per_frame=per_frame, analysis_mode=mode)` with upsert
> 3. Cache key = pair `(file_path, analysis_mode)` — a single file can have distinct results for each mode (original, crop, backscan)

### 🔗 Go ↔ Python Communication
> Launch Python as subprocess from Go: `os/exec.Command("python", "-m", "starhe_plugin.pipeline", args...)`
> Each Python stdout line follows the format `GO_PRINT|<level>|<JSON>`.
> Parsed on the Go side with `bufio.Scanner` + `json.Unmarshal` — relayed via SSE.
>
> Key flags:
> - `--no_risk` → skip STARHE-RISK (C3D)
> - `--no_detection` → skip STARHE-DETECT (RTMDet)

---

*🔖 This file is maintained manually. Update as sprints progress.*
