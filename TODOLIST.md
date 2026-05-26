# 📋 TODOLIST — STARHE Plugin / MEDomics
> Operational project logbook.  
> Last updated: **26 mai 2026**

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

### 🔬 Preprocessing — Supersonic Imagine fix (identified 14 mai 2026)
- [ ] **Detect `Manufacturer` DICOM tag** (`0008|0070`) in `prepus_bridge.py` / `reader.py` to identify Supersonic Imagine devices before preprocessing
- [ ] **Calibrate crop geometry for Supersonic** — 5 confirmed FP patients caused by crop mismatch on Supersonic Imagine devices: `02-0022`, `02-0025`, `05-0018`, `05-0077`, `06-0029`; apply device-specific pixel spacing normalization or ROI recalibration before passing frames to C3D
- [ ] **Validate fix on Supersonic batch** — re-run batch after fix; expected result: 5 FP → TN, bringing specificity from 52% → ~72% (matching Jérémy's reference)

---

## 📅 Roadmap — Next Steps

### 🔬 Phase 1: Backend Validation (Short term)

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

> Context: batch analysis of 14 mai 2026 (49 patients) vs. Jérémy reference (50 patients).
> Current results: **Sens=91.7% / Spec=52%** — reference: **Sens=72% / Spec=72%**.
> Two categories of remaining errors: 5 FP Supersonic (fixable via preprocessing), 7 FP structural (model limit, also present in Jérémy's reference).

- [ ] **Decision threshold calibration** — Current threshold fixed at 50%. Borderline HighRisk patients (`02-0016` at 53.8%, `02-0049` at 54.0%, `05-0065` at 51.1%) are near-miss. Calibrate threshold on a held-out validation split to optimize F1 or Youden index; even a 48% threshold may recover borderline TPs without introducing many FPs.

- [ ] **Domain adaptation for Supersonic Imagine** — The C3D model was trained predominantly on non-Supersonic devices. Fine-tune on a small annotated Supersonic set, or apply feature-level normalization (histogram matching, z-score per device type) before feeding frames to C3D.

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
> `preprocess_with_prepus(frames, fps, thresh, back_scan_conversion, backscan_width, backscan_height)`
> 1. Export numpy → temporary MP4 (OpenCV)
> 2. `removeLayoutFile(mp4, out_dir, ...)` — static pixel detection + masking + crop
> 3. Always called with `back_scan_conversion=True` → dual output in a single pass
> 4. Returns `(backscan_array, crop_only_array, info_dict)` + tmp cleanup
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
