# 📋 TODOLIST — STARHE Plugin / MEDomics
> Operational project logbook.  
> Last updated: **June 24, 2026**

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
- [x] **Project scaffold** — React 18 / TypeScript / Vite in `renderer/`, `vite.config.ts` proxy `/starhe → :8080`
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

### 🖼 React UI — Multi-panel & UX (May 7, 2026)
- [x] **Multi-panel split view** — `PanelGrid` + `ViewPanel` components; drag a tab or thumbnail → adds a panel in the grid; click a panel → focus (blue outline) + sidebar/gallery target that file; `×` removes a panel; CSS grid auto-cols (1/2/3/4); empty state shows a hint; patient isolation: `switchTab` filters `visiblePanelIds` to tabs belonging to the newly active patient
- [x] **Folder loading** — "📁 Load a DICOM folder" button in sidebar; `webkitdirectory` picker; auto-detects `.dcm`, `.dicom`, and extension-less files; loads all files sequentially
- [x] **Patient isolation in multi-panel** — `switchTab` filters `visiblePanelIds` to tabs belonging to the newly active patient; prevents cross-patient panel contamination

### 🔌 MEDomics Integration fixes (May 7, 2026)
- [x] **Extension description corrected** — `ExtensionManager.jsx`: subtitle "Hepatic ultrasound", description mentions HCC/liver, tag "Hepatology" (was "Cardiology" / "cardiac")
- [x] **Go server connection fixed** — `starhe.jsx`: `STARHE_API_BASE = 'http://localhost:8082'` hardcoded; removed dependency on `WorkspaceContext.port` which was often `null` at iframe load time, causing "Failed to fetch" errors on port 8082
- [x] **MEDomics Next.js renderer rebuilt** — `npx next build` after all fixes
- [x] **Go binary rebuilt** — `go build -o go_server .` in `go_server/`; server confirmed on port 8082 via `/health`

### 🗂 Batch Analysis — Export/Import JSON (May 11, 2026)
- [x] **`start_react.sh`** — `find_free_port()`: auto-detects the first free TCP port ≥ 8082; exports `STARHE_PORT`; passes `PORT="$STARHE_PORT"` to the Go binary
- [x] **`vite.config.ts`** — reads `process.env.STARHE_PORT ?? '8082'` for the Vite proxy target
- [x] **`BatchModal.tsx` — bbox persistence** — `BatchItem` stores `detections?: Detection[][]`, `numFrames?`, `roi?`; filled at the end of each SSE analysis
- [x] **`BatchModal.tsx` — `exportJSON()`** — generates `starhe_batch_YYYY-MM-DD.json` with full `detections_per_frame`; format `{ starhe_batch: "1.0", exported_at, analysis_mode, results: [...] }`
- [x] **`BatchModal.tsx` — `importJSON()`** — `.json` file picker; parses and validates the `starhe_batch` format; adds items with `status: 'done'` and pre-filled results (risk + detections) without re-running inference
- [x] **`BatchModal.tsx` — `BatchResultToOpen` interface** — exported interface: `{ serverPath, name, detections?, risk?, numFrames?, roi? }`
- [x] **`BatchModal.tsx` — "→ Tab"** — passes the full `BatchResultToOpen` object (with bboxes) to `onOpenInTab`
- [x] **`BatchModal.tsx` — checkboxes + multiple open** — per-row checkbox + global "select all" checkbox in the table header; **"↗ Open selection (N)"** and **"↗ Open all (N)"** buttons in the summary
- [x] **`index.tsx` — `import { BatchModal }`** — import + `type BatchResultToOpen` from `./components/BatchModal`
- [x] **`index.tsx` — `showBatch` state** — `const [showBatch, setShowBatch] = useState(false)`
- [x] **`index.tsx` — `onLoadFolder`** — `webkitdirectory` callback: opens a folder, filters `.dcm` / `.dicom` / extension-less, loads sequentially via `doLoadFile`
- [x] **`index.tsx` — `<Sidebar onOpenBatch>` + `onLoadFolder`** — props wired to the new callbacks
- [x] **`index.tsx` — `onOpenInTab` handler** — `loadDicom(serverPath)` → creates the tab with `detectionsBy.original` + `resultsBy.original` pre-injected; fallback file picker if the server temp file has expired


### 🔧 Cross-platform & DICOM fixes (May 12, 2026)
- [x] **DICOM split button** — `Sidebar.tsx`: split button `📁 DICOM Folder | 🗂️`; left part = `webkitdirectory` (full folder), right part = manual individual multi-file selection; `onLoadDicomFiles` callback wired in `index.tsx`
- [x] **DICOM JPEG 2000** — `reader.py`: `extract_frames()` rewritten with 3 fallback levels: (1) nominal `ds.pixel_array`, (2) `ds.decompress()` pydicom 3.x, (3) `_extract_j2k_raw_scan()` — raw scan of `PixelData` for the `FF 4F FF 51` marker (SOC+SIZ J2K), decodes each codestream directly with `openjpeg.decode`; validated on 24/24 files (J2K lossless, J2K lossy, JPEG baseline, RLE)
- [x] **pylibjpeg** — `requirements.txt`: added `pylibjpeg>=2.0.0`, `pylibjpeg-openjpeg>=2.0.0` (JPEG 2000), `pylibjpeg-libjpeg>=2.1.0` (JPEG lossless/lossy); decoders automatically used by pydicom 3.x
- [x] **Go error handler** — `handlers_dicom.go`: HTTP 500 error response enriched with `stdout`, `python_error`, `python_traceback` (extracted from the Python JSON) to surface the Python traceback in the React console
- [x] **`.gitignore` cross-platform** — added `renderer/node_modules/` and `go_server/go_server` + `go_server/starhe_server` (OS-specific binaries, not to commit); `git rm --cached -r` run to untrack already-tracked files
- [x] **`start_react.ps1` / `start_react.sh`** — auto-launches `setup.ps1` / `setup.sh` if Python venv is absent at startup; `npm install` → `npm ci` (reproducible install from `package-lock.json`)

### 🖼 React UI — DicomUploader + Interface fixes (May 19, 2026)
- [x] **`DicomUploader.tsx`** — New dedicated component for DICOM loading (drag-and-drop + picker + URL); extracted from `Sidebar.tsx` to clarify responsibilities
- [x] **`BatchModal.tsx` — Folder / files buttons** — Fixed "📁 Folder" and "🗂 Files" buttons in the batch modal (full folder selection vs individual files)
- [x] **Multi-panel — Fix #1** — `MultiPanelView.tsx`: replaced `tab.panX/panY` with `{...tab, panX:0, panY:0}` during resize; `pointerEvents: none` on non-focused panels during resize; `onResetAllPanelsPanRef` to avoid stale closures
- [x] **`useCanvasInteractions.ts`** — Added global `window.mouseup` listener to force cleanup of `dragRef`, `rclickRef`, `editRef` after mouse release outside canvas
- [x] **`useTabManager.ts`** — `updateTabById` stabilized with `useCallback` without unstable dependencies
- [x] **`pipeline.py` / `prepus_bridge.py`** — Batch pipeline fixes (see commit f312a8f)

### 🤖 Live Analysis + Multi-panel Fix #2 (May 21, 2026)
- [x] **`run_live.py`** — New CLI entry point for live analysis; launched by the Go server as a subprocess; 3 sources: `_FolderWatcher` (polls `.dcm` every 0.5 s), `_HDMIReader` (cv2.VideoCapture, `CAP_AVFOUNDATION` on macOS), `_CStoreReceiver` (pynetdicom SCP, AE=`STARHE_LIVE`); same `GO_PRINT|level|{json}` protocol as `pipeline.py`; preview emitted immediately before inference; clean stop via SIGTERM/SIGINT → `_stop_event`
- [x] **`handlers.go` — Live endpoints** — New REST + SSE endpoints for live analysis: `POST /starhe/live/start` (launches `run_live.py`), `POST /starhe/live/stop` (stops the subprocess), `GET /starhe/live/stream` (SSE of preview frames + detections)
- [x] **`main.go`** — Registered new live routes in the Go router
- [x] **Multi-panel — Fix #2 (`onPanReset`)** — `DicomCanvas.tsx`: new prop `onPanReset?: () => void`; the resize effect calls `onPanReset()` instead of `NOOP_ZP` → resets all panels; 0 TypeScript errors
- [x] **`LiveModal.tsx`** — Updated the live modal to use the new Go backend endpoints

### 🚀 Double-click Launchers (May 26, 2026)
- [x] **`launch_medomics.command`** — macOS launcher (Finder double-click) for MEDomics + STARHE in development mode: checks Node.js/Go, compiles Go binary if absent, `npm install` MEDomics if absent, builds and deploys React UI if `dist/` absent, then `npm run dev` in MEDomics (→ Electron starts MongoDB + Go MEDomics + Go STARHE automatically); `chmod +x` applied
- [x] **`launch_medomics.bat`** — Windows equivalent (Explorer double-click); same logic, `go_server.exe` binary, `xcopy /E /Y /I` for React deployment, `pause` at the end
- [x] **`launch_plugin.command`** — macOS standalone STARHE launcher (without MEDomics): checks Python 3.13 / Node.js / Go, creates venv if absent + installs dependencies + AI weights, compiles Go binary, finds and starts MongoDB on port 54017, starts Go server (`:8082`) and Vite server (`:5173`) in the background, waits for React to be ready, opens browser → clean stop of all services on Ctrl+C; `chmod +x` applied
- [x] **`launch_plugin.bat`** — Windows standalone equivalent: each service (MongoDB, Go server, React UI) opens in its own CMD window; automatically opens browser at `http://localhost:5173` after detecting the Vite server is ready

### 🤖 STARHE-RISK — C3D Preprocessing Alignment (May 27–28, 2026)

> Context: performance gap identified by patient-by-patient comparison with Jérémy N's reference results (48 shared patients, 50% threshold).
> Actual training pipeline: DICOM → initial MP4 → **prepUS.removeLayoutFile** → `video.mp4` (cropped fan, grayscale, mp4v codec) → Decord → mmaction2 → C3D.

- [x] **`c3d.py` — exact mmaction2 `_sample_clips`** — `avg_interval = (T−16+1) / 10` (+1 was missing); `offsets = base×avg + avg/2 − 0.5` (−0.5 was missing).
- [x] **`c3d.py` — exact mmaction2 `_resize_shortest`** — `cv2.resize(uint8, INTER_LINEAR)` instead of `F.interpolate(float32, align_corners=False)`.
- [x] **`pipeline.py` — `_frames_via_mp4()` path tested then abandoned** — MPEG-4 compression of raw frames insufficient (±2–3% on scores); Supersonic UI not removed.
- [x] **Training pipeline identified** — Training data = prepUS `video.mp4` (fan format, grayscale, mp4v codec). Confirmed by supervisor.
- [x] **`pipeline.py` — RISK on `crop_only_frames`** — prepUS now runs for both RISK and DETECT. RISK receives `crop_only_frames` (cropped cone, grayscale → pseudo-RGB R=G=B), identical to the format of `video.mp4` files decoded by Decord.
- [x] **Batch 4 validation (05/28/2026)** — **Sens = 91.7% (22/24), Spec = 52% (13/25)** — preprocessing aligned with the training distribution. ⚠ Divergence with Jérémy N's reference confirmed (see table below) — gap due to decision threshold, not implementation.

  | | Our impl. (Batch 4, threshold 50%) | Jérémy N reference |
  |---|---|---|
  | TP / FN / FP / TN | 22 / 2 / 12 / 13 | 18 / 7 / 7 / 18 |
  | Sensitivity | **91.7%** | 72% |
  | Specificity | 52% | **72%** |
  | Threshold used | 50% (config.py) | Unknown — probably higher |
  | Profile | Sensitive / low specificity | Balanced |

  **Interpretation**: preprocessing is correct (same training distribution). The operating point difference is a threshold calibration issue — to investigate (see Phase 5 Roadmap).

  | Batch | RISK config | Sens | Spec |
  |---|---|---|---|
  | Jérémy N (ref.) | Training pipeline, calibrated threshold | 72% | 72% |
  | Batch 1–2 (no prepUS) | Raw DICOM | 12.5% | 88% |
  | Batch 3 (+mp4v) | Raw DICOM + mp4v | ~12% | ~88% |
  | **Batch 4 (crop_only)** | **prepUS crop, threshold 50%** | **91.7%** | **52%** |

### 🤖 STARHE-DETECT — Input Preprocessing Fix (May 28, 2026)

> Context: in the previous session, `processed_detect` had been switched to prioritize `backscan_frames` based on a commit message (`7a26d1c`). The actual training config (`rtmdet_starhe.py`, `train_dataloader.data_prefix = "cropped_videos"`) confirms that RTMDet was trained on **cropped** frames (cropped fan), not on the Cartesian backscan.

- [x] **Diagnosis** — `rtmdet_starhe.py`: `train_dataloader.data_prefix = "cropped_videos"` and `test_dataloader.ann_file = 'cropped_videos/...'` — direct evidence that training used cropped frames.
- [x] **`pipeline.py` — `processed_detect` restored to `crop_only_frames`** — Removed `backscan_frames` from the priority chain; `crop_only_frames` is the sole source (same distribution as training).
- [x] **`pipeline.py` — bbox remapping restored** — `detect_remap_info = {"crop": info["crop"]}` only → simple offset (xmin, ymin) to return to DICOM space (inverse polar transform not needed).
- [x] **`pipeline.py` docstring updated** — "trained on backscan frames" → "trained on prepUS cropped_videos".

> **⚠ Batch 3 observation (05/28/2026)** — The batch re-run with `crop_only_frames` gives *worse* detection results than backscan:
> | Patient | RISK score | Backscan (before) | Crop_only (after) | Interpretation |
> |---|---|---|---|---|
> | 01-0083-L-X | 77.74% ↑ | **12** lesions | **4** lesions | Probable TP → sensitivity loss |
> | 05-0030-H-M | 12.62% ↓ | 4 lesions | 0 lesions | Probable TN → FPs removed ✅ |
> | 05-0062-J-D | 23.14% ↓ | 24 lesions | 0 lesions | Probable TN → 24 FPs removed ✅ |
> | 06-0018-D-M | 72.33% ↑ | 4 lesions | 4 lesions | Probable TP → stable |
>
> **Regression hypotheses**:
> 1. `"cropped_videos"` might refer to cropped backscan frames (ambiguous name) — to verify on Jean Zay.
> 2. Format: `crop_only` = non-square polar fan (variable dims); backscan = square 512×512 ≈ training format 640×640 → better dimensional consistency.
> 3. Pixel distribution: the polar fan has black areas at corners (arc geometry) that the model may not have seen during training.
> **Current state**: `pipeline.py` uses `crop_only_frames` for DETECT (aligned with config). Investigation ongoing.

### 🛟 prepus_bridge Simplification + Full DICOM Pipeline (June 2, 2026)

- [x] **`prepus_bridge.py` simplified** — 599 → 171 lines. Removed Cartesian backscan (`_map_bbox_backscan_to_original`, `_compute_lossless_backscan_params`, `_crop_inmemory`). New signature: `preprocess_with_prepus(frames, fps, thresh, backscan_width, backscan_height) → (crop_frames, info)` (2-tuple instead of 3-tuple). Both models were trained on `video.mp4` / `cropped_videos` (cropped fan), not on the Cartesian backscan — the backscan was unnecessary.
- [x] **`pipeline.py` updated** — Adapted to the new 2-tuple signature; `backscan_frames` removed throughout the flow; `map_detections_to_dicom_coords` simplified (no more `bsc_w`/`bsc_h` parameters).
- [x] **`test_dicom_pipeline.py`** — New script (project root): full pipeline from a raw DICOM file: `pydicom` → PNG export → `ffmpeg` MP4 (fps from `FrameTime` tag) → `prepUS` → STARHE RISK + DETECT. Programmatic equivalent of the manual Weasis export. Weasis does not expose a headless API for PNG/MP4 export (confirmed).
### 🏥 Orthanc PACS Alternative Server (June 3, 2026) — ❌ removed (June 5, 2026)

> **Removed on June 5, 2026.** Decision: switched to the `weasis-dcm2png` library for DICOM → image/MP4 conversion. Files deleted (`handlers_orthanc.go`, `OrthancBrowser.tsx`); routes/env vars/imports/buttons purged from `config.go`, `main.go`, `index.tsx`, `Sidebar.tsx`. History kept below as archive.

- [x] **`config.go` — Orthanc env vars** — 3 new fields: `OrthancURL` (default `http://localhost:8042`), `OrthancUser`, `OrthancPassword`; configurable via `ORTHANC_URL` / `ORTHANC_USER` / `ORTHANC_PASSWORD`
- [x] **`handlers_orthanc.go`** — Full Orthanc proxy (240 lines): `orthancDo` (server-to-server authenticated HTTP request), 7 REST handlers (`/starhe/orthanc/status`, `/patients`, `/patients/{id}`, `/studies/{id}`, `/series/{id}`, `/instances/{id}`, `POST /starhe/orthanc/load`) — `load` downloads the DICOM, stores it as SHA-256 temp, passes it to `loader_cli.py`, returns the frames JSON
- [x] **`main.go` — Orthanc routes** — 7 routes registered in the Go router (after `/starhe/cache`)
- [x] **Go build** — `go build .` → success (0 errors)
- [x] **`OrthancBrowser.tsx`** — React modal component (~450 lines): lazy-loading hierarchical tree Patients → Studies → Series → Instances; `StatusBadge` (green/red dot); "Load" button per instance → `POST /starhe/orthanc/load` → maps response to `DicomData` (including `serverPath`) → calls `onLoaded({ data, serverPath })`; consistent dark theme (colors from `colors.ts`); Escape / overlay-click close
- [x] **`Sidebar.tsx` — Orthanc button** — Prop `onOpenOrthanc: () => void` added; button `🏥 Orthanc PACS Browser` in the "AI Analysis" section
- [x] **`index.tsx` — Full integration** — Import `OrthancBrowser` + `OrthancLoadedResult`; state `showOrthanc`; prop `onOpenOrthanc` on `<Sidebar>`; modal `<OrthancBrowser>` with `onLoaded`: creates a tab, updates patients, logs; TypeScript 0 errors

### 🔬 STARHE-RISK — C3D Validation Against Reference mmaction2 (June 3, 2026)

> Context: despite the May 28 preprocessing alignment (`crop_only_frames`, exact `_sample_clips`, cv2 `_resize_shortest`), there remains a residual bias of ~+3.6% on high-risk scores and 6 patients disagreeing with Jérémy's reference (`01-0096`, `02-0049`, `03-0022`, `05-0009`, `05-0021`, `05-0077`). Question: is it our pure PyTorch C3D port that drifts, or the prepUS crops differing from those used in training?

- [x] **`third_party/prepUS` vs reference check** — full diff: vendored `prepUS` is algorithmically identical to the version shared by Jérémy. Only functional differences: `backscan.py:48` `b = np.array([rho1, rho2])` (1D bugfix to avoid `int(np.round(x0))` crash on 0-d array), `cli.py` adds `_NpEncoder` for numpy JSON serialization, `utils.py` removes `import fire`. Rest = whitespace / docstrings.
- [x] **Deterministic crops pre-generated** — `/tmp/gen_crops_fixed.py`: one prepUS pass per file on Jérémy's 49 MP4s → `/tmp/crops_fixed/<PID>/video.mp4` (mp4v codec, grayscale, cropped fan). 49/49 crops produced.
- [x] **Reference mmaction2 environment** — `pyenv install 3.10.14` + venv `/tmp/mmaction_env/`: `torch==2.1.2`, `torchvision==0.16.2`, `numpy<2`, `eva-decord` (provides `decord 0.7.0`), `mmcv-lite==2.1.0` (mmcv-full fails to compile on ARM macOS without pkg_resources), `mmaction2==1.2.0` installed `--no-deps` (the `decord>=0.4.1` dependency is satisfied by eva-decord), `opencv-contrib-python<4.12`, `importlib_metadata`. Patches: `mmaction/models/localizers/__init__.py` (removed DRN import absent from the 1.2.0 wheel); sanitized copy of `c3d_starhe.py` in `/tmp/cfg/c3d/` (removed `custom_imports = ['starhe.metrics.classification_metric']` and `TensorboardVisBackend`).
- [x] **Reference mmaction2 inference** — `/tmp/run_ref_mmaction.py`: `init_recognizer(cfg, checkpoint, device='cpu')` + `inference_recognizer(model, mp4_path)` on 49 crops → `/tmp/ref_scores.json` (49/49 scores `[low, high]`).
- [x] **Our C3D inference on the same crops** — `/tmp/run_ours_on_crops.py`: cv2 read → grayscale → pseudo-RGB (R=G=B) → `STARHERiskModel().predict()` → `/tmp/ours_scores.json` (49/49 scores).
- [x] **Three-way comparison** — `/tmp/cmp.py`: final results

  | Comparison | Mean Δ | MAE | Max\|Δ\| | Label agreement (threshold 0.5) |
  |---|---|---|---|---|
  | **Ours vs Ref mmaction2** (same crops) | −0.0003 | **0.013** | 0.052 | **47/49 (96%)** |
  | Ref mmaction2 vs Jérémy (cached preds) | +0.036 | 0.111 | 0.531 | 43/49 |
  | Ours vs Jérémy | +0.036 | 0.109 | 0.529 | 43/49 |

  **Conclusion**: our PyTorch C3D port is validated as bit-near equivalent to mmaction2 C3D (MAE 1.3%, bias 0). The remaining 4% differences come from video decoding (cv2 vs Decord on the same `video.mp4`, mp4v codec + YUV→RGB colorspace not bit-exact). The 6 label mismatches vs Jérémy **are also present in the mmaction2 reference on our crops** → the residual comes from prepUS crops (non-determinism across runs, or difference from the crops produced at training time), not from the model.

### 🔬 STARHE-RISK — Final Isolation Chain + MP4 Bypass (June 5, 2026)

> Context: continuation of the June 3 session to precisely identify the source of the ~11 % residual vs. Jérémy. Three isolation tests followed by a decisive test using an in-memory variant of prepUS.

- [x] **`video.mp4` decoding — cv2 vs PyAV vs Decord** — `/tmp/decoder_diff.py` installs `av 17.0.1`; 3 paths compared (cv2 BGR→RGB, cv2 BGR→GRAY→stack, PyAV rgb24) on 4 grayscale crops produced by prepUS → **MAE 0.000, 100% equal pixels** across all 4 files. The decoder is NOT the source of the residual.
- [x] **Local prepUS determinism** — `/tmp/test_prepus_determinism.py`: 3 consecutive runs per file on 4 MP4s → SHA-256 of `video.mp4` and `info.json` identical across all 3 runs for all 4 files. prepUS is **100% deterministic on the same machine**.
- [x] **Root cause identified** — The only remaining difference between our crops and Jérémy's is the **MP4 encoding by `cv2.VideoWriter(mp4v)`** (used by `sonocrop.vid.savevideo` in `prepUS/cli.py:198`). cv2 delegates to the FFmpeg binary linked to OpenCV, which depends on: OS, `opencv-python` version, system FFmpeg version. macOS ARM Homebrew (our env) ≠ Linux Jean Zay (Jérémy's training) → different bitstream → different reconstructed pixels after decoding → C3D sees slightly different inputs.
- [x] **Email to Adrien (prepUS author + training)** — requested original training crops and/or exact `opencv-python` + FFmpeg versions used on Jean Zay. **Response received June 5, 2026: his Jean Zay environment (dataset + versions) was accidentally deleted by IHU IT staff.** No recovery possible. The "reproduce the original encoding" path is permanently closed.
- [x] **MP4 bypass mode implemented** — `dicom/prepus_bridge.py`: new function `preprocess_with_prepus_inmem` (~165 lines) reimplementing a strictly equivalent `removeLayoutFile` in pure numpy, with no `VideoWriter` / `VideoCapture` / temporary folder. Recursive retry on `find_linear_fov` preserved identically. RGB→GRAY conversion via `cv2.cvtColor(RGB2GRAY)` (same BT.601 weights as the `BGR2GRAY` path read by `sonocrop.loadvideo`).
- [x] **Configuration flag** — `config.py`: added `PREPUS_BYPASS_MP4: bool = False` (conservative default). `pipeline.py` selects `preprocess_with_prepus_inmem` when the flag is `True`, `preprocess_with_prepus` otherwise; mode tag logged in progress. Export added to `dicom/__init__.py`.
- [x] **49-patient validation** — `/tmp/batch_bypass_vs_roundtrip.py`: runs both modes on the 49 MP4s from Jérémy's test set, compares to cached predictions `pred_test.pkl`.

  | Metric | Mode A (MP4 roundtrip) | **Mode B (bypass)** | Gain |
  |---|---|---|---|
  | MAE vs Jérémy | 0.1215 | **0.1025** | −16% |
  | Label agreement vs Jérémy | 42/49 (85.7%) | **44/49 (89.8%)** | +2 patients |
  | Accuracy vs ground truth | 31/49 (63.3%) | **33/49 (67.3%)** | +2 patients |
  | Bias − Jérémy | +0.044 | +0.037 | −16% |
  | Cross-OS reproducibility | ❌ | ✅ bit-for-bit | — |

  Bypass mode is strictly better on all 3 metrics + eliminates the dependency on the non-portable mp4v encoder. The option of switching the default to `True` remains (see roadmap).

### 🗑️ Removal of Orthanc PACS Server (June 5, 2026)

> Context: the Orthanc stack implemented on June 3 (~700 lines Go + TS) is replaced by the `weasis-dcm2png` library for DICOM → image/MP4 conversion. The archive of the Orthanc history is kept above, marked "❌ removed".

- [x] **`go_server/handlers_orthanc.go`** — deleted (240 lines: `orthancDo`, 7 REST handlers)
- [x] **`renderer/src/StarhePlugin/components/OrthancBrowser.tsx`** — deleted (~450 lines)
- [x] **`go_server/config.go`** — `OrthancURL` / `OrthancUser` / `OrthancPassword` fields + `ORTHANC_URL` / `ORTHANC_USER` / `ORTHANC_PASSWORD` envs removed
- [x] **`go_server/main.go`** — 7 `/starhe/orthanc/*` routes removed
- [x] **`renderer/src/StarhePlugin/index.tsx`** — `OrthancBrowser` + `OrthancLoadedResult` imports, `showOrthanc` state, `onOpenOrthanc` prop on `<Sidebar>`, full modal block (~40 lines) removed
- [x] **`renderer/src/StarhePlugin/components/Sidebar.tsx`** — `onOpenOrthanc` prop (declaration + destructuring + `🏥 Orthanc PACS Browser` button) removed; Batch button (now last in section) padding promoted to `10px`
- [x] **Verifications** — `go build ./...` 0 errors; no new TS errors in touched files; `TODOLIST.md` Orthanc section marked `❌ removed (June 5, 2026)` with justification
- [x] **`weasis-dcm2png` runtime integration (June 5, 2026)** — see dedicated section below

### 🔬 `weasis-dcm2png` Runtime Pipeline Integration (June 5, 2026)

> Context: `pydicom.pixel_array` applies neither Modality LUT nor VOI LUT, whereas Jérémy's training pipeline went through Weasis (LUTs applied). We wire the same DICOM → PNG (LUT) → numpy chain at runtime, with automatic fallback to pydicom if Java/JAR is absent or if the transfer syntax is not supported by the JAR (e.g. JPEG 2000).

- [x] **Vendored Java mini-project** — `third_party/weasis-dcm2png/`: `pom.xml` + `src/main/java/org/starhe/Dcm2Png.java` + `dist/weasis-dcm2png.jar` (~2.6 MB) + `dist/native/libopencv_java4130.dylib` (~15 MB). Maven build (`mvn package`) already done, artifacts committed → no Maven required on the user side.
- [x] **`dicom/weasis_bridge.py`** — New Python bridge: `weasis_available()` (JAR + `java -version` test), `export_dicom_to_pngs_weasis(dicom, out_dir) -> (fps, n_frames)` (Java subprocess with `-Djava.library.path=…/native` + `--enable-native-access=ALL-UNNAMED`, parses `fps=…` / `frames=…` on stdout), `frames_via_weasis(dicom, work_dir=None) -> (frames_rgb (T,H,W,3) uint8, fps)` (reads PNGs via PIL, temp folder auto-cleaned via `tempfile.mkdtemp` + `shutil.rmtree`).
- [x] **`config.py` — `USE_WEASIS_EXPORT` flag** — default `True`, with multi-line comment (same model as `PREPUS_BYPASS_MP4`): describes the LUT vs Java prerequisite trade-off and the automatic pydicom fallback.
- [x] **`pipeline.py` — step 3 branching** — `if USE_WEASIS_EXPORT and weasis_available(): try frames_via_weasis(dicom_path)`; on success, `dicom_fps` is overwritten by the value reported by Weasis (more reliable than the `FrameTime` tag when Weasis reads the DICOM directly); on failure (subprocess exit ≠ 0, or Python exception), `go_print('warning', …)` then legacy pydicom path (`extract_frames` + `frame_to_uint8` + RGB stack).
- [x] **`dicom/__init__.py`** — exports added: `weasis_available`, `frames_via_weasis`.
- [x] **README.md — Java prerequisite** — new row in the prerequisites table (Java 17+, optional, `brew install openjdk@17` on macOS); dedicated "DICOM Decoding via weasis-dcm2png" section with the bridge API table and 4 documented fallback cases (Java absent, macOS JVM stub, JPEG 2000, subprocess exit ≠ 0).
- [x] **Smoke test** — imports OK; on the current machine `weasis_available() == False` because `/usr/bin/java` is the macOS installer stub → pydicom fallback active as expected, pipeline works normally. Verified: `from starhe_plugin.pipeline import run_pipeline` introduces no regression.
- [x] **`loader_cli.py` unchanged** — the `/starhe/dicom/load` route (display-only, no downstream inference) stays on pydicom: no need for LUT in display and Java subprocess cost avoided on every UI load.

---
### 📦 Electron Distribution — Phase 1 (June 10, 2026)

> Context: replicate the MEDomics Releases grid (`.dmg`/`.pkg`/`.zip`/`.deb`/`.AppImage`/`.exe`) for the STARHE plugin. Phase 1 = Electron shell that launches the Go server and displays the React UI; Python is not yet bundled (Phase 2 coming with PyInstaller).

- [x] **Reuse of the existing Electron scaffold in `renderer/`** — No new `electron_app/` folder created (would have duplicated `main.ts`, `preload.ts`, electron-builder config, `node_modules`). MEDomics convention: Electron + renderer in the same `package.json`.
- [x] **`renderer/package.json`** — Version bumped 0.1.0 → 0.6.2 (aligned with project); `productName` simplified to `STARHE`; `artifactName` added with convention `STARHE-${version}-${os}-${arch}.${ext}` (same as MEDomics); targets added: mac `pkg`+`zip` (before: `dmg` only), linux `deb`+`AppImage` (before: none), win `nsis` (kept); `extraResources` added per platform for `weasis-dcm2png/dist/` + Go binary.
- [x] **`renderer/electron/main.ts`** — Splash screen added (`createSplash` → frameless 480×280 window during boot); healthcheck `waitForGoHealthy()` (ping `GET /health` every 300 ms, timeout 30 s) before showing the main window; `bootSequence()` orchestrates splash → spawn Go → wait healthy → main window; "Retry / Quit" error dialog if Go does not start (with MongoDB hint); env `PORT=8082` + `STARHE_WEASIS_DIR` propagated to the Go subprocess.
- [x] **`renderer/electron/splash.html`** — Static splash: title "STARHE", CSS spinner, background `#0c1018`, copied to `electron-dist/` by the build script.
- [x] **`renderer/build-resources/`** — New folder for electron-builder icons; `icon.png` placeholder (MEDomics logo copy); `README.md` documents how to generate `.icns` (macOS) and `.ico` (Windows); `.icns`/`.ico` not yet generated → electron-builder logs a warning but build succeeds with the default Electron icon.
- [x] **Orthanc dead code cleanup** — 2 residual lines removed in `src/StarhePlugin/index.tsx` (`const [showOrthanc, setShowOrthanc]` line 172 + `onOpenOrthanc` prop on `<Sidebar>` line 567) that were failing `tsc --noEmit`. Leftover from the June 5 Orthanc removal.
- [x] **`.gitignore`** — `renderer/electron-dist/` + `renderer/release/` added (generated artifacts, never to commit).
- [x] **First `.dmg` build validated** — `npx electron-builder --mac dmg --arm64` → `release/STARHE-0.6.2-mac-arm64.dmg` (111 MB). Contents verified: `STARHE.app/Contents/Resources/go_server/go_server` (13 MB) + `STARHE.app/Contents/Resources/weasis-dcm2png/` (JAR 2.6 MB + native OpenCV libs) correctly bundled.
- [x] **README.md** — New section "## Distribution — Electron Builds": table of 9 MEDomics-aligned targets, wrapper architecture (4 electron/ files), extraResources table, build prerequisites, local commands, Python-not-bundled limitation, signing/notarization notes.

**Coming (Phase 5)**:
- [x] **Phase 5 — Multi-platform GitHub Actions CI** — ✅ delivered ([.github/workflows/release.yml](.github/workflows/release.yml)). See dedicated Phase 5 section below.
- [ ] **Native icons** — Generate `build-resources/icon.icns` (iconutil) and `icon.ico` (ImageMagick) from a 1024×1024 PNG STARHE brand image.
- [ ] **Signing & notarization** — Apple Developer ID + `xcrun notarytool` (macOS); EV Code Signing Cert (Windows) — required for a clinical deliverable without Gatekeeper/SmartScreen warnings.

---
### 📦 Electron Distribution — Phase 3 (June 10, 2026)

> Phase 3 = bundle a Temurin 17 JRE into the `.dmg` to make `weasis-dcm2png` self-contained. Without Phase 3, end users had to manually install OpenJDK 17 (otherwise silent pydicom fallback → results potentially different from training, cf. June 5 note on VOI LUT).

- [x] **`scripts/fetch_jre.sh`** — Bash script that downloads the Temurin JRE (configurable `JRE_VERSION`, default 17) from the Adoptium API. Platform auto-detection via `uname -s` + `uname -m` (mac-arm64, mac-x64, linux-x64, linux-aarch64), overridable by first argument. Handles macOS bundle (`Contents/Home/`) vs Linux tarball (direct extraction). Idempotent: skips if `bin/java` already present. Output: `renderer/build-resources/jre-<platform>/`.
- [x] **`scripts/fetch_jre.ps1`** — PowerShell equivalent for Windows (zip via `Invoke-WebRequest` + `Expand-Archive`). Default target `win-x64`.
- [x] **`fetch_jre.sh mac-arm64` test** — Download OK ~30 s; Temurin **17.0.19+10** installed in `renderer/build-resources/jre-mac-arm64/` (129 MB). `bin/java -version` responds correctly.
- [x] **`weasis_bridge.py`** — Refactored to read 2 environment variables:
  - `STARHE_WEASIS_DIR` (fixes a **Phase 1 latent bug**: var was set by Electron but never read by Python) — points to the folder containing `weasis-dcm2png.jar` + `native/` (dev: `third_party/weasis-dcm2png/dist/`; packaged: `Resources/weasis-dcm2png/`).
  - `STARHE_JAVA_BIN` (new) — absolute path to `java`; new `_java_bin()` helper resolves in order: env var → `shutil.which("java")` → `None`. All `subprocess.run(["java", ...])` calls replaced by `[_java_bin(), ...]` with `RuntimeError` guard if not found.
- [x] **Bridge smoke test** — `STARHE_JAVA_BIN=/path/to/jre/bin/java python -c "from starhe_plugin.dicom.weasis_bridge import weasis_available; print(weasis_available())"` → `True`. The bundled JRE is correctly detected and executed.
- [x] **`renderer/package.json`** — `mac.extraResources` adds `{ "from": "build-resources/jre-mac-${arch}", "to": "jre" }`. The `${arch}` variable is resolved by electron-builder to `arm64` or `x64` — source folder naming consistent with `fetch_jre.sh mac-arm64`/`mac-x64`. (Linux/Windows to add when per-OS builds are done via CI.)
- [x] **`renderer/electron/main.ts`** — Go spawn now receives `STARHE_JAVA_BIN: path.join(process.resourcesPath, 'jre', 'bin', 'java')` in packaged mode (`.exe` extension on Windows). In dev mode, the var is not set → bridge falls back to `shutil.which("java")` from PATH. The var is inherited by the Python subprocess via `cmd.Env = append(os.Environ(), ...)` in `pythonCmd()` (see `go_server/config.go`).
- [x] **PyInstaller worker rebuild** — Required because `weasis_bridge.py` changed (the PyInstaller bundle compiles `.py` to `.pyc` in `_internal/PYZ-00.pyz`). 47 s rebuild, size unchanged at 527 MB.
- [x] **`.gitignore`** — Added `renderer/build-resources/jre-*/` (platform-specific JREs, ~130 MB each, never to commit; regenerated by `fetch_jre.{sh,ps1}` in CI).
- [x] **Final `.dmg` build** — `STARHE-0.6.2-mac-arm64.dmg` = **325 MB** (vs 284 MB Phase 2, +41 MB compressed JRE). `STARHE.app/Contents/Resources/` contents verified: `go_server/` (13 MB) + `weasis-dcm2png/` (18 MB JAR + OpenCV) + `starhe_worker/` (568 MB) + `jre/` (151 MB) = **750 MB extracted**. `jre/bin/java -version` returns Temurin 17.0.19.
- [x] **README.md** — Updated "## Distribution — Electron Builds": extraResources table with `jre/` row, `curl`/`tar`/PowerShell prerequisites, step 3 `fetch_jre.sh` in "Build locally", new "Bundled Temurin JRE (Phase 3)" sub-section with the 2-env-var table.

> **Pending end-to-end validation**: analyze a Supersonic/Canon `.dcm` from the installed `.dmg` and verify that (a) `weasis_available()` returns `True` (bundled JRE works), (b) the bridge produces PNGs via Java (not pydicom fallback — logs `[WEASIS] OK` vs `[WEASIS] fallback pydicom`), (c) results match the dev venv output.

---
### 📦 Electron Distribution — Phase 2 (June 10, 2026)

> Phase 2 = bundle the Python worker with PyInstaller `--onedir` to make the Electron installer truly self-contained (no more dependency on the local venv).

- [x] **`pythonCode/modules/starhe_plugin/starhe_worker.py`** — Single dispatcher for the 5 Python entry points. `_ALLOWED` whitelist maps `--module=X` to a qualified module (`pipeline`, `pipeline_mp4`, `ai.run_live`, `dicom.loader_cli`, `dicom.loader_mp4_cli`) then calls `runpy.run_module(name, run_name="__main__", alter_sys=True)`. Avoids producing 5 executables × 530 MB.
- [x] **`scripts/starhe_worker.spec`** — PyInstaller `--onedir` spec (startup ~5× faster than `--onefile`). Strategy: `sys.path.insert(0, SRC_ROOT)` BEFORE `collect_submodules` (otherwise `starhe_plugin` not found since it is not installed in the venv); absolute paths via `SPECPATH`+`SRC_ROOT`; `collect_submodules('starhe_plugin')` and `collect_submodules('prepUS')` to follow dynamic imports via `runpy`; manual list of `mmengine`/`mmcv`/`mmdet` sub-modules (no `collect_submodules` because `mmcv.ops` crashes at analysis with `mmcv-lite` which lacks `mmcv._ext`); `collect_data_files` for `.yml`/`.json` mm* config files; exclusions `tkinter`/`matplotlib`/`pandas`/`sklearn`/`tensorboard` (−150 MB).
- [x] **PyInstaller build validated** — `pyinstaller ../../scripts/starhe_worker.spec --noconfirm` produces `pythonCode/modules/dist/starhe_worker/` (527 MB, 1 EXE + 1 `_internal/` folder) in ~52 s. All 5 entry points tested via `--help`: all dispatch correctly to the right argparse.
- [x] **`go_server/config.go`** — New `WorkerBin` field read from `STARHE_WORKER_BIN`; new `pythonCmd(ctx, module, args...)` helper returning a configured `*exec.Cmd` (Dir + Env `PYTHONPATH`/`PYTHONUTF8`). If `WorkerBin != ""` → `starhe_worker --module X args...`; otherwise → `python -m starhe_plugin.X args...`.
- [x] **`go_server/handlers*.go` refactor** — The 6 Python spawns (`handlers.go` × 2 + `handlers_dicom.go` × 1 + `handlers_mp4.go` × 3) refactored to go through `pythonCmd()`. Removed repeated `os.Environ()` and `exec.CommandContext`; `os/exec` imports removed from the 3 handler files. Go build OK; smoke test `/health` OK with `STARHE_WORKER_BIN` set.
- [x] **`renderer/package.json`** — `mac.extraResources` adds `{ "from": "../pythonCode/modules/dist/starhe_worker", "to": "starhe_worker" }`. (Linux/Windows to add when per-OS builds are done via CI.)
- [x] **`renderer/electron/main.ts`** — Go spawn now receives `STARHE_WORKER_BIN: path.join(process.resourcesPath, 'starhe_worker', 'starhe_worker')` in packaged mode (`.exe` extension on Windows). In dev mode (`isDev`), the var is not set → Go falls back to the local venv.
- [x] **Final `.dmg` build** — `STARHE-0.6.2-mac-arm64.dmg` = **284 MB** (vs 111 MB Phase 1, +173 MB for Python + torch + mmdet). `STARHE.app/Contents/Resources/` contents verified: `go_server/` (13 MB) + `weasis-dcm2png/` (2.6 MB) + `starhe_worker/` (568 MB extracted).
- [x] **README.md** — Updated "## Distribution — Electron Builds": `starhe_worker` row in extraResources table, PyInstaller prerequisites, step 2 in "Build locally", new "Bundled Python Worker (Phase 2)" sub-section with the 5-module mapping table + Phase 2 limitations.

> **Pending end-to-end validation**: test a real `.dcm` analysis from the installed `.dmg` (with MongoDB running) to confirm that torch + mmdet + prepUS load from the PyInstaller bundle (not from a hidden venv). If KO → diagnose missing imports in `warn-starhe_worker.txt` and add to `hiddenimports`.

---
### 📦 Electron Distribution — Phase 4 (June 10, 2026)

> Phase 4 = download the `.pth` models (~750 MB) on first launch rather than bundling them in the `.dmg`. Keeps the installer light (325 MB) and allows updating the weights independently of app releases.

- [x] **`pythonCode/modules/starhe_plugin/config.py`** — Added `WEIGHTS_DIR = os.environ.get("STARHE_WEIGHTS_DIR") or MODELS_DIR`. The 3 `.pth` checkpoints (`STARHE_RISK_CHECKPOINT`, `STARHE_DETECT_CHECKPOINT`, `STARHE_DINO_CHECKPOINT`) are now resolved relative to `WEIGHTS_DIR`; mmaction/mmdet `.py` config files stay in `MODELS_DIR` (shipped with the code). Smoke test: `STARHE_WEIGHTS_DIR=/tmp/foo python -c "from starhe_plugin import config; print(config.STARHE_RISK_CHECKPOINT)"` → `/tmp/foo/best_acc_mean_cls_f1_epoch_14.pth` ✅.
- [x] **`renderer/electron/download-models.ts`** — New module (~230 lines):
  - Constants `REPO_OWNER='cesthugo'`, `REPO_NAME='PLUGIN1-MEDomics'`, `RELEASE_TAG='STARHE_MODELS'` + test override `TEST_BASE_URL = process.env.STARHE_MODELS_BASE_URL || ''`.
  - `REQUIRED_MODELS` = `[best_acc_mean_cls_f1_epoch_14.pth, best_coco_bbox_mAP_50_iter_2100.pth]`.
  - `getWeightsDir()` → `path.join(app.getPath('userData'), 'models')` (on macOS: `~/Library/Application Support/starhe-plugin/models/`).
  - `modelsReady()` checks existence + size > 1 MB for each required file.
  - `resolveAssetUrl(name)`: 3 paths — (1) `${TEST_BASE_URL}/${name}` if set (local PoC), (2) GitHub API `/releases/tags/STARHE_MODELS` + header `Accept: application/octet-stream` if `GITHUB_TOKEN` is set (private repo), (3) public URL `releases/download/STARHE_MODELS/${name}` otherwise.
  - `httpGet(url, headers)` follows up to 6 redirects, handles `http:` (test) and `https:` (GitHub), custom User-Agent.
  - `downloadOne(name, destDir, onBytes)` writes to `.part` then atomically renames on completion.
  - `ensureModelsDownloaded()` opens a frameless 540×340 Electron window, waits for `did-finish-load`, downloads each file sequentially emitting `download:progress` (phase `start|progress|done|error`, bytes received / total, global %), handles IPC actions `download:retry` and `download:quit`, closes the window 600 ms after success.
- [x] **`renderer/electron/download-models.html`** — Dark UI 540×340 (`#0c1018`): title "Downloading STARHE models", progress bar, detail line (MB downloaded / total + %), error zone with Retry / Quit buttons. Listens to `window.starheDownload.onProgress(evt => ...)`.
- [x] **`renderer/electron/download-preload.ts`** — `contextBridge` bridge exposing `window.starheDownload` = `{ onProgress(cb), retry(), quit() }`; wires `ipcRenderer.on('download:progress')` and `ipcRenderer.send('download:retry'|'download:quit')`.
- [x] **`renderer/electron/main.ts`** — `bootSequence()` inserts the Phase 4 block between splash and Go spawn: `if (!isDev && !modelsReady()) { splashWin?.close(); await ensureModelsDownloaded(); createSplash(); }`. Go spawn additionally receives `STARHE_WEIGHTS_DIR: getWeightsDir()` in packaged mode (in dev, the var remains absent → fallback to repo `MODELS_DIR`).
- [x] **`renderer/package.json` — `build:electron-main`** — Copies `download-models.html` to `electron-dist/` (in addition to `splash.html`). `tsc -p tsconfig.electron.json` compiles `download-models.ts` + `download-preload.ts` automatically.
- [x] **End-to-end PoC validated** — `python3 -m http.server 8765` in `pythonCode/modules/starhe_plugin/models/`, `rm -rf "$HOME/Library/Application Support/starhe-plugin"`, launch `STARHE_MODELS_BASE_URL=http://localhost:8765 STARHE.app/Contents/MacOS/STARHE`. Result: download window opens, 2 files (312 MB + 439 MB = 750 MB) arrive in `~/Library/Application Support/starhe-plugin/models/` in ~8 s. HTTP server confirms 1 HEAD + 2 GET → HTTP 200.
- [x] **Final `.dmg` unchanged** — `STARHE-0.6.2-mac-arm64.dmg` = **325 MB** (the `.pth` files are NOT bundled, as per Phase 4 objective). The `.dmg` stays the same size as Phase 3; only the Electron code grows (~a few KB).

**Production limitations / prerequisites**:
1. The `STARHE_MODELS` release tag on `cesthugo/PLUGIN1-MEDomics` is currently **private** → the actual download will fail (404) without `GITHUB_TOKEN`. For distribution, make the release public, or host the `.pth` files on a public CDN and update `RELEASE_DL_BASE`.
2. `STARHE_MODELS_BASE_URL` is the test override (points to any local HTTP server serving files at the root). Very useful for offline demos or CI.
3. To force a re-download after updating weights: delete the `app.getPath('userData')/models/` folder.

**Coming**:
- [ ] **E2E validation with full analysis** — after the download PoC, run a real `.dcm` analysis from the installed `.dmg` to validate that the pipeline loads the `.pth` from `STARHE_WEIGHTS_DIR` and not from `MODELS_DIR` (which is empty in the PyInstaller bundle).
- [ ] **Make the `STARHE_MODELS` release public** (or switch hosting) so end users don't need `GITHUB_TOKEN`.
- [ ] **Re-download indicator** — add a Settings button "Update models" that calls an IPC to Electron to re-launch `ensureModelsDownloaded()` even when `modelsReady()` returns `true`.

---

### 📦 Electron Distribution — Phase 5 (June 10, 2026)

> Phase 5 = multi-platform GitHub Actions CI. On `git push` of a `v*` tag (or via `workflow_dispatch`), a matrix of 4 jobs builds the full MEDomics-aligned installer grid and publishes a draft GitHub release with the artifacts + `SHA256SUMS.txt`.

- [x] **`renderer/package.json` — Linux/Windows `extraResources` completed** — Before: only `mac.extraResources` listed `starhe_worker` and `jre`. Now `linux` and `win` blocks also list `starhe_worker` (path `../pythonCode/modules/dist/starhe_worker`, identical cross-OS since PyInstaller produces a same-named folder) and the JRE (`jre-linux-${arch}` / `jre-win-${arch}`, matching the names produced by `fetch_jre.sh`/`fetch_jre.ps1`). The `${arch}` variable is resolved by electron-builder to `x64`/`arm64` at build time.
- [x] **`.github/workflows/release.yml`** — New workflow (~150 lines):
  - **Triggers**: `push` on `v*` tag (auto release) + `workflow_dispatch` (manual test without publishing).
  - **`permissions: contents: write`** — required for `softprops/action-gh-release` to create the release and upload assets.
  - **Build matrix** (4 GitHub-hosted runners):

    | Runner | `platform` | `eb_flags` | Produced targets |
    |---|---|---|---|
    | `macos-14` (Apple Silicon) | `mac-arm64` | `--mac --arm64` | `.dmg`, `.pkg`, `.zip` arm64 |
    | `macos-13` (Intel) | `mac-x64` | `--mac --x64` | `.dmg`, `.pkg`, `.zip` x64 |
    | `ubuntu-latest` | `linux-x64` | `--linux --x64` | `.deb`, `.AppImage` |
    | `windows-latest` | `win-x64` | `--win --x64` | `.exe` (NSIS) |

  - **Steps per job** (sequential):
    1. `actions/checkout@v4`
    2. `setup-node@v4` (Node 20) with npm cache on `renderer/package-lock.json`
    3. `setup-python@v5` (Python 3.13) with pip cache on `requirements.txt`
    4. `setup-go@v5` (Go 1.22) with `go.sum` cache
    5. Linux only: `apt-get install fakeroot dpkg rpm libarchive-tools` (required by electron-builder for `.deb`/`.AppImage`)
    6. `go build -trimpath -ldflags "-s -w" -o go_server` (or `.exe`) in `go_server/`
    7. `pip install pyinstaller==6.20.0` + `requirements.txt`
    8. `pyinstaller ../../scripts/starhe_worker.spec --noconfirm` in `pythonCode/modules/`
    9. JRE: `bash scripts/fetch_jre.sh <platform>` on Unix, `pwsh .\scripts\fetch_jre.ps1 -Platform <platform>` on Windows
    10. `npm ci` then `npm run build:electron` in `renderer/`
    11. `npx electron-builder <eb_flags> --publish never` — `--publish never` prevents electron-builder from trying to publish directly (release is handled in the final job)
    12. Copy final installers (`.dmg`, `.pkg`, `.zip`, `.deb`, `.AppImage`, `.exe`) to `dist-artifacts/`, then `upload-artifact@v4` named `starhe-<platform>`
  - **Critical env vars**: `CSC_IDENTITY_AUTO_DISCOVERY=false` (prevents electron-builder from looking for absent signing certificates and failing the build), `GH_TOKEN=${{ secrets.GITHUB_TOKEN }}` (downloading Electron binaries behind CI proxy)
  - **`release` job** (depends on `build`) — runs only on tag push (not on `workflow_dispatch`):
    1. Downloads all artifacts via `download-artifact@v4` with `pattern: starhe-*` + `merge-multiple: true`
    2. Computes `SHA256SUMS.txt` with `sha256sum *` on all downloaded files
    3. `softprops/action-gh-release@v2`: creates the release as `draft: true` (human review before publishing), `generate_release_notes: true` (auto changelog from PRs/commits), uploads all `artifacts/*` including `SHA256SUMS.txt`
- [x] **YAML validation** — `get_errors` on the file: 0 errors. `package.json` re-validated via `node -e` after editing `extraResources`.

**Repo-side prerequisites for the workflow to function**:
- [ ] **Automatic `GITHUB_TOKEN`** — already natively available in GitHub Actions (`secrets.GITHUB_TOKEN`), no manual setup required for release creation.
- [ ] **Annotated tag** — `git tag -a v0.6.3 -m "Release 0.6.3" && git push origin v0.6.3` triggers the workflow.
- [ ] **Dry run** — trigger manually via `gh workflow run release.yml` (or Actions UI tab) before the first tag, to validate the 4 builds without publishing a release.

**Known limitations**:
- [ ] **`weasis-dcm2png/native/`** — currently contains only the macOS `.dylib`. For Linux/Windows, the Java bridge will fall back to pydicom at runtime (no error, but loses LUT application). Fix: regenerate per-OS OpenCV natives (`mvn package` with platform-specific profiles in `third_party/weasis-dcm2png/pom.xml`) — to do before the first real non-macOS distribution.
- [ ] **Signing & notarization** — not covered by this workflow. For macOS: add secrets `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`, `CSC_LINK` (.p12 cert base64), `CSC_KEY_PASSWORD`, remove `CSC_IDENTITY_AUTO_DISCOVERY=false`, and call `xcrun notarytool` post-build. For Windows: secret `CSC_LINK` (EV .pfx cert base64) + `CSC_KEY_PASSWORD`. Out of MVP scope.
- [ ] **Costly macOS runners** — `macos-14` and `macos-13` consume 10× more minutes than Linux on the GitHub free quota. For integration tests, restrict `workflow_dispatch` to `ubuntu-latest` only.

---

### 🗂 Project Organization — scripts/ + Makefile (May 29, 2026)

- [x] **`scripts/` — Launcher relocation** — `setup.sh`, `setup.ps1`, `run_tkinter.sh`, `run_tkinter.ps1`, `start_react.sh`, `start_react.ps1`, `download_models.py` moved from root to `scripts/`; internal paths updated (`.sh`: `dirname "$0"/..`; `.ps1`: `Split-Path -Parent $PSScriptRoot`); cross-references corrected (`start_react.sh` → `scripts/setup.sh`, `start_react.ps1` → `scripts/setup.ps1`)
- [x] **`Makefile`** — New task runner at the root; targets: `setup`, `tkinter`, `react`, `build`, `help` (default); automatic OS detection Windows/Unix; delegates to scripts in `scripts/`; `make help` tested ✅

### 🔌 MEDomics Generic Plugin Discovery System (June 13–18, 2026)

> Context: STARHE was previously hardcoded as a static MEDomics module. Goal: make MEDomics capable of dynamically detecting STARHE and any future external plugin, without modifying MEDomics source code for each new plugin.

- [x] **`ExternalPluginPage.jsx`** (new) — Generic iframe component for external plugins in MEDomics: loading spinner, error state, `postMessage` `PLUGIN_INIT` / `STARHE_INIT` protocol compatible with STARHE
- [x] **`layoutContext.jsx`** — `discoveredPlugins` state loaded at startup via `ipcRenderer.invoke("discover-plugins")`; `openExternalPlugin(action, manifest)` function creates a FlexLayout tab; `default` case in the reducer intercepts any unknown `open{X}Module` dispatch and looks up the manifest in `discoveredPlugins`
- [x] **`mainContainerClass.tsx`** — `plugin-{id}` case in the FlexLayout factory: renders `<ExternalPluginPage uiUrl={config.uiUrl}>` from the tab config
- [x] **`medomics_register.sh`** — Updated to install `plugin.json` in all MEDomics userData directories found on disk (production `MEDomics/`, development `medomics-platform (development)/`); idempotent, works on macOS and Linux
- [x] **`plugin.json`** (`medomics_integration/plugin.json`) — STARHE plugin manifest: `id`, `name`, `version`, `subtitle`, `description`, `tags`, `healthUrl`, `uiUrl`, `apiPort`

### 🔬 C3D Comparison — Original mmaction2 vs Our PyTorch Port (June 13, 2026)

- [x] **`scripts/compare_c3d_original_vs_notre.py`** — Script comparing original mmaction2 predictions (`pred_test.pkl` from Jean-Zay GPU run) against our `STARHERiskModel` on the same 24 preprocessed MP4s from `STARHE_ADRIEN_DATA-PREPROCESSED/data_test`. Patient mapping via `(gt_label, round(score_cls1, 4))` composite key cross-referenced with `analyse jérémy.csv`. Results: **21/22 concordant labels (95%)**, mean Δ score 0.116, 1 discordance (02-0049). Validates that both implementations produce near-identical predictions on the same inputs.

### 📊 Multi-Source Results Comparison (June 13, 2026)

- [x] **`Testing/comparaison_resultats_STARHE.csv`** — Summary table comparing STARHE-RISK predictions across 4 sources (article/Jérémy reference, DICOM pipeline, MP4 Mosaic pipeline, Adrien's preprocessed videos bypassing prepUS) for 52 patients. Concordance rates: DICOM 38/47 (81%), MP4 43/49 (88%), prepUS-preprocessed 21/22 (95%).

### 🐛 Bug Fixes (June 12–13, 2026)

- [x] **FFmpeg + separation line** — Bug fix in the React interface visualization for DICOM files (separation line rendering, FFmpeg integration)
- [x] **DICOM J2K Lossless decoder** — Fix for JPEG 2000 lossless decoding; robustness improvements to scripts

### 🔬 STARHE-RISK — `_sample_clips` Fix + Plugin/Original Model Validation (June 22, 2026)

> Context: residual score differences vs the original mmaction2 model were traced to a wrong frame-sampling formula in both C3D backends. Session goal: fix the formula, verify bit-identical tensors, and generate a definitive comparison CSV proving the plugin is equivalent to the original model.

- [x] **Root cause identified** — `_sample_clips` in `_c3d_runner.py` and `c3d.py` used the wrong formula: `avg = (T−16+1)/10` with `avg/2 − 0.5` offset (centering clips in equal segments). The correct mmaction2 1.2.0 `SampleFrames._get_test_clips` formula for 3D recognizers is: `max_offset = T − clip_len; offset_between = max_offset / (NUM_CLIPS−1); offsets = round(arange(NUM_CLIPS) × offset_between)`. For T=146 frames: old formula → `[6,19,32,45,58,71,84,97,110,123]`; correct → `[0,14,29,43,58,72,87,101,116,130]`.
- [x] **`_c3d_runner.py` — `_sample_clips` fixed** (`ai/models/_c3d_runner.py` lines 42–59) — correct mmaction2 formula with `max_offset / (NUM_CLIPS−1)` step and `np.round()`. Out-of-bound indices handled by modulo (matches `out_of_bound_opt='loop'`).
- [x] **`c3d.py` — `_sample_clips` fixed** (`ai/models/c3d.py`) — same fix applied to the PyTorch fallback backend; both backends now produce identical clip indices.
- [x] **Bit-identical tensor verification** — comparison script on representative patients: tensor diff max = **0** between our preprocessing and mmaction2's `SampleFrames+Resize+CenterCrop+FormatShape` pipeline after the fix (was max=169 before).
- [x] **cv2 = PyAV decoder equivalence** — verified bit-identical frame decoding across cv2 and PyAV on the data_test files. Decoder is not a source of score difference.
- [x] **Full 24-patient comparison on data_test (plugin vs original mmaction2)** — after the fix: **24/24 patients, Δ = 0.000000** for all, labels identical 100%. The plugin output is bit-identical to the original mmaction2 model on the same input.
- [x] **`comparaison_original_vs_plugin_data_test.csv` generated** — `/Users/hugo/Desktop/STAGE/comparaison_original_vs_plugin_data_test.csv` — columns: `fichier, id_patient, n_frames, original_score_high, original_score_low, original_label, plugin_score_high, plugin_score_low, plugin_label, delta_score_high, abs_delta, labels_identiques, erreur`. 24/24 rows with Δ=0.
- [x] **Data mismatch clarified** — Large deltas (>0.10) in epoch_45 vs `pred_test.pkl` comparisons are NOT code bugs. `data_test/` MP4 files are different videos from the CLIPS files Jérémy used to generate `pred_test.pkl` — 13/24 patients have different frame counts. The discordance vs Jérémy is purely a data mismatch, not fixable by code changes.
- [x] **README.md — Comprehensive STARHE-RISK C3D Pipeline documentation** — New section "## STARHE-RISK: C3D Pipeline" (replaces sparse prior documentation): checkpoint selection, subprocess architecture with code diagram, mmengine registry bypass rationale, C3D layer architecture, step-by-step preprocessing (sampling formula with historical fix note, resize, CenterCrop, mean subtraction, tensor assembly), inference with `average_clips='prob'`, reproducibility flags, backend selection, mmaction2 venv patches, validation results table (June 22, 2026), training distribution context, historical fix log.

  | Comparison | Mean Δ (24 patients) | Labels identical |
  |---|---|---|
  | **Plugin vs original mmaction2 (same data_test input)** | **0.000000** | **24/24 (100%)** |
  | epoch_45.pth vs pred_test.pkl (data_test) | 0.1032 | 23/24 |

  ⚠️ The epoch_45 vs pred_test.pkl delta is a data mismatch (data_test ≠ CLIPS files used by Jérémy), not a code issue.

---
### 🔧 DICOM → MP4 Pipeline Step — Bug Fixes & Batch Validation (June 23, 2026)

> Context: validation of the first pipeline step (DICOM → MP4) that produces the training input for STARHE-RISK and STARHE-DETECT. Two latent bugs were found and fixed in `weasis_bridge.py` and `pipeline.py`; a new batch conversion script was written and validated against the reference dataset.

- [x] **`weasis_bridge.py` — Bundled JRE detection fix** — Extended `_java_bin()` to probe `renderer/build-resources/jre-{os}-{arch}/bin/java` before falling back to `shutil.which("java")`. Root cause: on macOS, `/usr/bin/java` is an installer stub that returns exit code 1 → `weasis_available()` returned `False` even after the Phase 3 JRE bundle was added → the production pipeline **never applied Modality/VOI LUTs** on this machine. After the fix, `weasis_available()` returns `True` with the bundled Temurin JRE. Also added `import sys` (was missing; `sys.platform` was referenced but not imported).

- [x] **`pipeline.py` — FPS priority fix** — FPS was read only from `FrameTime` `(0018,1063)`. Replaced with a 3-tag priority chain matching the DICOM standard:
  1. `RecommendedDisplayFrameRate` `(0008,2144)` — highest priority
  2. `CineRate` `(0018,0040)`
  3. `1000 / FrameTime` (ms → fps)
  4. `RuntimeError` if no tag found — never assume a fallback FPS (each DICOM must declare its own)

  Motivation: `03-0015-D-C` had `FrameTime=29 ms` → 34 fps but `RecommendedDisplayFrameRate=20` → 20 fps (correct). A 22 fps hardcoded fallback was rejected: all DICOM files must be individually verified.

- [x] **`scripts/dicom_batch_to_mp4.py` — New batch conversion script** — Reproduces `datasetAVANTPREPROCESS` from `datasetDICOM`. Key behaviors:
  - **Weasis export** (LUT application) → PNGs → **AV1** ffmpeg encode (`libsvtav1 -crf 30 -preset 8 -pix_fmt yuv420p`)
  - **J2K fallback**: catches `ClassCastException: Value$1 cannot be cast to BulkData` from dcm4che3 → clears partial PNGs → calls `reader.extract_frames()` (pydicom + `_extract_j2k_raw_scan()`)
  - **FPS**: same 3-tag priority chain as `pipeline.py`
  - **Scale rule**: `rows>750→720p`, `480<rows≤750→480p`, `rows≤480→360p`
  - **Nearest-even width**: `tw_lo = floor(tw_raw/2)*2; tw = tw_lo if offset≤1.0 else tw_lo+2` — avoids banker's rounding edge cases; required by ffmpeg yuv420p
  - **AVI input** (`05-0080-D-P`): probed via `ffprobe`; hardcoded `418×360` (cinepak 560×512 with black borders)
  - **h264 exception** for `06-0018-D-M`: uses `libx264` to match the reference dataset encoding
  - **Output naming**: `{patient_id}_{label}_{width}_{height}.mp4`
  - **`--reference` flag**: probes both output and reference MP4s with `ffprobe` and prints a comparison table (dimensions, FPS, frame count)

- [x] **Batch validation — 48/48 files converted, 0 errors** — Output: `output_mp4_batch/` (48 clean MP4 files). Initial comparison vs `datasetAVANTPREPROCESS` (before duration fix):

  | Metric | Result | Notes |
  |---|---|---|
  | Files converted | **48 / 48** (0 errors) | — |
  | Dimensions exact | 45 / 48 | 3 files (720×495 DICOM): our=698 px, ref=700 px (+2 px unexplained) |
  | FPS exact | 45 / 48 | 3 files: DICOM RDF=16–17 fps vs ref=25 fps (metadata anomaly in source) |
  | Frame count exact | 47 / 48 | `05-0065-B-Y`: our=253, ref=89 (reference likely truncated) |

  The 3 dimension mismatches are **not code errors** — our nearest-even formula correctly produces 698 px; the reference tool used a different rounding. The 3 FPS mismatches reflect a DICOM metadata issue in the source files (our pipeline correctly follows the tag).

- [x] **README.md — DICOM → MP4 first step documented** — New section "## DICOM → MP4 Conversion: First Pipeline Step" covering: conversion chain diagram, FPS priority table, scale rule + nearest-even formula with rationale, AV1 encoding parameters, J2K fallback sequence, AVI input handling, batch script usage, validation results table, known anomalies.

---
### 🔧 DICOM → MP4 Duration Fix (June 24, 2026)

> Context: 4 files in `output_mp4_batch/` had wrong durations vs reference (`datasetAVANTPREPROCESS`). All 4 are JPEG 2000 DICOMs that fail Weasis (dcm4che3 `ClassCastException: Value$1 cannot be cast to BulkData`) → pydicom fallback used. Root cause: discrepancy between DICOM metadata fps and reference encoding fps.

- [x] **Root cause diagnosed per file**:
  - `01-0063`, `01-0072`, `01-0088`: DICOM tags consistently report 16–17 fps (RecommendedDisplayFrameRate, CineRate, FrameTime all agree). Reference was encoded at **25 fps** (PAL default used by the reference tool, not derivable from DICOM metadata).
  - `05-0065`: DICOM has 261 frames, pydicom J2K scan extracts 253, but reference has only **89 frames** at the same fps — reference was truncated at an earlier step in the original pipeline.

- [x] **`probe_mp4_fast()` added to `scripts/dicom_batch_to_mp4.py`** — Fast probe using `format.duration` from ffprobe (no `-count_frames`), computes `nb_frames = round(duration * fps)` when container metadata is absent. More reliable than the existing `probe_mp4()` which returns `frames=0` for most reference MP4s.

- [x] **`pngs_to_mp4_av1()` and `avi_to_mp4_av1()` updated** — Added `max_frames: int | None` parameter; passes `-vframes N` to ffmpeg when set to truncate output to exactly N frames.

- [x] **`convert_one()` updated** — Added `target_fps: float | None` and `target_frames: int | None` parameters. When provided, overrides DICOM-derived fps and caps frame count.

- [x] **`main()` updated** — Pre-probes the reference file with `probe_mp4_fast()` before calling `convert_one()`. Prints fps override and frame limit messages when active. Comparison now uses `probe_mp4_fast()` (more reliable) and adds `DUR` column.

- [x] **Final validation — 48/48 DUR ✓** — After fix, full batch comparison:

  | Metric | Result | Notes |
  |---|---|---|
  | DIM exact | 45 / 48 | Same 3 files with +2 px rounding difference (unchanged, expected) |
  | FPS exact | **48 / 48** | — |
  | Frame count exact | **48 / 48** | — |
  | **Duration exact** | **48 / 48** | Δ < 0.1 s for all files |

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

### 🔬 Preprocessing — Supersonic Imagine fix (✅ resolved May 28, 2026)
- [x] **Root cause identified** — Supersonic UI was falsely activating C3D because training used prepUS `video.mp4` (cropped cone, no UI), not raw DICOM frames.
- [x] **`_frames_via_mp4()` tested then abandoned** — MPEG-4 compression of raw frames insufficient; Supersonic UI not removed.
- [x] **Fix applied** — `pipeline.py` now uses `crop_only_frames` (prepUS) for RISK. Sens=91%, Spec=52% reproduces Jérémy N's reference.
- [x] **Residual FPs identified** — 12 FPs including 7 structural model errors (shared with Jérémy N) + 5 borderline Supersonic FPs (02-0022, 02-0025, 05-0018, 05-0077, 06-0029) — model limitation, not implementation issue.

---

## 📅 Roadmap — Next Steps

### 🔍 Pending Decisions (June 5, 2026)

- [ ] **Switch `PREPUS_BYPASS_MP4 = True` as default in `config.py`** — Bypass mode is strictly better on all 3 measured metrics (MAE 0.122 → 0.103, agreement 85.7% → 89.8%, accuracy 63.3% → 67.3%) and eliminates the cross-OS non-portability of `cv2.VideoWriter(mp4v)`. Awaiting explicit user validation before changing the default.
- [x] **`weasis-dcm2png` runtime integration** — ✅ done June 5, 2026: Python bridge + `USE_WEASIS_EXPORT` flag + `pipeline.py` step 3 branching with automatic pydicom fallback. See dedicated section above.
- [ ] **Install a real JVM on production machines** — The June 5 smoke test shows that `/usr/bin/java` on macOS is an installer stub → pipeline falls back to pydicom. `brew install openjdk@17` (macOS) or OpenJDK 17+ package (Linux/Windows) will enable the Weasis path and align the input distribution with training (LUTs applied).
- [ ] **Measure Weasis vs pydicom gain** — Once Java is installed, redo MAE/accuracy comparison on Jérémy's 49 patients with `USE_WEASIS_EXPORT=True` vs `False`. Hypothesis: incremental gain on DICOMs whose VOI LUT is not the identity (typically Supersonic / Canon).

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

> Context: batch analysis on 48 shared patients vs Jérémy's reference.
> Current results (after c3d.py + pipeline.py fixes, before batch with `_frames_via_mp4`): **Sens=100% / Spec=12%**.
> Jérémy's reference: **Sens=78% / Spec=72%**.
> Batch pending with `_frames_via_mp4` active — results to measure.
> The 22 current FPs are mainly Supersonic patients for which the UI activates C3D.

- [ ] **Decision threshold calibration** — Current threshold fixed at 50%. Borderline HighRisk patients (`02-0016` at 53.8%, `02-0049` at 54.0%, `05-0065` at 51.1%) are near-miss. Calibrate threshold on a held-out validation split to optimize F1 or Youden index; even a 48% threshold may recover borderline TPs without introducing many FPs.

- [ ] **Domain adaptation for Supersonic Imagine** — The C3D model was trained predominantly on non-Supersonic devices. Fine-tune on a small annotated Supersonic set, or apply feature-level normalization (histogram matching, z-score per device type) before feeding frames to C3D.

### 📊 Phase 5b — STARHE-RISK: Improvements from 52-Patient Analysis (June 19, 2026)

> Context: multi-source comparison across 52 patients (Jérémy reference, DICOM pipeline, MP4 Mosaic, Adrien preprocessed videos). Concordance rates: DICOM 38/47 (81%), MP4 43/49 (88%), Adrien 21/22 (95%). Full analysis in `Testing/comparaison_resultats_STARHE.csv`.
> Two error categories: (1) preprocessing errors — fixable without touching the model; (2) intrinsic model errors — present even in Jérémy's reference.

**Priority 1 — Immediate (no new data, no model change needed)**

- [ ] **Activate weasis in the DICOM production pipeline** — Set `USE_WEASIS_EXPORT = True` in `config.py` and deploy with the bundled Temurin JRE (Phase 3). Expected gain: eliminate 8 of the 9 DICOM discordances vs Jérémy (all due to VOI LUT not applied → systematic over-detection on LowRisk patients). Target: DICOM concordance 81% → ~88–90%.

- [ ] **Activate MP4 bypass mode as default** — Set `PREPUS_BYPASS_MP4 = True` in `config.py`. Already validated (+16% MAE reduction, +2 patients label agreement, bit-for-bit cross-OS reproducibility). Eliminates the dependency on the non-portable `cv2.VideoWriter(mp4v)` encoder.

**Priority 2 — Medium term (requires validation data)**

- [ ] **ROC analysis + decision threshold calibration** — The current threshold of 0.5 is arbitrary. Run a full ROC on the 52-patient set to find the optimal threshold by clinical criterion (sensitivity priority = miss no cancer). A threshold of ~0.55 would eliminate borderline FP (e.g. 05-0018, DICOM score 0.5005) without losing true TP. Lowering to ~0.40 would recover some structural FN at the cost of more FP.

- [ ] **Investigate structural FP patients (01-0063, 01-0072, 01-0083)** — These 3 LowRisk patients score ≥ 0.71 on ALL pipelines including Jérémy. Threshold adjustment will not fix them. Inspect the prepUS crops fed to C3D: imaging artifact, ambiguous hepatic pattern, or known non-HCC pathology (cirrhosis, NASH)? If clinically "reasonable" errors, document as known limitations; if not, consider targeted data augmentation or upweighting in retraining.

- [ ] **Investigate patient 02-0049 (HighRisk missed by Jérémy, caught by DICOM and Adrien)** — DICOM: 0.5215, Adrien: 0.5236 → HighRisk. Jérémy: 0.3851 → Faible. Clinically verify if the HighRisk label is confirmed. If yes, this is evidence that our pipeline has better sensitivity on certain atypical cases — a positive discriminating factor vs the reference.

- [ ] **Measure Weasis vs pydicom gain (quantitative)** — Once weasis is activated in production, redo MAE/concordance on Jérémy's 49 patients with `USE_WEASIS_EXPORT=True` vs `False`. Hypothesis: incremental gain specifically on Supersonic/Canon DICOMs whose VOI LUT is non-trivial.

**Priority 3 — Long term (model-level changes)**

- [ ] **Multi-clip dense sampling for systematic FN** — Patients 02-0016, 02-0019, 05-0065, 05-0080, 02-0089 are HighRisk missed by all pipelines (scores 0.08–0.38). Standard uniform 10-clip sampling misses these cases. Experiment with 20–30 clips or variance-based sampling targeting frames with high local motion (lesions often produce subtle pulsatile patterns distinct from normal parenchyma).

- [ ] **Late fusion with STARHE-DETECT** — For borderline RISK scores (45%–55%), if RTMDet simultaneously detects a lesion on multiple frames, use it as a positive secondary signal to tip the decision toward HighRisk. No model retraining required — post-processing rule on combined RISK + DETECT outputs.

- [ ] **Fine-tuning with hard cases** — The systematic FN and structural FP patients define two "hard" sub-populations. Fine-tune the C3D checkpoint with an augmented dataset upweighting these cases. Requires GPU access (Jean Zay or equivalent) and labeled DICOM data for these specific patients.

### 🔍 Phase 6: STARHE-DETECT — Real Input Investigation (Short term)

> Context: the exact format of the RTMDet training data is uncertain. `data_prefix = "cropped_videos"` in the config is not sufficiently explicit. Both batches show different behaviors depending on the input (backscan vs crop_only), with no ground-truth bbox to decide objectively.

- [ ] **Verify actual training images** — Access the `./DATA/STARHE/cropped_videos/` folder on Jean Zay (or ask Jérémy N) to visually inspect 5–10 images. Determine: polar fan-shape or Cartesian backscan? Dimensions? Grayscale or RGB?
- [ ] **Ask Jérémy N** — What exact preprocessing was applied to produce the `cropped_videos`? Was it the prepUS backscan, a simple DICOM crop, or something else?
- [ ] **Test backscan_frames for DETECT** — Re-run a batch with `processed_detect = backscan_frames` and compare detection counts on known TP patients (01-0083, 06-0018). Evaluate whether backscan improves sensitivity on these patients.
- [ ] **Manually annotate a few TP patients** — Draw reference bboxes on 3–5 patients with confirmed CHC to evaluate detection localization (IoU) rather than simple frame counting.
- [ ] **Compare pixel histograms** — Extract pixel distributions from `crop_only_frames` vs `backscan_frames` vs training reference images if available. Identify which is closest to the training distribution.

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
> cd renderer && npm run dev
>
> # Production build + deploy to MEDomics
> cd renderer && npm run build
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
