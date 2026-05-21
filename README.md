# STARHE Plugin — MEDomics

> **STARHE** = **S**tratification of risk and de**T**ection of **H**epatocellular carcinoma by **E**chography.  
> Python/Go extension of the [MEDomics](https://medomicslab.gitbook.io/medomics-docs) platform.

*Version `0.5.0` — Last updated: 11 mai 2026*

---

## Overview

The plug-in analyzes abdominal ultrasound DICOM cine-clips to screen for hepatocellular carcinoma (HCC). It operates in **four modes**:

| Mode | Description |
|---|---|
| **React UI (standalone)** | React 18 / TypeScript frontend (`react_ui/`) built with Vite, served by a standalone Go server (`go_server/`). Full DICOM viewer, AI pipeline, multi-tab, live analysis. **Current primary UI.** |
| **Tkinter prototype** | Legacy Tkinter UI (`ui/prototype_tkinter.py`). Used for early validation before porting to React. Launched via `run_tkinter.sh`. |
| **MEDomics Integrated** | Integrates into the MEDomics platform as a *Standard Plugin*. An adapter (`run_starhe.py`) translates the `GO_PRINT|…` protocol to the MEDomics protocol (`progress*_*` / `response-ready*_*`). A Go blueprint (`starhe_blueprint.go`) registers routes in the MEDomics server. |
| **Live Streaming** | Real-time frame-by-frame inference on a live ultrasound feed. The `LivePipeline` (`ai/live_pipeline.py`) processes incoming frames in a background thread. Three input sources: C-STORE DICOM (pynetdicom SCP), local folder watcher, USB HDMI capture card. Live modal available in the React UI. |

Two AI models are used:

| Model | Architecture | Task | Checkpoint |
|---|---|---|---|
| **STARHE-RISK** | C3D (3D-CNN, pure PyTorch) | Binary classification: low / high HCC risk | `models/best_acc_mean_cls_f1_epoch_14.pth` |
| **STARHE-DETECT** | RTMDet (mmdet) or DINO-DETR | Detection and localization of hepatic lesions | `models/best_coco_bbox_mAP_50_iter_2100.pth` |

---

## Prerequisites

| Tool | Minimum Version | Notes |
|---|---|---|
| Python | 3.13 | tkinter included; 3.14 incompatible (tkinter broken). On macOS Homebrew: `brew install python@3.13 python-tk@3.13` |
| MongoDB | 4.x+ | Local service on port **54017** (non-standard) |
| Go | 1.21+ | Required for the REST/SSE server |
| Node.js | 18+ | Required for the React UI (`react_ui/`) |
| CUDA (optional) | 11.8+ | GPU inference; CPU used if absent |

> **AI model weights**: the `.pth` checkpoint files (~200 MB each) are **not included** in the repository. They are downloaded automatically by `run_tkinter.sh` / `run_tkinter.ps1` from the [GitHub Release STARHE_MODELS](https://github.com/cesthugo/PLUGIN1-MEDomics/releases/tag/STARHE_MODELS). To download them manually: `python download_models.py`.
>
> **Private repo — GitHub token required**: since this repository is private, downloading the weights requires a GitHub Personal Access Token.
>
> 1. Create a token at https://github.com/settings/tokens → *Generate new token (classic)* → scope **`repo`** → copy the generated token (`ghp_...`).
> 2. Set the token in your terminal **without sharing it** (never paste a token in a chat or a versioned file):
>    ```bash
>    # macOS / Linux — add to ~/.zshrc or ~/.zprofile to make it permanent
>    export GITHUB_TOKEN=ghp_your_token
>    ```
>    ```powershell
>    # Windows PowerShell — add to $PROFILE to make it permanent
>    $env:GITHUB_TOKEN = "ghp_your_token"
>    ```
> 3. Run the download:
>    ```bash
>    python download_models.py
>    ```
>    Or let `run_tkinter.sh` / `run_tkinter.ps1` handle it automatically on first launch.

> **MongoDB port 54017**: MEDomics deliberately uses a non-standard port to avoid conflicts with system MongoDB instances. This port is hardcoded in `config.py` AND in `go_server/config.go`.

---

## Installation and Getting Started

> **All commands below assume you are in the project root directory** (`PLUGIN1-MEDomics/`).

### 1. Launch the React UI (primary interface)

```bash
# macOS / Linux
./start_react.sh

# Windows PowerShell
.\start_react.ps1
```

The launcher builds and starts the Go server on `http://localhost:8082`, then starts the React/Vite UI on `http://localhost:5173`.
Logs are written to `logs/go_server.log`, `logs/react_ui.log`, and `logs/starhe_dev.log`.

> **Production build**: `cd react_ui && npm run build` — outputs to `react_ui/dist/`.  
> The `dist/` folder can be served statically by any HTTP server or embedded in an Electron shell.

The React UI auto-proxies all `/starhe/*` calls to `http://localhost:8082` (configured in `vite.config.ts`). In production or Electron, set `window.__STARHE_API_BASE__ = 'http://localhost:8082'`.

### 2. Launch the Tkinter prototype (legacy development)

Both scripts are **self-contained**: they detect Python 3.13, create the venv if absent, install all dependencies and prepUS, then launch the interface. Only Python 3.13 needs to be installed on the system.

**Windows (PowerShell):**

> **One-time prerequisite**: allow local PowerShell scripts (to do once, as user):
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then, from the project root:

```powershell
.\run_tkinter.ps1
```

The script detects Python 3.13 on the system (via `py -3.13`, `python3.13`, or `python`), checks that tkinter is available, creates the venv if absent, installs dependencies, downloads the AI weights if absent, then launches the UI.

**macOS / Linux:**

```bash
# One-time prerequisite (macOS Homebrew only)
brew install python@3.13 python-tk@3.13
# Then launch the prototype from the project root (everything else is automatic)
./run_tkinter.sh
```

The `run_tkinter.sh` script checks that Python 3.13 and tkinter are present, creates the venv and installs dependencies if absent, installs prepUS, downloads the AI weights if absent, then launches the UI.

> **macOS (Homebrew)**: Homebrew **does not include tkinter by default** — `brew install python-tk@3.13` is mandatory, otherwise the UI will fail with `ModuleNotFoundError: No module named '_tkinter'`. Verify with: `python3.13 -c "import tkinter"`.

<details>
<summary>Equivalent manual commands (macOS / Linux)</summary>

> From the project root (`PLUGIN1-MEDomics/`):

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

<details>
<summary>Equivalent manual commands (Windows PowerShell)</summary>

> From the project root (`PLUGIN1-MEDomics/`):

```powershell
py -3.13 -m venv pythonCode\modules\starhe_plugin\.venv
pythonCode\modules\starhe_plugin\.venv\Scripts\pip install -r pythonCode\modules\starhe_plugin\requirements.txt
pythonCode\modules\starhe_plugin\.venv\Scripts\pip install sonocrop --no-deps
pythonCode\modules\starhe_plugin\.venv\Scripts\pip install third_party\prepUS --no-deps
Set-Location pythonCode\modules
..\..\pythonCode\modules\starhe_plugin\.venv\Scripts\python -m starhe_plugin.ui.prototype_tkinter
```

</details>

<details>
<summary>Equivalent manual commands (macOS / Linux)</summary>

> From the project root (`PLUGIN1-MEDomics/`):

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

### 3. Launch the Go server (MEDomics integration)

> From the project root (`PLUGIN1-MEDomics/`):

**Windows / macOS / Linux:**
```bash
cd go_server
go run .
# Listens on http://localhost:8082 (PORT configurable via environment variable)
```

Python paths are detected **automatically** by `config.go` from the `go_server/` directory (relative path `../pythonCode/modules/…`). No environment variables are necessary if the venv was created in step 1 and the server is launched from `go_server/`.

Go server environment variables:

| Variable | Default | Description |
|---|---|---|
| `PORT` / `STARHE_PORT` | `8082` | HTTP server port — `start_react.sh` auto-detects the first free port ≥ 8082 and exports it as `STARHE_PORT` |
| `STARHE_PYTHON_EXE` | absolute path in `config.go` | Python 3.13 from venv |
| `STARHE_PYTHON_PATH` | absolute path in `config.go` | Root directory of Python modules |
| `MONGO_URI` | `mongodb://localhost:54017/` | MongoDB URI |
| `MONGO_DB` | `medomics` | Database name |
| `MONGO_COLL` | `starhe_results` | Collection name |

### 4. Deploy in MEDomics (integrated mode)

> This mode is described in detail in the **MEDomics Integration** section below.  
> The plugin is deployed in the MEDomics repository via symlinks and a Go blueprint.

---

## Architecture

### React UI + standalone Go server (primary mode)

```
react_ui/  (React 18 / TypeScript / Vite — port 5173 in dev, dist/ in prod)
  src/StarhePlugin/
    index.tsx                 → root component (StarhePlugin), full state management
    api.ts                    → fetch / SSE calls to the Go server
    types.ts                  → shared types (DicomData, Detection, TabState, Measure…)
    colors.ts                 → MEDomics color palette
    hooks/
      useDisplaySettings.ts   → persistent display settings (localStorage)
      usePipelineSSE.ts       → SSE streaming consumer (analysis progress + results)
      usePlayback.ts          → frame playback (speed, loop, FPS from DICOM FrameTime)
      useCanvasInteractions.ts → pan / zoom / measure / series scroll (canvas events)
    components/
      Sidebar.tsx             → left sidebar 270 px: DICOM controls, nav, AI, results, metadata
      DicomCanvas.tsx         → main DICOM canvas (frames, bboxes, measures, brightness/contrast)
      DetectionGallery.tsx    → right panel 190 px: detected frames with thumbnails + SVG bboxes
      ConsolePanel.tsx        → collapsible log console at the bottom
      AdjustDialog.tsx        → floating contrast / brightness slider dialogs
      ContextMenu.tsx         → right-click context menu
      SettingsPanel.tsx       → settings overlay (font, colors, analysis mode, console toggle)
      LiveModal.tsx           → live analysis modal (C-STORE / folder / HDMI)
      BatchModal.tsx          → batch analysis modal (multi-file, JSON/CSV export-import, open-in-tab with pre-injected bboxes)
        │ HTTP + SSE (proxied by Vite dev server → port 8082 in dev)
        ▼
  Go Server (port 8082)
  go_server/main.go           → HTTP routing + CORS middleware
  go_server/handlers.go       → /starhe/analyze SSE, /starhe/results CRUD
  go_server/handlers_dicom.go → /starhe/dicom/load (path), /starhe/dicom/upload (file), /starhe/dicom/delete
  go_server/config.go         → absolute paths via os.Executable(), env var overrides
        │ subprocess os/exec  (stdout pipe, line by line)
        ▼
  Python Engine
  starhe_plugin/pipeline.py   → main orchestrator (run_risk / run_detection flags)
        │
        ├── dicom/reader.py        → DICOM reading (pydicom)
        ├── dicom/anonymizer.py    → tag anonymization
        ├── dicom/prepus_bridge.py → prepUS preprocessing
        ├── ai/starhe_risk.py      → STARHE-RISK (C3D, PyTorch)
        ├── ai/starhe_detect.py    → STARHE-DETECT (RTMDet subprocess server)
        │       └── ai/models/_rtmdet_runner.py  (secondary subprocess)
        ├── db/mongo_client.py     → MongoDB persistence (pymongo)
        └── utils/go_print.py      → stdout protocol to Go
```

```
Tkinter UI
        │ Python callbacks (set_log_sink)
        ▼
  starhe_plugin/pipeline.py (same engine, run in a thread)
```

### MEDomics integrated mode — iframe

The React UI production build (`react_ui/dist/`) is deployed as a **static bundle** inside the MEDomics renderer:

```
MEDomics/renderer/public/starhe-ui/   ← cp -r react_ui/dist/. here
MEDomics/app/starhe-ui/               ← cp -r react_ui/dist/. here (Electron main process)
```

`MEDomics/renderer/components/mainPages/starhe.jsx` renders an `<iframe src="/starhe-ui/index.html">` and, once loaded, sends a `postMessage` to configure the API base URL:

```js
// starhe.jsx
const STARHE_API_BASE = 'http://localhost:8082'
iframeRef.current.contentWindow.postMessage(
  { type: 'STARHE_INIT', apiBase: STARHE_API_BASE }, '*'
)
```

`react_ui/src/main.tsx` listens for `STARHE_INIT` and sets `window.__STARHE_API_BASE__` before mounting. All `api.ts` calls use this value at runtime, so the build is environment-agnostic.

> **Why hardcoded?** The STARHE Go server always runs on port 8082. It is independent of the MEDomics main server (port 54288). Using `WorkspaceContext.port` (the MEDomics server port) caused "Failed to fetch" errors.

**After any React change, redeploy:**
```bash
cd react_ui && npm run build
cp -r dist/. ../MEDomics/renderer/public/starhe-ui/
cp -r dist/. ../MEDomics/app/starhe-ui/
cd ../MEDomics/renderer && npx next build
```

### MEDomics integrated mode — Go blueprint

```
MEDomics Frontend (Electron / React)
        │ HTTP
        ▼
  MEDomics Go Server
  go_server/main.go  →  import Starhe "go_module/blueprints/starhe"
                          Starhe.AddHandleFunc()
        │
        ▼
  blueprints/starhe/starhe.go          → routes: starhe/analyze/, starhe/progress/
        │ Utils.StartPythonScripts(json, "run_starhe.py", id)
        ▼
  pythonCode/modules/starhe/run_starhe.py    → GoExecutionScript adapter (MEDomics conda env)
        │ subprocess.Popen([venv_python, "-m", "starhe_plugin.pipeline", ...])
        │ translates GO_PRINT|progress|… → set_progress(label=…, now=pct)
        │ translates GO_PRINT|result|…  → send_response(result_data)
        ▼
  pythonCode/modules/starhe_plugin/pipeline.py  → full pipeline (dedicated STARHE venv)
        │                                         (torch, mmdet, pydicom, etc.)
        └── ... (same modules as in standalone mode)
```

**Key difference**: in integrated mode, `run_starhe.py` serves as a bridge between two distinct Python environments:
- The **MEDomics env** (conda) where `GoExecutionScript` runs
- The **STARHE venv** (`.venv/`) where PyTorch, mmdet, and the pipeline run

### Go ↔ Python protocol (`go_print`)

Each Python output line follows the format:

```
GO_PRINT|<level>|<JSON message>
```

Levels: `info`, `warning`, `error`, `progress`, `result`.

The Go server parses each line with `bufio.Scanner` and relays it as SSE to the frontend:

```
data: {"level":"progress","message":"Loading DICOM…","data":{"step":1,"total":6}}
data: {"level":"result","message":"Pipeline completed","data":{...}}
data: [DONE]
```

In Tkinter UI mode, the sink can be redirected to a Python callback via `set_log_sink()` (see `utils/go_print.py`) — lines do not reach stdout.

---

## React UI (`react_ui/`)

### Stack

| Layer | Technology | Version |
|---|---|---|
| Framework | React | 18.3 |
| Language | TypeScript | 5.6 |
| Bundler | Vite | 5.4 |
| Styling | Inline styles + CSS (no external UI lib) | — |

### Features

| Feature | Description |
|---|---|
| **Multi-tab / multi-file** | Load N DICOM files concurrently; each tab stores its own independent state (frames, zoom, measures, contrast, analysis results…); analysis results are injected into the tab that launched the analysis, regardless of which tab is active when results arrive |
| **Multi-panel split view** | Drag a tab or thumbnail card into the viewer → opens that file in a new side-by-side panel; click a panel to focus it (blue outline); sidebar and gallery target the focused panel’s file; `×` removes a panel; CSS grid auto-layout (1/2/3/4 columns); empty state shows a drag hint; patient isolation — switching to a different patient automatically removes the previous patient’s panels; splitter-drift bug fixed (render override during resize + `onPanReset` prop resets all panels) |
| **DICOM loading** | Via absolute path (Electron / MEDomics), file picker (browser), or **folder picker** |
| **Folder loading** | "📁 Charger un dossier DICOM" button in the sidebar — browser folder picker (`webkitdirectory`); auto-detects `.dcm`, `.dicom`, and extension-less files; loads all files sequentially |
| **Frame viewer** | Hardware-accelerated canvas, `letter-box` fit, smooth scroll / keyboard navigation |
| **Playback** | Variable-speed loop (0.25×→3.0×) calibrated from DICOM `FrameTime` |
| **Pan / Zoom** | Mouse wheel zoom, middle-click drag, Ctrl+0/+/- shortcuts |
| **Measure tool** | Multi-segment mm measurements; draggable endpoints + whole segment; label auto-placed perpendicularly with draggable position; dashed leader line |
| **Contrast / Brightness** | Pixel-level ImageData manipulation (`c×pixel + b`, pivot at 0 — adapted for dark ultrasound images); contrast 0.1–3.0, brightness −50–+100; independent sliders; no CSS filter artifacts |
| **Right-click context menu** | 7 actions: Pan, Zoom, Measure, Series scroll, Contrast, Brightness, Reset view |
| **Analysis modes** | `RISK + DETECT` / `RISK only` / `DETECT only` — configurable from Settings |
| **SSE progress** | Real-time step-by-step progress from the pipeline streamed to the console and status label |
| **DetectionGallery** | Right panel (190 px): scrollable list of detected frames with thumbnail + SVG bbox overlay; click to navigate |
| **Console panel** | Collapsible log console; toggled from Settings or keyboard shortcut |
| **Settings panel** | Font scale, font family, text/sidebar/bg colors, analysis mode, console toggle — persisted to `localStorage` |
| **Live analysis modal** | Full port of `live_tab.py`: 3 sources (C-STORE, folder, HDMI), real-time RTMDet overlay, risk score |
| **MongoDB cache** | Cached results restored instantly on re-open; "Réinitialiser l'analyse" clears the server cache |
| **Batch analysis modal** | Multi-file sequential analysis; results table with risk score + bbox count per file; **JSON export** (full `detections_per_frame` — reloadable); **JSON import** — reload previous results without re-running inference; **CSV export**; checkboxes to open one, several, or all files in viewer tabs with detections pre-injected; fallback file picker when temp file has expired |
| **Theme** | Dark theme by default; sidebar and background colors fully configurable from Settings |
| **Keyboard shortcuts** | Space (play/pause), ←/→ (±1 frame), Shift+←/→ (±10), Home, P/M/S/R/C/L, `+`/`-` (±speed without modifier), `Cmd+`/`Cmd-`/`Cmd+0` (zoom only), B (loop), Ctrl+Tab / Ctrl+W |

### Development workflow

```bash
# Start Go + React together (Go is rebuilt automatically)
./start_react.sh

# Type-check + production build + deploy to MEDomics
cd react_ui && npm run build
cp -r dist/. ../MEDomics/renderer/public/starhe-ui/
cp -r dist/. ../MEDomics/app/starhe-ui/
```

### API surface (Go server → React)

| Method | Route | Description |
|---|---|---|
| `POST` | `/starhe/dicom/load` | Load DICOM by absolute path → frames base64 + metadata |
| `POST` | `/starhe/dicom/upload` | Upload DICOM file (multipart) → same response |
| `DELETE` | `/starhe/dicom/delete` | Release server-side upload reference (does **not** delete the file) |
| `POST` | `/starhe/analyze` | Launch pipeline → SSE stream of `progress` / `result` / `error` events |
| `GET` | `/starhe/results` | List MongoDB results (`?limit=N`) |
| `GET` | `/starhe/results/{id}` | One result by ObjectId |
| `DELETE` | `/starhe/results/{id}` | Delete cached result (reset) |
| `GET` | `/health` | Healthcheck |

### `POST /starhe/analyze` request body

```json
{
  "dicom_path"           : "/absolute/path/file.dcm",
  "anon_mode"            : "hash",
  "run_risk"             : true,
  "run_detection"        : true,
  "back_scan_conversion" : true,
  "backscan_width"       : 512,
  "backscan_height"      : 512
}
```

`run_risk: false` → pipeline skips STARHE-RISK (adds `--no_risk` arg to Python).  
`run_detection: false` → pipeline skips STARHE-DETECT (adds `--no_detection` arg).

---

## Analysis Pipeline (`pipeline.py`)

```
run_pipeline(dicom_path, anon_mode, run_detection, back_scan_conversion, ...)
```

Steps in order:

1. **DICOM Loading** — `load_dicom()` with `pydicom force=True` (supports files without extension).
2. **Anonymization** — mode `"hash"` (truncated SHA-256) or `"remove"`. The 16 sensitive DICOM tags are defined in `config.DICOM_SENSITIVE_TAGS`. Anonymization is reversible on the UI side (original values are saved in memory before anonymization).
3. **Frame Extraction** — `extract_frames()` returns `(T, H, W)` or `(T, H, W, 3)` in `uint8`.  
   At this point, the **RTMDet subprocess is launched in a background thread** so its model loading (~4 s) overlaps with the next two steps.
4. **prepUS Preprocessing** — see dedicated section below.
5. **STARHE-RISK** — C3D inference on the full clip.
6. **STARHE-DETECT** — RTMDet frame-by-frame inference (with temporal subsampling). The subprocess is already warm by the time steps 4–5 finish.
7. **MongoDB Save** — upsert on `file_path`.

---

## prepUS Preprocessing (`dicom/prepus_bridge.py`)

prepUS is the ultrasound image preprocessor from MEDomics. It is **vendored** in `third_party/prepUS/` to avoid an external dependency.

### What prepUS does

- Detects and removes static elements from the ultrasound machine interface (text, rulers, borders) by analyzing temporal pixel variability.
- Crops the US cone to remove black margins.
- Performs an inverse scan conversion (backscan): reconstructs the image in a 512×512 Cartesian space, correcting the ultrasound sector distortion.

### Code usage

```python
backscan_frames, crop_only_frames, info = preprocess_with_prepus(
    frames_rgb,                 # (T, H, W, 3) uint8 RGB
    back_scan_conversion=True,
    backscan_width=512,
    backscan_height=512,
)
```

Returns a tuple `(backscan, crop_only, info_dict)`:
- `backscan`: `(T, 512, 512)` uint8 grayscale — used for AI inference
- `crop_only`: `(T, H_crop, W_crop)` uint8 grayscale — used for visualization
- `info_dict`: keys `crop` (xmin/ymin/xmax/ymax), backscan parameters

### Internal implementation

1. Export numpy frames → temporary MP4 (OpenCV `VideoWriter`)
2. Call `prepUS.cli.removeLayoutFile(mp4, out_dir, back_scan_conversion=True, ...)`
3. Read `out_dir/backscan_video.mp4` → numpy
4. Read `out_dir/video.mp4` (crop without backscan) → numpy
5. Read `out_dir/infos.json` → ROI dict
6. Cleanup of temporary directory

> **Warning**: prepUS must be installed with `--no-deps` to avoid conflicts with the venv's OpenCV version. The `run_tkinter.ps1` script handles this automatically.

---

## STARHE-RISK Model (C3D)

### Architecture

C3D is a 3D convolutional network (spatiotemporal) defined in `ai/models/c3d.py` in pure PyTorch — **no mmaction2/mmcv dependency** at runtime.

```
Input:  (N, 3, 16, 112, 112)  — N clips, 3 channels, 16 frames, 112×112
  conv1a → pool1
  conv2a → pool2
  conv3a → conv3b → pool3
  conv4a → conv4b → pool4
  conv5a → conv5b → pool5
  flatten → fc6(4096) → relu → dropout
            fc7(4096) → relu
  I3DHead: fc_cls(2) → softmax
Output: (N, 2)  — prob [low_risk, high_risk]
```

### Why pure PyTorch without mmaction2

The `.pth` checkpoint was trained with mmaction2 (mmcv framework). To avoid dependency conflicts (mmcv incompatible with Python 3.13), the submodule names (`backbone.conv1a.conv.weight`, `cls_head.fc_cls.weight`, etc.) are **exactly reproduced** in `c3d.py`. The checkpoint therefore loads directly with `torch.load` without key remapping.

### Clip preprocessing

```python
clips = preprocess_clips(frames)  # returns (10, 3, 16, 112, 112)
```

- **10 clips** uniformly sampled over the entire duration (`NUM_CLIPS=10`)
- Each clip: 16 consecutive frames (`clip_len=16`)
- Resize → 128px (short side), center crop → 112×112
- Normalization: `mean=[104, 117, 128]`, `std=[1, 1, 1]` (BGR values, no division by 255)

### Inference

```python
logits = model(clips)           # (10, 2)
probs  = softmax(logits, dim=1) # (10, 2)
avg    = probs.mean(dim=0)      # (2,)  — average of 10 clips
risk_score = avg[1]             # "high risk" class probability
```

Display threshold: no threshold applied, the raw [0–1] score is returned.

---

## STARHE-DETECT Model (RTMDet)

### Problem: mmcv incompatible with Python 3.13

mmdet/mmcv uses compiled C extensions (`mmcv._ext`) and Python 2 frame metadata incompatible with Python 3.13. The adopted solution is an **isolated subprocess** that runs the RTMDet runner in a context where the necessary patches are applied.

### Persistent subprocess architecture

```
starhe_detect.py (main process)
        │
        │  os.Popen([python, _rtmdet_runner.py, --mode server, ...])
        ▼
    _rtmdet_runner.py (subprocess)
        │ applies 3 patches BEFORE any mmcv import:
        │   1. mmcv._ext stub (replaces missing C extension)
        │   2. tqdm stub (optional, avoids an ImportError)
        │   3. inspect.getmodule patch (Python 3.13 / mmengine compat)
        │
        │ loads RTMDet model (428 MB) ONCE
        │ emits "READY" on stdout
        │
        │ stdin/stdout JSON loop
        ▼
    {"type":"batch","images":["base64...", ...], "score_thr": 0.70}
        │
    [[{"bbox":[x0,y0,x1,y1],"score":0.87,"label":"tumor"}], [...], ...]
```

### Initialization sequence

1. `STARHEDetectModel.__init__()` calls `_start_server()`
2. `_start_server()` launches the subprocess with `--mode server`
3. Blocking wait for the `[rtmdet_server] READY {hw_json}` line on stdout
4. The runner embeds hardware info in the READY signal (see below)
5. `_start_server()` reads that info and computes the optimal batch size
6. Any other line = failure → `RuntimeError` with the last 2000 characters of stderr

### Adaptive hardware detection

After loading the model, the runner measures available memory **in the subprocess** (after the model is loaded) and reports it in the READY signal:

```
# NVIDIA GPU (CUDA)
[rtmdet_server] READY {"device": "cuda", "vram_free_mb": 5800.1, "vram_total_mb": 8192.0}
# Apple Silicon (MPS) — free RAM measured after model load
[rtmdet_server] READY {"device": "mps", "ram_free_mb": 14336.0}
# CPU only — free RAM measured after model load
[rtmdet_server] READY {"device": "cpu", "ram_free_mb": 6144.0}
```

Measuring in the subprocess (after model load) is more accurate than measuring in the parent process — the model's ~450 MB footprint is already accounted for.

Device selection in the runner:

```python
if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():   # Apple Silicon (M-series)
    device = "mps"
else:
    device = "cpu"
```

`_start_server()` parses this JSON and calls `utils/hardware.py::compute_optimal_batch_size()`:

```python
# utils/hardware.py
_FRAME_COST_MB = 50   # estimated memory cost per 640×640 frame
_MAX_BATCH_GPU = 32   # NVIDIA GPU cap
_MAX_BATCH_MPS = 16   # Apple Silicon cap (GPU+CPU share the same pool)
_MAX_BATCH_CPU = 16   # CPU cap — RAM is the only limit
_GPU_SAFETY    = 0.80  # fraction of free VRAM used
_MPS_SAFETY    = 0.30  # conservative: unified memory shared between GPU and CPU
_CPU_SAFETY    = 0.35  # 35 % of free RAM (eval() mode, no gradient → lower pressure)

def compute_optimal_batch_size(device, vram_free_mb=None, ram_free_mb=None):
    # ram_free_mb: measured in the subprocess after model load (preferred)
    if device == "cuda":
        usable = vram_free_mb * _GPU_SAFETY       # e.g. 5800 × 0.80 = 4640 MB
        batch  = min(int(usable / _FRAME_COST_MB), _MAX_BATCH_GPU)  # → capped 32
    elif device == "mps":
        ram_free = ram_free_mb or get_free_ram_mb()
        batch    = min(int(ram_free * _MPS_SAFETY / _FRAME_COST_MB), _MAX_BATCH_MPS)
    else:                                          # cpu
        ram_free = ram_free_mb or get_free_ram_mb()
        batch    = min(int(ram_free * _CPU_SAFETY / _FRAME_COST_MB), _MAX_BATCH_CPU)
    return max(1, batch)
```

Typical results on common hardware:

| Hardware | device | batch_size |
|---|---|---|
| NVIDIA RTX 3080 (10 GB) | `cuda` | 32 (capped) |
| Apple M5 Pro (24 GB unified) | `mps` | 16 (capped) |
| Apple M5 (16 GB unified) | `mps` | 16 (capped) |
| CPU only (16 GB RAM, ~14 GB free after model) | `cpu` | 16 (capped) |

> The `batch_size` is computed from free memory measured **after model loading** in the subprocess, making it accurate regardless of other processes running on the machine.

The result is stored in `detect_model.batch_size` and used directly by the pipeline.

Setting `DETECT_BATCH_SIZE = "auto"` in `config.py` activates this logic (default). Set it to an integer (e.g. `4`) to force a fixed size and bypass hardware detection.

### Frame serialization: base64 over pipe (no disk I/O)

Frames are no longer written to disk as PNG files. They are encoded as raw BGR bytes and transmitted directly over stdin:

```python
# parent process (starhe_detect.py)
bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
b64 = base64.b64encode(bgr.tobytes()).decode("ascii")
req = json.dumps({"frame_b64": b64, "shape": list(bgr.shape), "score_thr": score_thr})
proc.stdin.write(req + "\n")

# subprocess (_rtmdet_runner.py)
raw   = base64.b64decode(req["frame_b64"])
frame = np.frombuffer(raw, dtype=np.uint8).reshape(req["shape"])
```

For batches, `frame_b64` becomes `frames_b64` (list) and `shape` becomes `shapes` (list of shapes). The legacy file-path protocol (`image` / `images` keys) is preserved for backward compatibility.

### Sending a batch of frames

```python
# In predict_batch(frames) — base64 in-memory protocol:
payload = {
    "frames_b64": [base64.b64encode(cv2.cvtColor(f, cv2.COLOR_RGB2BGR).tobytes()).decode() for f in frames],
    "shapes":     [list(cv2.cvtColor(f, cv2.COLOR_RGB2BGR).shape) for f in frames],
    "score_thr":  score_thr,
}
proc.stdin.write(json.dumps(payload) + "\n")
proc.stdin.flush()
response = json.loads(proc.stdout.readline())
# response = [[det, ...], [det, ...], ...]  — one list per frame
```

### Temporal subsampling + active batch

In `pipeline.py`, only 1 frame out of every `DETECT_EVERY_N=4` is analysed. The intermediate frames inherit the same detections. The sampled frames are now grouped into batches of `detect_model.batch_size` before being sent:

```python
sampled = list(range(0, n_frames, stride))        # every 4th frame
bs      = detect_model.batch_size                 # auto-computed from hardware
for b_start in range(0, len(sampled), bs):
    batch_idx    = sampled[b_start : b_start + bs]
    batch_frames = [frames_processed[i] for i in batch_idx]
    batch_dets   = detect_model.predict_batch(batch_frames)  # single network pass
    for idx, dets in zip(batch_idx, batch_dets):
        for j in range(idx, min(idx + stride, n_frames)):
            detections.append({**d, "frame": j} for d in dets)
```

Practical gain: ×4 from temporal subsampling × batch parallelism on GPU (actual factor depends on hardware).

### DINO backend (alternative)

Defined in `ai/models/_dino_runner.py`. No server mode — each frame launches a separate subprocess (slow, for development use only). Selectable via `DETECT_BACKEND = "dino"` in `config.py`.

---

## Live Streaming Pipeline (`ai/live_pipeline.py`)

The live pipeline performs frame-by-frame inference on a continuous video stream. It is designed to run completely locally — no data leaves the machine.

### Architecture

```
source thread  ─push_frame()─►  LiveRingBuffer (deque, maxlen=160, thread-safe)
                                        │
                              _run() thread (daemon)
                                        │
                              snapshot() → (T, H, W, 3) window
                                        │
                    ┌───────────────────┴───────────────────┐
                    │                                       │
              RTMDet detect                          C3D risk (every 16 frames)
              (every DETECT_EVERY_N=4)               (on the ring buffer snapshot)
                    │                                       │
                    └────────────────► result dict ─────────┘
```

### `LiveRingBuffer`

Thread-safe circular buffer wrapping `collections.deque(maxlen=160)`:

```python
buf = LiveRingBuffer(maxlen=160)
buf.push(frame_uint8)          # (H, W, 3) numpy array
window = buf.snapshot()        # → (T, H, W, 3) copy — thread-safe
```

`maxlen=160` covers ~5 seconds at 30 fps, enough for the C3D sliding window (16 frames).

### `LivePipeline`

```python
pipe = LivePipeline(detect_model, risk_model)
pipe.start()           # starts the background inference thread
pipe.push_frame(arr)   # called by the source — non-blocking
result = pipe.latest_result()  # latest result dict (polled by UI)
pipe.stop()            # graceful shutdown
```

The `_run()` loop:
1. Drains `_input_queue` (maxsize=`INPUT_QUEUE_MAXSIZE=8` — drops oldest if full).
2. Every `DETECT_EVERY_N=4` frames: runs RTMDet on the current frame (512×512 after ROI crop).
3. Every `RISK_UPDATE_INTERVAL=16` frames: takes a `snapshot()` of the ring buffer and runs C3D.
4. Stores the latest result in `_latest_result` (thread-safe dict swap).

### ROI auto-calibration

`ROI_CALIBRATION_FRAMES = 30`. After 30 frames are received, `_auto_roi()` is called once to detect the ultrasound cone and compute the crop rectangle. All subsequent frames are cropped and resized to 512×512 before being sent to RTMDet.

### Result dict

```python
{
    "frame_idx"    : int,
    "timestamp"    : float,          # time.time()
    "detections"   : list[dict],     # [{bbox, score, label}, ...]
    "risk_score"   : float,          # 0.0–1.0
    "risk_label"   : str,            # "Low risk" | "High risk"
    "roi"          : list[int],      # [x0, y0, x1, y1] — None before calibration
    "_frame_display": np.ndarray,    # cropped+resized frame for the UI preview
}
```

### Key constants (`config.py`)

| Constant | Default | Effect |
|---|---|---|
| `LIVE_RING_MAXLEN` | `160` | Ring buffer depth (~5 s at 30 fps) |
| `LIVE_DETECT_EVERY_N` | `4` | RTMDet called every N frames |
| `LIVE_RISK_INTERVAL` | `16` | C3D updated every N frames |
| `LIVE_INPUT_QUEUE_MAXSIZE` | `8` | Drop policy: oldest frame dropped if queue full |
| `LIVE_ROI_CALIBRATION_FRAMES` | `30` | Frames before ROI auto-detection |

---

## Live Analysis Tab (`ui/live_tab.py`)

`LiveTab(tk.Frame)` is opened as a `tk.Toplevel` window from the main prototype (button **📡 Analyse en direct** in the sidebar).

### Input sources

| Source constant | Thread class | Description |
|---|---|---|
| `SOURCE_CSTORE = "cstore"` | `_DicomReceiver` (pynetdicom SCP) | Listens on a configurable TCP port for C-STORE from the ultrasound machine |
| `SOURCE_FOLDER = "folder"` | `_FolderWatcher(Thread)` | Polls a directory every 0.5 s for new `.dcm` files |
| `SOURCE_HDMI = "hdmi"` | `_HDMIReader(Thread)` | Reads frames from a USB HDMI capture card via `cv2.VideoCapture` |

### HDMI capture card

`_list_capture_devices()` enumerates video devices (`CAP_AVFOUNDATION` on macOS, `CAP_MSMF` on Windows). It returns `(index, name, fps, width, height)` tuples. `_refresh_hdmi_devices()` uses a 3-pass selection:
1. Prefer devices whose name contains known capture card keywords (`elgato`, `avermedia`, `magewell`, `capture`, `usb`, …).
2. Exclude known cameras (e.g. `facetime`, `iphone`, `continuity`).
3. Among remaining candidates, pick the highest-resolution device.

If no recognized capture card is found, `_hdmi_capture_card_found = False` and a warning label is shown (⚠ orange). The **Start** button is hard-blocked — `_start_live()` raises an error without opening any camera.

> **Hardware note**: plugging an HDMI cable directly into a Mac Thunderbolt/USB-C port is not supported — those ports are output-only. A USB HDMI capture card (e.g. Elgato HD60 S+, AVerMedia, Magewell USB Capture) is required.

### Display decoupling

The preview canvas is refreshed by `_preview_tick()` at 33 ms (≈30 fps) regardless of the inference rate. It reads `_latest_display_frame` (written by the source thread) and overlays bounding boxes from `pipe.latest_result()`. This ensures smooth video even when inference is slower than 30 fps.

### Source sidebar frames

Each source has its own sidebar frame shown/hidden by `_on_source_changed()`:

- **C-STORE**: AE title + TCP port entry, pynetdicom SCP start/stop.
- **Folder**: directory browse button, recursive toggle.
- **HDMI**: device combobox (populated by **Scan** button), resolution selector (`Auto` / `1080p` / `720p` / `PAL` / `SD`), hardware warning label.

The STARHE plugin integrates into the MEDomics platform following the "Standard Plugin" pattern (analogous to 3D Slicer extensions). The integration consists of three parts:

### 1. Go Blueprint (`medomics_integration/starhe_blueprint.go`)

Go file to copy into `MEDomics/go_server/blueprints/starhe/starhe.go`. It registers two routes:

| Route | Function | Description |
|---|---|---|
| `starhe/analyze/` | `handleAnalyze` | Launches the STARHE pipeline via `Utils.StartPythonScripts()` |
| `starhe/progress/` | `handleProgress` | Returns the progress of the current job |

Then in `MEDomics/go_server/main.go`:
```go
import Starhe "go_module/blueprints/starhe"
// in main():
Starhe.AddHandleFunc()
```

### 2. Python Adapter (`pythonCode/modules/starhe/run_starhe.py`)

Python script that inherits from `GoExecutionScript` (MEDomics lib). It runs in the MEDomics conda environment and:

1. Receives `--json-param <json> --id <id>` from the Go server
2. Locates the STARHE venv (`.venv/` in `starhe_plugin/`, or via `$STARHE_PLUGIN_DIR`)
3. Launches `python -m starhe_plugin.pipeline` as a subprocess in the STARHE venv
4. Reads `GO_PRINT|…` lines and translates them:
   - `GO_PRINT|progress|{…}` → `self.set_progress(label=…, now=pct)`
   - `GO_PRINT|result|{…}` → data collected for `send_response()`
   - `GO_PRINT|error|{…}` → `go_print("[STARHE ERROR] …")`

### 3. Manifest (`plugin.json`)

JSON file at the project root documenting the integration elements (routes, paths, commands to add to MEDomics `main.go`) and the standalone configuration.

### Deployment

Deployment in the MEDomics repository is done by:

1. **Copy** the Go blueprint → `MEDomics/go_server/blueprints/starhe/starhe.go`
2. **Symlinks** in `MEDomics/pythonCode/modules/`:
   - `starhe/` → adapter (`run_starhe.py`)
   - `starhe_plugin/` → the complete plugin (pipeline, AI, DICOM, DB…)
3. **Patch** `MEDomics/go_server/main.go` (import + `AddHandleFunc()`)

> **Windows note**: symlinks require administrator rights or developer mode enabled.

---

## MongoDB Database

### Connection

Local port `54017` (non-standard, configured in `config.py` and `go_server/config.go`). Each `_get_collection()` call opens a connection with 3s timeout — no global pool on the Python side (pymongo manages its own pool).

### Document schema

```json
{
  "_id"                  : "<ObjectId>",
  "file_path"            : "/absolute/path/file.dcm",
  "processed_at"         : "2026-04-01T14:22:11Z",
  "num_frames"           : 180,
  "roi"                  : [x0, y0, x1, y1],
  "risk"                 : {"score": 0.82, "label": "High risk"},
  "detections_per_frame" : [
    [],
    [{"bbox": [120, 80, 200, 160], "score": 0.91, "label": "tumor"}],
    []
  ],
  "anon_mode"            : "hash",
  "analysis_mode"        : "backscan"
}
```

- `detections_per_frame` is a **list of lists** indexed by frame, length = `num_frames`.
- The cache key is the pair `(file_path, analysis_mode)` — one document per file **and per** analysis mode (`original`, `crop`, `backscan`). Sensitive to file relocation/renaming.
- `replace_one({file_path: ..., analysis_mode: ...}, doc, upsert=True)`: one document per file + mode combination.

### Available operations (`db/mongo_client.py`)

```python
save_result(file_path, num_frames, roi, risk, detections_per_frame, anon_mode, analysis_mode)
find_by_file(file_path, analysis_mode=None)  # → dict | None  (optional filter by mode)
get_result(result_id)     # → dict | None  (by ObjectId string)
list_results(limit=100)   # → list[dict]
delete_result(file_path)  # → bool
```

---

## Go Server (`go_server/`)

> The full API surface is documented in the **React UI** section above.

### Files

| File | Role |
|---|---|
| `main.go` | HTTP routing, CORS middleware (`withCORS`), server startup |
| `handlers.go` | `POST /starhe/analyze` — launches `pipeline.py`, SSE streaming of `GO_PRINT|…` lines |
| `handlers_dicom.go` | DICOM load (path), upload (multipart), delete cache reference |
| `config.go` | Absolute paths via `os.Executable()`, env var overrides (`STARHE_PYTHON_EXE`, `STARHE_PYTHON_PATH`, etc.) |

### CORS

The `withCORS` middleware in `main.go` adds `Access-Control-Allow-*` headers for all endpoints — required for the React frontend (Electron / Vite dev server) to call the API.

### Absolute paths

`config.go` uses `os.Executable()` to resolve Python paths relative to the **binary location**, not the working directory. This means the server can be launched from any directory without `STARHE_PYTHON_EXE` / `STARHE_PYTHON_PATH` environment variables.

---

## Tkinter Prototype Interface (`ui/prototype_tkinter.py`)

---

## Tkinter Prototype Interface (`ui/prototype_tkinter.py`)

The prototype is used to validate the pipeline and UX before porting to React. It is a single file of about 2500 lines.

### Non-obvious technical points

**Persistent RTMDet subprocess**: on the UI side, `STARHEDetectModel` is used exactly as in `pipeline.py`, in a `threading.Thread` to avoid blocking the interface.

**Multi-file tabs**: each tab stores a complete state `dict` (~30 keys: raw frames, prepUS frames, current index, measurements, zoom, contrast, AI results per mode, metadata, etc.). The `_save_tab_state()` method copies `self._xxx` variables into `self._tabs[i]`, and `_restore_tab_state(i)` does the reverse. No data is reloaded from disk when switching tabs.

**Results per display mode**: detections and results are stored in dicts indexed by mode (`_detections_by_mode` and `_results_by_mode`, keys: `"backscan"`, `"crop"`, `"original"`). When the user toggles between modes (toggle crop/backscan), only the bounding boxes and results for the active mode are displayed. The `_refresh_results_panel()` method updates the Mode, Risk, and Lesions labels accordingly.

**Measurements in mm**: calibration follows this priority order from DICOM metadata:
1. `SequenceOfUltrasoundRegions` (tag `(0018,6011)`) — physicalDeltaX/Y in cm
2. `PixelSpacing` (tag `(0028,0030)`) — in mm
3. `ImagerPixelSpacing` (tag `(0018,1164)`) — in mm

The `pixel_spacing` value (mm/px) is stored in the tab state and used by `_draw_measure_overlay()` to display the distance in mm.

**Playback loop**: the `_tick()` method is called via `self.after(delay_ms, self._tick)`. The delay is calculated from the DICOM `FrameTime` (in ms) divided by `_speed_mult`. For speeds ≥1, frames are skipped (`_skip_n`) instead of reducing the delay (limited to ~15ms by `after`).

**go_print on the UI side**: at initialization, `set_log_sink(lambda level, msg: self._append_log(msg))` redirects all messages to the interface console. The sink is reset to `None` on close.

**Live analysis button**: the sidebar contains a **📡 Analyse en direct** button that calls `_open_live_window()`. This opens a singleton `tk.Toplevel` (stored in `self._live_win`) containing a `LiveTab` frame. Re-clicking the button while the window is open brings it to the foreground instead of opening a second window.

**Zoom and pan**: all canvas coordinates are recalculated at each `_refresh_canvas()` by applying the affine transform `(x * zoom + pan_x, y * zoom + pan_y)`. Images are resized via `PIL.Image.resize` with `LANCZOS`.

**Anonymization at import**: original values are saved in `original_sensitive` (list of tuples `(tag_name, value)`) before anonymization. They are displayed in red in the metadata panel. Anonymized values are in `kept_metadata`.

### Keyboard shortcuts

A `_kb_guard()` guard checks that focus is not on a text widget (`tk.Entry`, `tk.Text`, `scrolledtext.ScrolledText`) before executing the shortcut — avoids interference with user input.

---

## Python 3.13 Compatibility

Python 3.13 introduced several changes incompatible with mmcv/mmdet. Here are the patches applied in `_rtmdet_runner.py` **before any mmcv import**:

### 1. `mmcv._ext` stub

mmcv attempts to import a compiled C extension `mmcv._ext` (`NMSop`, etc.). This extension does not exist in recent versions or with incompatible builds. The stub replaces the module with a Python object whose every attribute raises a `RuntimeError` only if called:

```python
class _CExtStub(types.ModuleType):
    def __getattr__(self, name):
        def _unavailable(*a, **kw):
            raise RuntimeError(f"mmcv._ext.{name}: C-extension missing.")
        return _unavailable
sys.modules["mmcv._ext"] = _CExtStub("mmcv._ext")
```

RTMDet inference does not in practice use the NMS functions from the extension (PyTorch provides its own).

### 2. `inspect.getmodule` patch

mmengine (mmdet dependency) calls `inspect.getmodule()` on Python frame objects. In Python 3.13, this can raise `AttributeError` or `OSError` in certain contexts. The patch wraps the original call in a try/except and returns `None` on failure (tolerable behavior for mmengine).

### 3. `tqdm` stub

tqdm is not in the mmdet dependencies. If absent, mmdet raises an `ImportError` on import. The stub injects a minimal module where `tqdm.tqdm(iterable)` returns the iterable as-is.

### 4. NMS CPU coercion (MPS compatibility)

On Apple Silicon (`device="mps"`), the NMS inputs (`bboxes`, `scores`) produced by the RTMDet head are MPS tensors. `torchvision.ops.nms` does not support MPS, and `mmengine.InstanceData.__getitem__` only accepts `torch.LongTensor` (CPU type) — passing an MPS tensor causes an `AssertionError`. The patch forces all NMS operands to CPU before calling `torchvision.ops.nms`:

```python
def _tv_nms_fwd(ctx, bboxes, scores, iou_threshold, offset, score_threshold, max_num):
    bboxes = bboxes.float().cpu()   # force CPU — MPS not supported by torchvision NMS
    scores = scores.float().cpu()
    ...
    return inds   # always a CPU torch.LongTensor
```

### 5. `InstanceData` MPS patch

Even with CPU NMS indices, the `InstanceData` fields (bboxes, scores…) produced by the head are still on MPS. Indexing an MPS tensor with a CPU index (`mps_tensor[cpu_index]`) raises a cross-device error. The patch detects any non-standard device in the `InstanceData` fields and copies everything to CPU before indexing:

```python
def _mps_safe_getitem(self, item):
    if isinstance(item, torch.Tensor) and item.device.type not in ("cpu", "cuda"):
        item = item.cpu()
    has_nonstandard = any(
        isinstance(v, torch.Tensor) and v.device.type not in ("cpu", "cuda")
        for v in self.values()
    )
    if has_nonstandard:
        cpu_self = type(self)()
        for k, v in self.items():
            cpu_self[k] = v.cpu() if isinstance(v, torch.Tensor) else v
        return _orig_inst_getitem(cpu_self, item)
    return _orig_inst_getitem(self, item)
```

This patch is applied after mmdet is imported (patch 6 in the runner), so it has no effect on CUDA or CPU inference.

---

## Full Project Structure

```
PLUGIN1-MEDomics/
│
├── run_tkinter.ps1                   # Windows UI prototype launcher (auto-installs prepUS)
├── run_tkinter.sh                    # macOS/Linux UI prototype launcher (auto-installs prepUS)
├── setup.sh                          # macOS/Linux venv + dependencies setup (without UI)
├── setup.ps1                         # Windows venv + dependencies setup (without UI)
├── plugin.json                       # Plugin manifest (standalone config + MEDomics integration)
├── README.md                         # This file
├── READMEUtilisateur.md              # Tkinter interface user guide
├── TODOLIST.md                       # Logbook / roadmap
├── MEDomicsLab_LOGO.png              # Logo displayed in the UI
│
├── go_server/                        # Standalone Go server (standalone mode)
│   ├── main.go                       # HTTP routing + MongoDB init
│   ├── config.go                     # Environment variables with default values
│   └── handlers.go                   # REST handlers + SSE streaming
│
├── medomics_integration/             # Files intended for the MEDomics repository
│   └── starhe_blueprint.go           # Go blueprint (routes starhe/analyze, starhe/progress)
│
├── third_party/
│   └── prepUS/                       # Vendored prepUS package (pip install --no-deps)
│
└── pythonCode/modules/
    │
    ├── starhe/                       # MEDomics adapter (GoExecutionScript)
    │   ├── __init__.py
    │   └── run_starhe.py             # MEDomics → STARHE venv subprocess bridge
    │
    └── starhe_plugin/                # Complete STARHE plugin
        │
        ├── .venv/                    # Python 3.13 virtual environment (not versioned)
        ├── __init__.py               # on_load() / on_unload() hooks (MEDomics lifecycle)
        ├── config.py                 # All constants, paths, hyperparameters
        ├── pipeline.py               # Main orchestrator (Go entry point)
        ├── requirements.txt          # Python dependencies
        │
        ├── ai/
        │   ├── starhe_risk.py        # C3D wrapper: loading + inference
        │   ├── starhe_detect.py      # RTMDet/DINO wrapper: subprocess server
        │   ├── live_pipeline.py      # Live streaming: LiveRingBuffer + LivePipeline
        │   └── models/
        │       ├── c3d.py            # C3D architecture in pure PyTorch (without mmaction2)
        │       ├── _rtmdet_runner.py # RTMDet runner (image mode + server mode)
        │       ├── _dino_runner.py   # DINO-DETR runner (image mode only)
        │       ├── rtmdet.py         # RTMDet stubs for mmdet config loading
        │       └── dino.py           # DINO-DETR stubs
        │
        ├── db/
        │   └── mongo_client.py       # MongoDB CRUD (save/find/list/delete) + graceful degradation
        │
        ├── dicom/
        │   ├── reader.py             # DICOM loading, frame extraction, uint8
        │   ├── anonymizer.py         # Tag anonymization + imager banner removal
        │   ├── prepus_bridge.py      # prepUS integration (MP4 export → numpy frames)
        │   └── crop.py               # Custom crop algorithm (fallback if prepUS unavailable)
        │
        ├── ui/
        │   ├── prototype_tkinter.py  # Prototype interface (~2500 lines)
        │   └── live_tab.py           # Live streaming tab (LiveTab Toplevel window)
        │
        └── utils/
            └── go_print.py           # Go ↔ Python stdout protocol + set_log_sink()
```

---

## Configuration (`config.py`)

All parameters are in a single file. Paths are relative to the project — no adaptation needed on a new machine:

```python
DATA_DIR   = os.environ.get("STARHE_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))  # DICOM files directory
MODELS_DIR = os.path.join(BASE_DIR, "models")   # AI checkpoints (not versioned)
```

`DATA_DIR` defaults to `data/` at the project root. Overridable via the `STARHE_DATA_DIR` environment variable.

### MongoDB environment variables

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:54017/` | MongoDB connection URI |
| `MONGO_DB` | `medomics` | Database name |
| `MONGO_COLL` | `starhe_results` | Collection name |

These variables allow sharing the same MongoDB instance between the standalone plugin and the MEDomics platform without modifying the code.

### Cross-platform compatibility

- **Paths**: `pathlib` is used in `mongo_client.py` and `starhe_detect.py` for path normalization (cache keys, venv detection).
- **MongoDB**: graceful degradation — if MongoDB is unavailable, the pipeline runs normally but results are not cached (`save_result()` and `find_by_file()` return `None` instead of raising an exception).

AI parameters:

| Parameter | Value | Effect |
|---|---|---|
| `DETECT_BACKEND` | `"rtmdet"` | Change to `"dino"` to test DINO-DETR |
| `DETECT_SCORE_THRESHOLD` | `0.70` | Minimum confidence threshold, affects display and cache |
| `DETECT_EVERY_N` | `4` | Temporal subsampling (1 = all frames) |
| `DETECT_BATCH_SIZE` | `"auto"` | Batch size for RTMDet: `"auto"` = compute from VRAM/RAM via `utils/hardware.py`; set to an integer to force a fixed value |

Live streaming parameters:

| Parameter | Value | Effect |
|---|---|---|
| `LIVE_RING_MAXLEN` | `160` | Ring buffer depth (frames) |
| `LIVE_DETECT_EVERY_N` | `4` | RTMDet called every N incoming frames |
| `LIVE_RISK_INTERVAL` | `16` | C3D risk score updated every N frames |
| `LIVE_INPUT_QUEUE_MAXSIZE` | `8` | Max frames queued for inference; oldest dropped if full |
| `LIVE_ROI_CALIBRATION_FRAMES` | `30` | Frames received before ROI auto-detection runs |

---

## Known Limitations and Points of Attention

- **MongoDB cache key = absolute path**: if the DICOM file is moved or renamed, the analysis is re-run even if it was already performed.
- **Tab switch during analysis**: the analysis runs in a separate thread and continues even if the source tab is closed. Results are lost if the tab is closed before completion.
- **prepUS and backscan**: backscan only works on sector images (standard B-mode). Linear images (superficial vessels) may produce a degraded backscan — use `back_scan_conversion=False` in that case.
- **GPU**: STARHE-RISK automatically switches to CUDA if available. STARHE-DETECT (RTMDet in subprocess) uses CPU by default; add `--device cuda` in the `_start_server()` cmd to enable GPU.

---

## Other Documents

- [READMEUtilisateur.md](READMEUtilisateur.md) — User guide for the Tkinter interface
- [TODOLIST.md](TODOLIST.md) — Logbook, completed tasks and roadmap
