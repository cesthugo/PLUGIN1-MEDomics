# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**STARHE** is a medical imaging plugin for the [MEDomics](https://medomicslab.gitbook.io/medomics-docs) platform. It analyzes hepatic ultrasound DICOM cine-clips to screen for hepatocellular carcinoma (HCC) using two AI models:
- **STARHE-RISK**: C3D 3D-CNN (binary: low/high HCC risk) — checkpoint `models/best_acc_mean_cls_f1_epoch_14.pth`
- **STARHE-DETECT**: RTMDet or DINO-DETR (lesion bounding boxes) — checkpoint `models/best_coco_bbox_mAP_50_iter_2100.pth`

Stack: Python 3.13 · Go 1.22 · React 18 + TypeScript + Vite · Electron 33

## Development Commands

### Setup (first time)
```bash
make setup              # macOS/Linux — creates .venv, installs deps, mmaction2, prepUS
# Windows: make setup (uses scripts/setup.ps1)
```

### Run (development)
```bash
make react              # Go server + React/Vite (http://localhost:5173)
make tkinter            # Legacy Tkinter UI
make electron           # Electron app in dev mode (Vite + Electron concurrently)
```

### Build & Package
```bash
make build              # Compile Electron renderer + main (no launch)
make pack               # Full distributable installer (DMG/deb/exe)

# Go server only
cd go_server && go build -o go_server . && ./go_server

# Python worker bundle (PyInstaller)
cd pythonCode/modules && pyinstaller ../../scripts/starhe_worker.spec --noconfirm
# Output: pythonCode/modules/dist/starhe_worker/
```

### TypeScript checks
```bash
cd renderer && npm run typecheck    # tsc --noEmit
cd renderer && npm run build        # type-check + Vite build
```

### Evaluation scripts (no prepUS needed — MP4 already preprocessed)
```bash
# Run RISK + DETECT on preprocessed MP4s
source pythonCode/modules/starhe_plugin/.venv/bin/activate
python scripts/eval_preprocessed_mp4.py --input <dir> --output results.csv

# Compare mmaction2 vs pytorch backends
python scripts/compare_risk_backends.py --input <dir> --output comparison.csv
```

## Architecture

### Request Flow

```
User (browser/Electron)
  → React UI (renderer/src/pages/StarhePlugin.tsx)
    → Go HTTP server (go_server/, port 8082)
      → Python subprocess: python -m starhe_plugin.pipeline <dicom_path> ...
        → pipeline.py (orchestrator)
          → STARHE-RISK: _c3d_runner.py subprocess (stdin/stdout JSON)
          → STARHE-DETECT: _rtmdet_runner.py subprocess (stdin/stdout JSON)
        → stdout: GO_PRINT|level|{json} lines (parsed by Go)
      → SSE stream to React (data: {json}\n\n)
```

### Python/Go Communication Protocol

All Python → Go communication goes through **stdout lines** with the prefix format:
```
GO_PRINT|<level>|<json_payload>
```
Levels: `info`, `warning`, `error`, `progress`, `result`. The `result` level carries the final structured output. See `utils/go_print.py`.

In the Electron bundle, Go calls `starhe_worker --module pipeline <args>` instead of `python -m starhe_plugin.pipeline`.

### Subprocess Pattern for AI Models (critical constraint)

`mmcv._ext` (C extension) is not compiled for Python 3.13. **All mmdet/mmaction2 imports live exclusively in subprocess runner scripts**, never in the main plugin process.

Each runner (`_rtmdet_runner.py`, `_c3d_runner.py`, `_dino_runner.py`) must apply these patches **before any mm* import**, in this exact order:
1. `sys.modules["mmcv._ext"] = _CExtStub(...)` — stub the missing C extension
2. Patch `inspect.getmodule` — Python 3.13 / mmengine incompatibility
3. (RTMDet only) `NMSop.forward = staticmethod(_tv_nms_fwd)` — NMS via torchvision

Runners communicate via **persistent stdin/stdout JSON** (server mode): parent sends one JSON line per request, runner responds with one JSON line. This keeps the model loaded in memory across calls.

### C3D Backend Selection (`config.py`)

`C3D_BACKEND = os.environ.get("C3D_BACKEND", "mmaction2")` selects between:
- `"mmaction2"` (default): `_c3d_runner.py` loads `mmaction2.C3D` + `mmaction2.I3DHead` directly (no registry). Requires mmaction2 installed with `--no-deps` + 3 venv patches (applied by `setup.sh`).
- `"pytorch"`: `C3DRecognizer` in `c3d.py` (pure PyTorch, float64 when `DETERMINISTIC_INFERENCE=True`). Fallback if mmaction2 unavailable.

Both backends share identical preprocessing (validated bit-identical on the same frames, Δ < 1e-7).

### mmaction2 Installation & Patches

mmaction2 is installed `--no-deps` and requires 3 patches to `.venv/lib/.../mmaction/`:
- `models/localizers/__init__.py`: remove `DRN` import (absent from wheel 1.2.0)
- `models/roi_heads/__init__.py`: add `AssertionError` to except clause (mmdet registry conflict)
- `models/task_modules/__init__.py`: same AssertionError fix

`setup.sh` applies these patches automatically via `sed`. Do not use `init_recognizer` from mmaction2 (registry scope conflict with mmdet under Python 3.13); load `C3D` and `I3DHead` classes directly instead.

### React UI Structure

`renderer/src/` follows the MEDomics renderer layout (components / pages / styles / utilities):
- `pages/StarhePlugin.tsx` — root component, all global state (tabs, patients, log)
- `utilities/starhe/api.ts` — all fetch calls to the Go server; `getApiBase()` resolves API URL (Electron preload → `window.__STARHE_API_BASE__` → relative proxy)
- `utilities/starhe/hooks/usePipelineSSE.ts` — consumes SSE from `/starhe/analyze`, dispatches progress/result events
- `utilities/starhe/hooks/usePlayback.ts` — frame-by-frame DICOM animation
- `components/starhe/DicomCanvas.tsx` — canvas rendering, zoom/pan/measure
- `utilities/starhe/types.ts` — all shared types (`TabState`, `DicomData`, `Detection`, `SSEPayload`, etc.)
- `styles/starhe/StarhePlugin.css` — global plugin CSS

`SSEPayload.data` mirrors the JSON emitted by `go_result()` in Python. When Python sends `risk_score`/`risk_label`, the React side reads `data.risk?.risk_score`.

### Key Config Flags (`config.py`)

| Flag | Default | Effect |
|---|---|---|
| `DETERMINISTIC_INFERENCE` | `True` | Forces CPU float64 for cross-platform reproducibility |
| `PREPUS_BYPASS_MP4` | `False` | `True` = pure numpy crop (no ffmpeg roundtrip) |
| `USE_WEASIS_EXPORT` | `True` | Apply DICOM Modality/VOI LUTs via Java JAR before prepUS |
| `C3D_BACKEND` | `"mmaction2"` | C3D inference backend |
| `DETECT_BACKEND` | `"rtmdet"` | Detection backend (`"rtmdet"` or `"dino"`) |
| `DETECT_EVERY_N` | `4` | Run detection on 1 frame out of N (propagate to others) |
| `DETECT_BATCH_SIZE` | `"auto"` | RTMDet batch size (auto-detects VRAM/RAM) |

### Electron / Distribution

In packaged mode, Electron sets:
- `STARHE_WORKER_BIN` → path to PyInstaller `starhe_worker` binary (dispatches to Python modules)
- `STARHE_WEIGHTS_DIR` → `userData/models/` (downloaded at first launch by `download-models.ts`)
- `STARHE_WEASIS_DIR` → bundled JRE + JAR path

Model `.pth` weights are **not bundled** in the installer — they are downloaded at first launch. Config `.py` files are bundled via PyInstaller `datas`.

### Pipeline Entry Points

| Entry point | Called by | Purpose |
|---|---|---|
| `pipeline.py` | Go `/starhe/analyze` | DICOM full pipeline (RISK + DETECT) |
| `pipeline_mp4.py` | Go `/starhe/mp4/analyze` | MP4 full pipeline |
| `dicom/loader_cli.py` | Go `/starhe/dicom/load` | DICOM → JPEG frames (no AI) |
| `dicom/loader_mp4_cli.py` | Go `/starhe/mp4/load` | MP4 → JPEG frames (no AI) |
| `ai/run_live.py` | Go `/starhe/live` | Live streaming inference |

### MongoDB Caching

Go caches analysis results in MongoDB (default `mongodb://localhost:54017/`). Cache key = `(file_path, analysis_mode)` where `analysis_mode` encodes run_risk/run_detect/backscan/anon flags. `DELETE /starhe/cache?path=…` clears a specific file's cache.

### Third-party Vendored Components

- `third_party/prepUS/` — ultrasound preprocessing (cone cropping, UI removal). Installed with `--no-deps`.
- `third_party/weasis-dcm2png/` — Java JAR for LUT-correct DICOM-to-PNG export. `dist/` is gitignored; CI rebuilds it from `target/` (committed Maven artifacts).
- `ai/vendor/starhe/` — vendored Python package from the training project. Required only by DINO backend. Do not modify manually.

### CI/CD

`.github/workflows/release.yml` builds on push to `v*` tags across 4 platforms (mac-arm64, mac-x64, linux-x64, win-x64). Build order: Go binary → Python PyInstaller bundle → JRE fetch → Electron build → artifacts upload. A draft GitHub release with SHA256SUMS is created after all matrix jobs succeed.
