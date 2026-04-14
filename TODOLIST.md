# 📋 TODOLIST — STARHE Plugin / MEDomics
> Operational project logbook.  
> Last updated: **April 14, 2026**

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
- [x] **`config.py` thresholds**: `DETECT_SCORE_THRESHOLD=0.70`, `DETECT_EVERY_N=4`, `DETECT_BATCH_SIZE=4`

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

### 🔗 Go Server
- [x] **`go_server/main.go`** — Endpoints: GET /health, POST /starhe/analyze (SSE), GET/DELETE /starhe/results
- [x] **`go_server/config.go`** — MongoDB port `54017`, Python venv paths configurable via env vars
- [x] **`go_server/handlers.go`** — SSE streaming `GO_PRINT|` from Python

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

---

## 🚧 In-Progress Tasks

### 🐍 Python Backend
- [ ] **End-to-end pipeline tests** — Validate `run_pipeline()` with a real `.dcm` file on hepatic data
- [ ] **MEDomics integration E2E test** — Send a POST `starhe/analyze/` from the MEDomics frontend and verify the full flow (Go → run_starhe.py → pipeline.py → MongoDB → response)

### 🖼 Tkinter Prototype
- [ ] **Full workflow validation with Canon Aplio i700** — Load `A0000` → banner removal + mm calibration → prepUS → AI inference → results display + MongoDB cache
- [ ] **User feedback collection** — Identify UX adjustments before porting to React

### 🔌 MEDomics Integration
- [ ] **MEDomics frontend** — No React page exists yet to drive STARHE from the MEDomics interface
- [ ] **MEDDataObject** — Results are not yet encapsulated in a `MEDDataObject` (MEDomics standard format for patient data/results)
- [ ] **Cross-platform symlinks** — Unix symlinks do not work natively on Windows (require developer mode or admin rights). Consider an installation script with copy as fallback.

---

## 📅 Roadmap — Next Steps

### 🔬 Phase 1: Backend Validation (Short term)

- [ ] **Unit test development**
  - `reader.py`: loading, frame count, array shapes
  - `anonymizer.py`: verify that all 15 tags are properly erased/hashed
  - `prepus_bridge.py`: validate crop + backscan on a reference DICOM
  - `mongo_client.py`: round-trip test save/find/delete
  - *Approach: create `pythonCode/modules/starhe_plugin/tests/` with `pytest`*

- [ ] **Phase 2 Optimization: GPU**
  - Configure the RTMDet runner to use CUDA if available (`--device cuda`)
  - Estimated gain: ×10–20 on the detection part (RTX 30/40: ~15–30ms/frame)

### 🔀 Phase 2: Go Server Integration (Medium term) — ✅ Partially completed

- [x] **Go blueprint for MEDomics** — `starhe_blueprint.go` with `AddHandleFunc()`, `analyze/` and `progress/` routes
- [x] **GoExecutionScript adapter** — `run_starhe.py` translates the GO_PRINT → MEDomics protocol

- [ ] **Real-time progress manager**
  - Wire `go_progress()` events from Python to the frontend via SSE

- [ ] **Error handling and timeouts**
  - Configurable timeout for AI inference
  - Semantic HTTP error codes with structured JSON messages

### ⚙ Phase 3: React UI Port (Long term)

- [ ] **`<DicomLoader />` component** — Upload and validation of a `.dcm` file
- [ ] **`<FrameViewer />` component** — Frame visualization, navigation, crop/backscan toggle
- [ ] **`<InferenceResults />` component** — STARHE-RISK score, bboxes, clickable detected frame list
- [ ] **`<AnalysisConsole />` component** — Real-time logs (SSE)
- [ ] **Integration into the MEDomics navigation system**
- [ ] **MEDDataObject encapsulation** — Produce and consume MEDDataObjects to integrate into existing MEDomics workflows

### 🧪 Phase 4: Testing & Deployment (Long term)

- [ ] **End-to-end integration tests** — React frontend → Go → Python → MongoDB
- [ ] **Go API documentation** — Swagger / OpenAPI
- [ ] **Plugin packaging** — MEDomics extension system compatibility
- [ ] **Automated installation script** — Automate blueprint copy, symlink creation (or copy on Windows), and `main.go` patching

---

## 📝 Key Technical Procedures

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
> Each Python stdout line is prefixed with `GO_PRINT:` followed by JSON.
> Parse on the Go side with `bufio.Scanner` + `json.Unmarshal` — relay via SSE.

---

*🔖 This file is maintained manually. Update as sprints progress.*
