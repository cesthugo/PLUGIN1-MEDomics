# STARHE Plugin — MEDomics

> **STARHE** = **S**tratification of risk and de**T**ection of **H**epatocellular carcinoma by **E**chography.  
> Python/Go extension of the [MEDomics](https://medomicslab.gitbook.io/medomics-docs) platform.

*Version `0.7.0-beta.1` — Last updated: July 9, 2026*

---

## Overview

The plug-in analyzes abdominal ultrasound DICOM cine-clips to screen for hepatocellular carcinoma (HCC). It operates in **four modes**:

| Mode | Description |
|---|---|
| **React UI (standalone)** | React 18 / TypeScript frontend (`renderer/`) built with Vite, served by a standalone Go server (`go_server/`). Full DICOM viewer, AI pipeline, multi-tab, live analysis. **Current primary UI.** |
| **Tkinter prototype** | Legacy Tkinter UI (`ui/prototype_tkinter.py`). Used for early validation before porting to React. Launched via `scripts/run_tkinter.sh`. |
| **MEDomics Integrated** | Integrates into the MEDomics platform as a *Standard Plugin*. An adapter (`run_starhe.py`) translates the `GO_PRINT|…` protocol to the MEDomics protocol (`progress*_*` / `response-ready*_*`). A Go blueprint (`starhe_blueprint.go`) registers routes in the MEDomics server. |
| **Live Streaming** | Real-time frame-by-frame inference on a live ultrasound feed. The `LivePipeline` (`ai/live_pipeline.py`) processes incoming frames in a background thread. Three input sources: C-STORE DICOM (pynetdicom SCP), local folder watcher, USB HDMI capture card. Live modal available in the React UI. |

Two AI models are used:

| Model | Architecture | Task | Checkpoint |
|---|---|---|---|
| **STARHE-RISK** | C3D (3D-CNN via mmaction2 subprocess) | Binary classification: low / high HCC risk | `models/best_acc_mean_cls_f1_epoch_14.pth` |
| **STARHE-DETECT** | RTMDet (mmdet) or DINO-DETR | Detection and localization of hepatic lesions | `models/best_coco_bbox_mAP_50_iter_2100.pth` |

---

## Prerequisites

| Tool | Minimum Version | Notes |
|---|---|---|
| Python | 3.13 | tkinter included; 3.14 incompatible (tkinter broken). On macOS Homebrew: `brew install python@3.13 python-tk@3.13` |
| MongoDB | 4.x+ | Local service on port **54017** (non-standard) |
| Go | 1.21+ | Required for the REST/SSE server |
| Node.js | 18+ | Required for the React UI (`renderer/`). `node_modules/` is **not** in the repository — installed automatically by `npm ci` on first launch |
| Java (optional) | 17+ | Activates the `weasis-dcm2png` path (DICOM → PNG with Modality/VOI LUT applied, aligned with training distribution). Without Java, the pipeline falls back to `pydicom` transparently. macOS: `brew install openjdk@17`. |
| CUDA (optional) | 11.8+ | GPU inference; CPU used if absent |

> **DICOM compressed formats**: JPEG Baseline, JPEG Lossless, and JPEG 2000 (lossless/lossy) are all supported via `pylibjpeg` (installed automatically with `requirements.txt`). No additional system library is needed.

> **AI model weights**: the `.pth` checkpoint files (~200 MB each) are **not included** in the repository. They are downloaded automatically by `scripts/run_tkinter.sh` / `scripts/run_tkinter.ps1` from the dedicated **public** repo [GitHub Release STARHE_MODELS](https://github.com/cesthugo/starhe-models/releases/tag/STARHE_MODELS) — no GitHub token required. To download them manually: `python scripts/download_models.py`.
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
>    Or let `scripts/run_tkinter.sh` / `scripts/run_tkinter.ps1` handle it automatically on first launch.

> **MongoDB port 54017**: MEDomics deliberately uses a non-standard port to avoid conflicts with system MongoDB instances. This port is hardcoded in `config.py` AND in `go_server/config.go`.

---

## Distribution — Builds Electron (`.dmg` / `.deb` / `.AppImage` / `.exe`)

The plugin is distributed as a **standalone Electron application** (same approach as MEDomics). The full pipeline (React renderer + electron-builder + extraResources) is configured in [renderer/package.json](renderer/package.json) under the `"build"` key.

### Produced Targets

| Platform | Format | Name | Notes |
|---|---|---|---|
| macOS arm64 | `.dmg` | `STARHE-<version>-mac-arm64.dmg` | Drag-and-drop (Apple Silicon M1/M2/M3) |
| macOS arm64 | `.zip` | `STARHE-<version>-mac-arm64.zip` | `.app` archive |
| macOS x64 | `.dmg` | `STARHE-<version>-mac-x64.dmg` | Mac Intel (macos-13 runner, long queue) |
| Linux x64 | `.deb` | `STARHE-<version>-linux-amd64.deb` | Debian / Ubuntu |
| Windows x64 | `.exe` | `STARHE-<version>-win-x64.exe` | NSIS installer |

> The `.pkg` and `.AppImage` targets were removed: `.pkg` requires an Apple Developer certificate, `.AppImage` was exhausting the disk of GitHub-hosted Ubuntu runners (~14 GB available).

### Electron Wrapper Architecture

| File | Role |
|---|---|
| [renderer/electron/main.ts](renderer/electron/main.ts) | Main process: splash → spawn `go_server` (auto-sélection binaire par plateforme) → wait `/health` 200 → main window |
| [renderer/electron/preload.ts](renderer/electron/preload.ts) | Minimal `contextBridge`: native `openDicomFiles()` + `apiBase` |
| [renderer/electron/splash.html](renderer/electron/splash.html) | 480×280 splash shown while the Go server starts |
| [renderer/build-resources/](renderer/build-resources/) | Binaires Go cross-compilés, JREs, bundle PyInstaller, JAR weasis, icônes |

`main.ts`:
- **Dev mode** : auto-sélectionne `renderer/build-resources/go-server/go-server-{os}-{arch}[.exe]` depuis `process.platform` + `process.arch` (mac-arm64, mac-x64, linux-x64, win-x64)
- **Packaged mode** : utilise `go_server/go_server[.exe]` depuis `process.resourcesPath` (copié par electron-builder)
- Spawns `go_server` with env `PORT=8082` + `STARHE_WEASIS_DIR` pointing to the packaged resources
- **Healthcheck**: pings `GET /health` every 300 ms, 30 s timeout — on failure, shows "Retry / Quit" dialog with MongoDB hint
- **Exponential backoff**: auto-restarts the Go server on crash (1s → 2s → 5s → 10s → 30s)
- **Clean kill** on `before-quit` (SIGTERM to the Go server)

### Bundled Resources (`extraResources`)

Copied into `STARHE.app/Contents/Resources/` (macOS) or `resources/` (Linux/Windows).  
Toutes les ressources sont dans `renderer/build-resources/` — plus aucune référence extérieure à `renderer/` dans `package.json` :

| Source (`renderer/build-resources/`) | Destination dans le paquet | Taille |
|---|---|---|
| `go-server/go-server-{os}-{arch}[.exe]` | `go_server/go_server[.exe]` | ~13 MB par plateforme (4 binaires cross-compilés, **committés dans le repo**) |
| `weasis-dcm2png/` | `weasis-dcm2png/` | ~31 MB JAR + libs OpenCV natives (macOS — rebuild Maven sur Linux/Windows) |
| `starhe_worker/` | `starhe_worker/` | ~568 MB (Python + torch + mmdet — PyInstaller, **gitignored**, rebuild via `make build-worker`) |
| `jre-{os}-{arch}/` | `jre/` | ~130–151 MB Temurin 17 JRE (**gitignored**, fetch via `scripts/fetch_jre.sh`) |

> **MongoDB remains an external prerequisite** (MEDomics consistency) — not bundled. If MongoDB is down, the user sees the "Retry / Quit" dialog with instructions.

### Build Prerequisites

| Tool | Version | Why |
|---|---|---|
| Node.js | 18+ | electron-builder + Vite |
| Go | 1.21+ | Only needed if Go source changed — run `make cross-compile` to regenerate the 4 cross-compiled binaries. Pre-built binaries are **committed in the repo** (not required for a simple `git clone`). |
| Python 3.13 + venv | — | Compile the PyInstaller worker (`pythonCode/modules/starhe_plugin/.venv/`) |
| PyInstaller | 6.20+ | `pip install pyinstaller` in the venv |
| `curl` + `tar` (Unix) or PowerShell (Win) | — | Download the Temurin JRE via `scripts/fetch_jre.{sh,ps1}` |
| (Optional) `iconutil` / ImageMagick | — | Generate `.icns` / `.ico` from a PNG (see [renderer/build-resources/README.md](renderer/build-resources/README.md)) |

### Build locally

```bash
# 1. (Optional) Re-cross-compile Go binaries — only if go_server/ source changed.
#    Pre-built binaries for mac/linux/win are already committed in the repo.
make cross-compile
# Produces: renderer/build-resources/go-server/go-server-{mac-arm64,mac-x64,linux-x64,win-x64.exe}

# 2. Bundle the Python worker (--onedir, ~5-10 min, ~530 MB)
cd pythonCode/modules
pyinstaller ../../scripts/starhe_worker.spec --noconfirm \
            --distpath ../../renderer/build-resources
# Produces: renderer/build-resources/starhe_worker/starhe_worker
# Test:     ../../renderer/build-resources/starhe_worker/starhe_worker --module pipeline --help

# 3. Download the Temurin 17 JRE for the current platform (~130 MB)
cd ../..
./scripts/fetch_jre.sh                # auto-detect (mac-arm64, mac-x64, linux-x64)
# Windows:  .\scripts\fetch_jre.ps1
# Produces: renderer/build-resources/jre-<platform>/bin/java(.exe)

# 4. Build the renderer + Electron main + package
cd renderer
npm install        # first time
npm run electron:pack         # all targets declared in package.json
# Or a specific target:
npx electron-builder --mac dmg --arm64
npx electron-builder --linux deb AppImage --x64
npx electron-builder --win nsis --x64
```

Artifacts generated in [renderer/release/](renderer/release/) (gitignored).

### Bundled Python Worker (Phase 2)

The Go server automatically detects which Python to use via the `STARHE_WORKER_BIN` environment variable (see [go_server/config.go](go_server/config.go), `pythonCmd()` helper):

- **Dev mode** (`STARHE_WORKER_BIN` not set): `python -m starhe_plugin.<module>` from the local venv
- **Packaged mode** (`STARHE_WORKER_BIN=/path/to/starhe_worker`): `starhe_worker --module <name>` — standalone PyInstaller bundle

Electron automatically passes this variable when spawning the Go server (see [renderer/electron/main.ts](renderer/electron/main.ts)). The 5 entry points are dispatched by [pythonCode/modules/starhe_plugin/starhe_worker.py](pythonCode/modules/starhe_plugin/starhe_worker.py) via `runpy.run_module()`:

| `--module` | Module Python invoqué |
|---|---|
| `pipeline` | `starhe_plugin.pipeline` (analyse DICOM SSE) |
| `pipeline_mp4` | `starhe_plugin.pipeline_mp4` (analyse MP4 SSE) |
| `ai.run_live` | `starhe_plugin.ai.run_live` (mode live cstore/folder/hdmi) |
| `dicom.loader_cli` | `starhe_plugin.dicom.loader_cli` (extraction frames DICOM) |
| `dicom.loader_mp4_cli` | `starhe_plugin.dicom.loader_mp4_cli` (extraction frames MP4) |

### Bundled Temurin JRE (Phase 3)

The pipeline calls `weasis-dcm2png` (Java JAR) to apply VOI LUTs exactly as during training. Rather than requiring `brew install openjdk@17` from the user, the `.dmg` bundles a standalone Temurin 17 JRE (~150 MB extracted).

The Python bridge [weasis_bridge.py](pythonCode/modules/starhe_plugin/dicom/weasis_bridge.py) reads two environment variables, in order:

| Variable | Dev mode | Packaged mode |
|---|---|---|
| `STARHE_JAVA_BIN` | not set → `shutil.which("java")` (PATH) | `Resources/jre/bin/java` (bundled JRE) |
| `STARHE_WEASIS_DIR` | not set → `third_party/weasis-dcm2png/dist/` (repo) | `Resources/weasis-dcm2png/` (bundled JAR + OpenCV libs) |

Electron sets both variables only in packaged mode. In dev mode, PATH fallback is used for `java`, and the repo JAR for the bridge.

> **Phase 3 limitations**:
> - The **`.pth` model weights** (~750 MB) are **still not bundled** — they remain to be downloaded on first launch (Phase 4).
> - The JRE and PyInstaller bundle are **specific to the current platform**. Build on each target OS+arch (GitHub Actions CI, Phase 5) with `fetch_jre.sh <platform>` then `electron-builder --mac/--linux/--win`.

### `.pth` Models Downloaded on First Launch (Phase 4)

To keep the `.dmg` small (325 MB instead of ~1 GB), the two C3D + RTMDet checkpoints are **not bundled** in the installer. On the first launch of a packaged build, Electron opens a "Downloading STARHE models" window that fetches the files and stores them in the app's `userData` folder.

| Fichier | Taille | Modèle |
|---|---|---|
| `best_acc_mean_cls_f1_epoch_14.pth` | 312 MB | C3D — STARHE-RISK (best validation mean-class-F1 checkpoint) |
| `best_coco_bbox_mAP_50_iter_2100.pth` | 439 MB | RTMDet — STARHE-DETECT |

**Emplacement** : `app.getPath('userData')/models/` — sur macOS : `~/Library/Application Support/starhe-plugin/models/`.

Le module [renderer/electron/download-models.ts](renderer/electron/download-models.ts) résout l'URL de téléchargement dans cet ordre :

| Priority | Condition | Source |
|---|---|---|
| 1 | `STARHE_MODELS_BASE_URL` set | `${STARHE_MODELS_BASE_URL}/<name>` (test override / custom hosting) |
| 2 | `STARHE_MODELS_CDN_URL` set | `${STARHE_MODELS_CDN_URL}/<name>` (baked-in public CDN default) |
| 3 | `GITHUB_TOKEN` set | GitHub API `/repos/cesthugo/starhe-models/releases/tags/STARHE_MODELS` (optional, public repo) |
| 4 | default | `https://github.com/cesthugo/starhe-models/releases/download/STARHE_MODELS/<name>` (**public** release — no token) |

On the Python side, [config.py](pythonCode/modules/starhe_plugin/config.py) reads `STARHE_WEIGHTS_DIR` (set by Electron when spawning the Go server in packaged mode) to resolve `.pth` paths. In dev mode, the variable is absent and the code falls back to `MODELS_DIR` (= `pythonCode/modules/starhe_plugin/models/` in the repo).

**Local PoC test** without GitHub dependency:

```bash
# 1) Serve the .pth files from the repo
cd pythonCode/modules/starhe_plugin/models && python3 -m http.server 8765 &

# 2) Clear userData then launch the app with the override
rm -rf "$HOME/Library/Application Support/starhe-plugin"
STARHE_MODELS_BASE_URL=http://localhost:8765 \
  /Applications/STARHE.app/Contents/MacOS/STARHE
```

The download window should open and progress to 100%, then the app continues its normal boot (splash → Go server → React UI).

> **Phase 4 status**:
> - **Resolved (July 2026)**: the `.pth` weights are now hosted in the dedicated **public** repo [`cesthugo/starhe-models`](https://github.com/cesthugo/starhe-models/releases/tag/STARHE_MODELS). Any tester downloads them on first launch with **no GitHub token**. The code repo stays private.
> - To force a re-download after updating weights: delete the `app.getPath('userData')/models/` folder.

### Multi-Platform CI (Phase 5)

The [.github/workflows/release.yml](.github/workflows/release.yml) workflow builds the complete MEDomics-aligned installer grid on GitHub-hosted runners as soon as a `v*` tag is pushed. To test without publishing a release: trigger `workflow_dispatch` from the **Actions** tab (or `gh workflow run release.yml`).

| Runner | Platform | Produced targets | Typical duration |
|---|---|---|---|
| `macos-14` | `mac-arm64` | `.dmg`, `.zip` | ~3 min |
| `macos-13` | `mac-x64` | `.dmg`, `.zip` | 1–5 h (long queue free tier) |
| `ubuntu-latest` | `linux-x64` | `.deb` | ~12 min (torch CPU-only) |
| `windows-latest` | `win-x64` | `.exe` (NSIS) | ~9 min |

Each job: disk cleanup (Linux, ~25 GB) → Python deps + torch CPU-only (Linux) + `pyinstaller starhe_worker.spec --distpath ../../renderer/build-resources` (cached on hit) → `fetch_jre.{sh,ps1} <platform>` → `npm ci` + `npm run build:electron` → `npx electron-builder <flags>` → upload installers. Go binaries are **pre-built and committed** — no Go compilation step needed in CI. The final `release` job aggregates artifacts, computes `SHA256SUMS.txt`, and creates a **draft GitHub release** via `softprops/action-gh-release@v2`.

**Trigger a new release**:

```bash
# 1. Bump the version
#    Edit "version" in renderer/package.json → e.g. "0.6.4"
git add renderer/package.json
git commit -m "chore: bump version to 0.6.4"
git push

# 2. Tag → automatically triggers the CI workflow
git tag -a v0.6.4 -m "v0.6.4"
git push origin v0.6.4
# → GitHub Actions builds 4 platforms and creates the draft release
# → Go to GitHub Releases and click "Publish release"
```

**First published release: [v0.6.3](https://github.com/cesthugo/PLUGIN1-MEDomics/releases/tag/v0.6.3)** (June 12, 2026) — 4 artifacts: `.dmg` arm64, `.zip` arm64, `.deb` linux, `.exe` win.

> **Limitations**: the workflow performs **neither signing nor notarization** (`CSC_IDENTITY_AUTO_DISCOVERY=false`). For a clinical release, add Apple/Windows secrets and enable `xcrun notarytool` post-build. The `weasis-dcm2png/native/` folder currently contains only macOS `.dylib` files → the Java bridge falls back to pydicom at runtime on Linux/Windows until the OpenCV `.so`/`.dll` are regenerated.

### Signing & Notarization

Current builds are **unsigned**:
- **macOS**: Gatekeeper will block the first launch → right-click > **Open** > **Open Anyway**
- **Windows**: SmartScreen will show a warning → **More info** > **Run anyway**

For an official clinical release, plan for: Apple Developer ID + notarization (`xcrun notarytool`), Windows EV Code Signing Certificate.

### MEDomics Generic Plugin Discovery Integration

STARHE integrates into MEDomics via a generic plugin discovery system added in June 2026, requiring **no MEDomics source code changes** per plugin.

**How it works:**
1. `scripts/medomics_register.sh` installs `medomics_integration/plugin.json` into the MEDomics `userData/plugins/STARHE/` directory (auto-detects dev/prod paths).
2. On startup, MEDomics calls the `discover-plugins` IPC handler, which scans `userData/plugins/` and reads each `plugin.json` manifest.
3. Any unknown `open{X}Module` dispatch in `layoutContext.jsx` looks up the matching plugin in `discoveredPlugins` and calls `openExternalPlugin()`, which opens a FlexLayout tab.
4. The tab renders `ExternalPluginPage.jsx` — a generic iframe component that loads the plugin `uiUrl` and exchanges `PLUGIN_INIT` / `STARHE_INIT` postMessages.

**`medomics_integration/plugin.json` manifest fields:**

| Field | Value |
|---|---|
| `id` | `starhe` |
| `name` | `STARHE` |
| `uiUrl` | `http://localhost:8082` (Go server serves the built React UI) |
| `healthUrl` | `http://localhost:8082/health` |
| `apiPort` | `8082` |

**Register the plugin (run once after launching MEDomics at least once):**
```bash
./scripts/medomics_register.sh
```

---

## Installation and Getting Started

> **All commands below assume you are in the project root directory** (`PLUGIN1-MEDomics/`).

### Quick Start — Double-click launchers (no terminal required)

Two sets of double-clickable launchers are available at the project root. They auto-configure every dependency (venv, Go binary, React build) on first run.

#### Plugin standalone — React UI + Go server (without MEDomics)

| File | Platform | What it launches |
|---|---|---|
| `launch_plugin.command` | macOS — double-click in Finder | MongoDB `:54017` · Go server `:8082` · Vite dev server `:5173` · opens browser automatically |
| `launch_plugin.bat` | Windows — double-click in Explorer | Same (each service opens in its own CMD window) |

Both scripts: verify Python 3.13 / Node.js / Go, create the venv if absent, install Python dependencies and AI weights, compile the Go binary if absent, install React `node_modules` if absent, find and start MongoDB, then open `http://localhost:5173`. **Ctrl+C** stops all services cleanly (macOS); close the individual service windows (Windows).

#### MEDomics + Plugin — Full Electron app

| File | Platform | What it launches |
|---|---|---|
| `launch_medomics.command` | macOS — double-click in Finder | MEDomics Electron app (MongoDB + Go MEDomics + Go STARHE `:8082`) |
| `launch_medomics.bat` | Windows — double-click in Explorer | Same |

Requires the `MEDomics/` directory as a sibling of `PLUGIN1-MEDomics/`. Builds the Go binary if absent, runs `npm install` in MEDomics if absent, builds and deploys the React UI bundle if `dist/` is absent, then launches `npm run dev` in the MEDomics directory (nextron → Electron, which auto-starts MongoDB, MEDomics Go server, and the STARHE Go server).

---

### 1. Launch the React UI (primary interface)

**macOS / Linux:**
```bash
# Recommended: one-command launcher (auto port detection + Go + Vite)
./scripts/start_react.sh   # or: make react
# Go server starts on the first free port ≥ 8082 (env var STARHE_PORT)
# Vite dev server starts on http://localhost:5173
```

**Windows (PowerShell):**
```powershell
.\scripts\start_react.ps1   # or: make react
# Go server starts on the first free port ≥ 8082 (env var STARHE_PORT)
# Vite dev server starts on http://localhost:5173
```

Or manually:
```bash
# 1. Start the Go server
cd go_server
go build -o go_server . && ./go_server
# Listening on http://localhost:8082

# 2. In a separate terminal: start the Vite dev server
cd renderer
npm ci    # first time only (installs from package-lock.json)
npm run dev
# Open http://localhost:5173
```

> **Production build**: `cd renderer && npm run build` — outputs to `renderer/dist/`.  
> The `dist/` folder can be served statically by any HTTP server or embedded in an Electron shell.

The React UI auto-proxies all `/starhe/*` calls to `http://localhost:8082` (configured in `vite.config.ts`). In production or Electron, set `window.__STARHE_API_BASE__ = 'http://localhost:8082'`.

> **Port auto-detection**: `scripts/start_react.sh` / `scripts/start_react.ps1` auto-detects the first free TCP port ≥ 8082 and exports it as `STARHE_PORT`. Override before launching: `STARHE_PORT=9000 ./scripts/start_react.sh` (macOS/Linux) or `$env:STARHE_PORT=9000; .\scripts\start_react.ps1` (Windows).

### 2. Launch the Tkinter prototype (legacy development)

Both scripts are **self-contained**: they detect Python 3.13, create the venv if absent, install all dependencies and prepUS, then launch the interface. Only Python 3.13 needs to be installed on the system.

**Windows (PowerShell):**

> **One-time prerequisite**: allow local PowerShell scripts (to do once, as user):
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then, from the project root:

```powershell
.\scripts\run_tkinter.ps1   # or: make tkinter
```

The script detects Python 3.13 on the system (via `py -3.13`, `python3.13`, or `python`), checks that tkinter is available, creates the venv if absent, installs dependencies, downloads the AI weights if absent, then launches the UI.

**macOS / Linux:**

```bash
# One-time prerequisite (macOS Homebrew only)
brew install python@3.13 python-tk@3.13
# Then launch the prototype from the project root (everything else is automatic)
./scripts/run_tkinter.sh   # or: make tkinter
```

The `scripts/run_tkinter.sh` script checks that Python 3.13 and tkinter are present, creates the venv and installs dependencies if absent, installs prepUS, downloads the AI weights if absent, then launches the UI.

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
# Listens on http://localhost:8080 (PORT configurable via environment variable)
```

Python paths are detected **automatically** by `config.go` from the `go_server/` directory (relative path `../pythonCode/modules/…`). No environment variables are necessary if the venv was created in step 1 and the server is launched from `go_server/`.

Go server environment variables:

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8082` | HTTP server port (also readable via `STARHE_PORT`) |
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
renderer/  (React 18 / TypeScript / Vite — port 5173 in dev, dist/ in prod)
  src/
    pages/
      StarhePlugin.tsx        → root component (StarhePlugin), full state management
    utilities/starhe/
      api.ts                  → fetch / SSE calls to the Go server
      types.ts                → shared types (DicomData, Detection, TabState, Measure…)
      colors.ts               → MEDomics color palette
      utils.ts                → pure utility functions (nextTabId, isDicomFile…)
      hooks/
        useDisplaySettings.ts   → persistent display settings (localStorage)
        usePipelineSSE.ts       → SSE streaming consumer (analysis progress + results)
        usePlayback.ts          → frame playback (speed, loop, FPS from DICOM FrameTime)
        useCanvasInteractions.ts → pan / zoom / measure / series scroll (canvas events)
        useTabManager.ts        → tab & patient state management
        useKeyboardShortcuts.ts → keyboard shortcuts wiring
    components/starhe/
      Sidebar.tsx             → left sidebar 270 px: DICOM controls, nav, AI, results, metadata
      DicomCanvas.tsx         → main DICOM canvas (frames, bboxes, measures, brightness/contrast)
      DicomUploader.tsx       → DICOM upload component (drag-and-drop, file picker, path input)
      DetectionGallery.tsx    → right panel 190 px: detected frames with thumbnails + SVG bboxes
      ConsolePanel.tsx        → collapsible log console at the bottom
      AdjustDialog.tsx        → floating contrast / brightness slider dialogs
      ContextMenu.tsx         → right-click context menu
      SettingsPanel.tsx       → settings overlay (font, colors, analysis mode, console toggle)
      LiveModal.tsx           → live analysis modal (C-STORE / folder / HDMI)
      BatchModal.tsx          → batch analysis modal (multi-file, export/import JSON+CSV, open-in-tab)
    styles/starhe/
      StarhePlugin.css        → global plugin CSS
        │ HTTP + SSE (proxied by Vite dev server → port 8082 in dev)
        ▼
  Go Server (port 8082, default — auto-detected by scripts/start_react.sh / scripts/start_react.ps1 via STARHE_PORT)
  go_server/main.go           → HTTP routing + CORS middleware
  go_server/handlers.go       → /starhe/analyze SSE, /starhe/results CRUD, /starhe/live/* (live analysis)
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
  starhe_plugin/ai/run_live.py → live analysis entry point (folder / HDMI / C-STORE)
        └── ai/live_pipeline.py   → LiveRingBuffer + LivePipeline (frame-by-frame inference)
```

```
Tkinter UI
        │ Python callbacks (set_log_sink)
        ▼
  starhe_plugin/pipeline.py (same engine, run in a thread)
```

### MEDomics integrated mode

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

## React UI (`renderer/`)

The `renderer/` folder follows the MEDomics `renderer/` layout convention (page 4 of the MEDomics architecture document):

```
renderer/src/
  pages/                 → StarhePlugin.tsx  (root component, global state)
  components/starhe/     → 14 React components (Sidebar, DicomCanvas, BatchModal…)
  utilities/starhe/      → api.ts · types.ts · colors.ts · utils.ts
  utilities/starhe/hooks/→ usePipelineSSE · usePlayback · useCanvasInteractions · …
  styles/starhe/         → StarhePlugin.css
renderer/public/images/  → static assets (medomics_logo.png)
renderer/electron/       → Electron main process (main.ts, preload.ts, splash.html…)
renderer/build-resources/→ go-server/ · starhe_worker/ · weasis-dcm2png/ · jre-{os}-{arch}/
```

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
| **DICOM loading** | Via absolute path (Electron / MEDomics) or file upload drag-and-drop / file picker (`DicomUploader.tsx` component) |
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
| **Live analysis modal** | 3 sources (C-STORE, folder, HDMI), real-time RTMDet overlay, risk score; backed by `run_live.py` subprocess launched by the Go server; preview frames streamed before inference → surveillance-camera behaviour |
| **MongoDB cache** | Cached results restored instantly on re-open; "Reset analysis" clears the server cache |
| **Batch analysis modal** | Multi-file sequential analysis; results table with risk score + bbox count per file; export to JSON (with full `detections_per_frame`) or CSV; import a previous JSON to reload results without re-running inference; checkboxes to open one, several, or all files directly in viewer tabs with detections pre-injected |
| **Folder loading** | "📁 Load a DICOM folder" — `webkitdirectory` picker; auto-detects `.dcm`, `.dicom`, and extension-less files |
| **Theme** | Dark theme by default; sidebar and background colors fully configurable from Settings |
| **Keyboard shortcuts** | Space (play/pause), ←/→ (±1 frame), Shift+←/→ (±10), Home, P/M/S/R/C/L, `+`/`-` (±speed without modifier), `Cmd+`/`Cmd-`/`Cmd+0` (zoom only), B (loop), Ctrl+Tab / Ctrl+W |

### Development workflow

```bash
# macOS / Linux — recommended one-command launch (auto port detection)
./scripts/start_react.sh   # or: make react
```
```powershell
# Windows — equivalent
.\scripts\start_react.ps1   # or: make react
```
```bash
# Or manually (macOS / Linux):
lsof -ti :8082 | xargs kill -9 2>/dev/null
# Go binaries are pre-built in renderer/build-resources/go-server/ — pick your platform:
./renderer/build-resources/go-server/go-server-mac-arm64 &   # macOS Apple Silicon
# ./renderer/build-resources/go-server/go-server-mac-x64 &   # macOS Intel
# ./renderer/build-resources/go-server/go-server-linux-x64 & # Linux
cd renderer && npm run dev

# Windows (PowerShell):
# Start-Process renderer\build-resources\go-server\go-server-win-x64.exe
# cd renderer; npm run dev

# Type-check + production build
cd renderer && npm run build
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
| `POST` | `/starhe/live/start` | Launch `run_live.py` subprocess → SSE stream of preview frames + detections |
| `POST` | `/starhe/live/stop` | Stop the running live subprocess |
| `GET` | `/starhe/live/stream` | SSE: live preview frames (base64) + detection + risk score events |

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
3. **Frame Extraction** — preferred path: `frames_via_weasis()` (subprocess Java → PNG with Modality + VOI LUT, controlled by `USE_WEASIS_EXPORT` flag). Automatic fallback to `extract_frames()` (pydicom) if Java/JAR absent or transfer syntax unsupported by Weasis (notably JPEG 2000). Output: `(T, H, W, 3)` uint8 RGB.  
   At this point, the **RTMDet subprocess is launched in a background thread** so its model loading (~4 s) overlaps with the next two steps.
4. **prepUS Preprocessing** — executed whenever `run_risk=True` or `run_detection=True`. Crops the US cone and removes static UI overlays. Both STARHE-RISK and STARHE-DETECT receive `crop_frames` (fan-shaped sector crop, same distribution as training data for both models). See dedicated section below.
5. **STARHE-RISK** — C3D inference on `crop_only_frames` (fan-shaped sector crop, grayscale → pseudo-RGB R=G=B). This matches the training distribution: the C3D was trained on `video.mp4` files produced by prepUS (fan-shaped crop, grayscale, mp4v codec, read by Decord). See [STARHE-RISK: C3D Pipeline](#starhe-risk-c3d-pipeline) below.
6. **STARHE-DETECT** — RTMDet inference on `crop_only_frames` (the model was trained on `cropped_videos` — fan-shaped crop, not Cartesian backscan; confirmed by `train_dataloader.data_prefix = "cropped_videos"` in `rtmdet_starhe.py`). Temporal subsampling at stride `DETECT_EVERY_N`. Bounding boxes are remapped from crop space to DICOM coordinates via simple offset (`xmin`/`ymin`). The subprocess is already warm by the time steps 4–5 finish.
7. **MongoDB Save** — upsert on `file_path`.

---

## STARHE-RISK: C3D Pipeline

STARHE-RISK classifies a hepatic ultrasound video clip as **low or high HCC risk** using a C3D 3D-CNN trained with mmaction2. At inference the plugin reproduces the exact training pipeline bit-for-bit, validated to produce a score delta of 0.000000 against the original mmaction2 pipeline on the same input files.

### Checkpoint

| File | Size | Notes |
|---|---|---|
| `best_acc_mean_cls_f1_epoch_14.pth` | 312 MB | Best checkpoint by validation mean-class F1 (early stopping). `STARHE_RISK_CHECKPOINT` in `config.py` points to this file, and Electron's `download-models.ts` fetches it on first launch. |

The plugin's copy is **byte-identical** (MD5 `2b212cc522f102d71f14ca740e64f108`) to the original training checkpoint at `starhe_share/models/classification/best_acc_mean_cls_f1_epoch_14.pth`, and reproduces its scores bit-for-bit on the 24-patient test set (see [Validation](#validation-june-22-2026)).

> **Note on `epoch_45.pth`**: the training project also ships a final-epoch checkpoint `epoch_45.pth` (624 MB full checkpoint incl. optimizer state). It is **not** used by the plugin — the plugin loads the validation-F1 best `best_acc_mean_cls_f1_epoch_14.pth`. The original eval config `c3d_starhe.py` has `load_from = None` (it trains from the Sports-1M pretrained backbone, not from another checkpoint).

### Subprocess Architecture (`_c3d_runner.py`)

mmcv's C extension (`mmcv._ext`) is not compiled for Python 3.13. All mmaction2 imports are confined to a **persistent subprocess** (`ai/models/_c3d_runner.py`) so the main process never loads mm* packages.

```
STARHERiskModel (main process, Python 3.13)
  │
  │  subprocess.Popen([python, ai/models/_c3d_runner.py,
  │                    --ckpt  models/best_acc_mean_cls_f1_epoch_14.pth,
  │                    --device cpu, --deterministic])
  ▼
_c3d_runner.py (subprocess)
  │
  │  from mmaction.models.backbones.c3d import C3D      # direct import, no registry
  │  from mmaction.models.heads.i3d_head import I3DHead
  │  backbone, cls_head = load_weights(ckpt_path)
  │  print("[c3d_server] READY")
  │
  │  loop:
  │    ← stdin  line: {"frames_b64": "<base64 uint8 T×H×W×3>", "shape": [T,H,W,3]}
  │    → stdout line: {"score_low": 0.352, "score_high": 0.648}
  │
  │  ← {"__EXIT__": true}  →  clean shutdown
```

The subprocess starts once at `STARHERiskModel.__init__()` and is reused for all subsequent predictions. `STARHERiskModel.close()` sends `{"__EXIT__": true}` and waits for the process to terminate cleanly.

The subprocess does **not** need the runtime `mmcv._ext` stub or `inspect.getmodule` patches required by the RTMDet runner — the C3D and I3DHead classes do not invoke mmcv C extension ops. Instead, it relies on the three **permanent venv patches** applied once by `scripts/setup.sh` (see [mmaction2 Venv Patches](#mmaction2-venv-patches) below).

#### Loading the model (bypassing the mmengine registry)

`init_recognizer()` routes through the mmengine registry, which conflicts with mmdet's registry under Python 3.13 (duplicate class names raise `KeyError`). The subprocess bypasses this by importing the classes directly and loading checkpoint weights by key prefix:

```python
from mmaction.models.backbones.c3d import C3D
from mmaction.models.heads.i3d_head import I3DHead

backbone = C3D(dropout_ratio=0.5)
cls_head = I3DHead(num_classes=2, in_channels=4096, dropout_ratio=0.5)

ckpt  = torch.load(ckpt_path, map_location='cpu', weights_only=False)
state = ckpt.get('state_dict', ckpt)
backbone.load_state_dict(
    {k[len('backbone.'):]: v for k, v in state.items() if k.startswith('backbone.')}
)
cls_head.load_state_dict(
    {k[len('cls_head.'):]: v for k, v in state.items() if k.startswith('cls_head.')}
)
```

The key prefixes `backbone.` and `cls_head.` are the exact format produced by mmaction2's training checkpointer.

### C3D Architecture

```
Input: (N, 3, 16, 112, 112)   N clips × 3 channels × 16 frames × 112×112 px
────────────────────────────────────────────────────────────────────────────────
Backbone (C3D):
  conv1a(3→64,  k=3³, pad=1) → ReLU → MaxPool3d(1×2×2, stride 1×2×2)
  conv2a(64→128, k=3³, pad=1) → ReLU → MaxPool3d(2×2×2)
  conv3a(128→256, k=3³, pad=1) → ReLU
  conv3b(256→256, k=3³, pad=1) → ReLU → MaxPool3d(2×2×2)
  conv4a(256→512, k=3³, pad=1) → ReLU
  conv4b(512→512, k=3³, pad=1) → ReLU → MaxPool3d(2×2×2)
  conv5a(512→512, k=3³, pad=1) → ReLU
  conv5b(512→512, k=3³, pad=1) → ReLU → MaxPool3d(2×2×2)
  AdaptiveAvgPool3d(1,1,1) → flatten → (N, 8192)
  fc6 Linear(8192→4096) → ReLU → Dropout(p=0.5)   ← inside backbone.forward()
  fc7 Linear(4096→4096) → ReLU                     ← inside backbone.forward()
Output: (N, 4096)
────────────────────────────────────────────────────────────────────────────────
Head (I3DHead):
  Dropout(p=0.5) → fc_cls Linear(4096→2)
Output: (N, 2) logits [p_low_risk, p_high_risk]
```

> **Critical**: `fc6`, `fc7`, and their activations are **inside `C3D.forward()`** — this is the mmaction2 convention, not the original C3D paper. `I3DHead` only adds its own dropout + `fc_cls`. Do not replicate `fc6`/`fc7` outside the backbone.

### Preprocessing Pipeline

Both backends (`_c3d_runner.py` and `c3d.py`) share identical preprocessing functions, validated **bit-for-bit** against mmaction2's official transforms `SampleFrames + Resize + CenterCrop + FormatShape` on the same input (diff max = 0.000000, June 22, 2026).

**Input**: `(T, H, W, 3)` uint8 RGB numpy array — fan-cropped grayscale frames from prepUS, replicated into 3 identical channels (R=G=B) to match the pseudo-RGB convention used during training (grayscale `video.mp4` read by Decord, which returns 3-channel frames by default).

#### Step 1 — Frame sampling (`_sample_clips`)

Exact reproduction of `SampleFrames._get_test_clips` for 3D recognizers (mmaction2 1.2.0):

```python
CLIP_LEN, NUM_CLIPS = 16, 10

def _sample_clips(total: int) -> np.ndarray:
    """Returns (NUM_CLIPS, CLIP_LEN) int array of frame indices."""
    max_offset = max(total - CLIP_LEN, 0)
    if NUM_CLIPS > 1:
        offset_between = max_offset / float(NUM_CLIPS - 1)
        offsets = np.round(np.arange(NUM_CLIPS) * offset_between).astype(int)
    else:
        offsets = np.array([max_offset // 2], dtype=int)
    # out_of_bound_opt='loop': wrap indices for videos shorter than CLIP_LEN
    return np.stack([np.arange(o, o + CLIP_LEN) % total for o in offsets])
```

**Formula details:**
- Clips are distributed from offset `0` to `max_offset = total − 16`, with uniform spacing `max_offset / (NUM_CLIPS − 1)`.
- `np.round()` (not `floor()` or `int()`) — matches mmaction2 exactly, matters for certain frame counts.
- The modulo `% total` handles short videos (`total < CLIP_LEN`) via wrapping (`out_of_bound_opt='loop'` semantics).

**Example** — `total=146` (`max_offset=130`, `step=130/9≈14.44`):
```
offsets = [0, 14, 29, 43, 58, 72, 87, 101, 116, 130]
```

> **Breaking change fixed June 22, 2026** — the prior formula was `avg = (T−16+1) / 10`, offset `base × avg + avg/2 − 0.5` (clips centered within equal segments). For `T=146` this produced `[6, 19, 32, 45, 58, 71, 84, 97, 110, 123]` — completely different clips from mmaction2. The tensor-level diff reached 169 pixel values, fully invalidating inference. **Both `_c3d_runner.py` and `c3d.py` were corrected.**

#### Step 2 — Resize to 128 px short side (`_resize_shortest`)

```python
RESIZE_SIZE = 128

def _resize_shortest(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    if h <= w:
        nh, nw = RESIZE_SIZE, max(1, round(w * RESIZE_SIZE / h))
    else:
        nh, nw = max(1, round(h * RESIZE_SIZE / w)), RESIZE_SIZE
    return cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
```

Operates on **uint8 pixels** (not float32) using `cv2.INTER_LINEAR` — identical to mmaction2's `Resize(scale=(-1, 128))` internal implementation.

#### Step 3 — Center crop to 112×112

```python
CROP_SIZE = 112
y = (h - CROP_SIZE) // 2   # integer division — matches mmaction2 CenterCrop
x = (w - CROP_SIZE) // 2
cropped = frame[y:y+CROP_SIZE, x:x+CROP_SIZE]
```

#### Step 4 — Mean subtraction and tensor assembly

```python
MEAN = np.array([104.0, 117.0, 128.0], dtype=np.float32)  # BGR ImageNet means

# Per clip (16 frames, shape 112×112×3 each):
clip_arr = np.stack(cropped_frames).astype(np.float32) - MEAN  # (16, 112, 112, 3)
clip_t   = clip_arr.transpose(3, 0, 1, 2)                      # (3, 16, 112, 112)

# Final tensor (all 10 clips stacked):
tensor = torch.from_numpy(np.stack([clip_t_i for i in range(NUM_CLIPS)]))  # (10, 3, 16, 112, 112)
```

**No division by 255.** `std = [1, 1, 1]`. The values `[104, 117, 128]` are **BGR** ImageNet channel means, consistent with the training config: `ActionDataPreprocessor(mean=[104,117,128], std=[1,1,1], to_rgb=False)`. Since input frames are grayscale (R=G=B), the channel order does not affect inference numerically.

### Inference

```python
@torch.no_grad()
def _infer(backbone, cls_head, frames: np.ndarray, device: str) -> tuple[float, float]:
    tensor = _preprocess(frames).to(device)               # (10, 3, 16, 112, 112)
    feats  = backbone(tensor)                             # (10, 4096) — includes fc6+fc7
    logits = cls_head.fc_cls(cls_head.dropout(feats))    # (10, 2)
    probs  = F.softmax(logits, dim=1).mean(dim=0)        # (2,)
    return float(probs[0]), float(probs[1])               # score_low, score_high
```

`average_clips='prob'` (mmaction2 training default): **softmax is applied per clip**, then averaged over the 10 clips. This differs from `average_clips='score'` (average raw logits first), which would yield different results. `probs[1]` is the final `risk_score ∈ [0, 1]`. The decision threshold (default `0.5`, configurable via `RISK_THRESHOLD` in `config.py`) is applied by `starhe_risk.py`, not by the runner.

### Reproducibility

> **Current default: `DETERMINISTIC_INFERENCE = False`.** As of the July 2026
> reproducibility campaign the flag is **off** so the pipeline runs in its native
> mode (device from `INFERENCE_DEVICE = "auto"`, float32). This is intentional: the
> CPU/float64 forcing below maximizes *cross-OS* reproducibility but moves *away*
> from Jérémy's native training environment (Linux + GPU, float32). Set it back to
> `True` when cross-platform bit-identity matters more than matching Jérémy.

When `DETERMINISTIC_INFERENCE = True`, the subprocess forces:

```python
device = "cpu"                                 # override — no CUDA/MPS variance
torch.set_num_threads(1)                       # single-threaded BLAS
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.deterministic   = True
torch.use_deterministic_algorithms(True, warn_only=True)
```

Without this, float32 accumulation differences between MKL (Linux/Windows) and Accelerate (macOS ARM) cause ~0.002 score variance per inference. With `DETERMINISTIC_INFERENCE=True`, scores are **bit-identical across all platforms** for the same input file. Cost: ~2–3× slower on CPU.

### Backend Selection

`C3D_BACKEND` in `config.py` (default: `"mmaction2"`) selects the inference backend:

| Value | File | Mode | Requires |
|---|---|---|---|
| `"mmaction2"` | `ai/models/_c3d_runner.py` | Persistent subprocess, server mode | mmaction2 1.2.0 installed `--no-deps` + 3 venv patches |
| `"pytorch"` | `ai/models/c3d.py` | In-process, pure PyTorch | PyTorch only — no mmaction2 |

`"pytorch"` is the automatic fallback if mmaction2 is unavailable or if the subprocess fails to start. **Both backends share the same `_sample_clips`, `_resize_shortest`, and `_preprocess` functions** — any preprocessing change must be applied to both files.

### mmaction2 Venv Patches

mmaction2 1.2.0 is installed without its dependency tree (`pip install mmaction2 --no-deps`) to avoid conflicts with the plugin's PyTorch version. Three file patches fix import errors and are applied automatically by `scripts/setup.sh`:

| File (relative to `.venv/lib/…/mmaction/`) | Problem | Patch |
|---|---|---|
| `models/localizers/__init__.py` | Imports `DRN`, which is absent from wheel 1.2.0 | Remove the `DRN` import line |
| `models/roi_heads/__init__.py` | Registry conflict with mmdet raises `AssertionError` | Add `AssertionError` to the `except` clause |
| `models/task_modules/__init__.py` | Same registry conflict | Same fix |

To verify the patches are correctly applied:
```bash
source pythonCode/modules/starhe_plugin/.venv/bin/activate
python -c "from mmaction.models.backbones.c3d import C3D; print('mmaction2 OK')"
```

If this raises an `ImportError`, re-run `make setup` or `scripts/setup.sh`.

### Validation (June 22, 2026)

| Test | Input | Outcome |
|---|---|---|
| Plugin vs original mmaction2 pipeline (PyAV decoding + mmaction2 transforms) | `data_test`, 24 patients | **Score delta = 0.000000** for all 24 patients — bit-identical |
| Our `_preprocess` tensor vs mmaction2 `SampleFrames+Resize+CenterCrop+FormatShape` | Single patient (146 frames) | **diff max = 0.000000** |
| cv2 VideoCapture vs PyAV frame decoder | `data_test`, 6 patients | **0 pixel difference** |

The three results together confirm the plugin is mathematically equivalent to running the original training inference code on the same input file.

### Training Distribution (context)

The C3D was trained on Jean Zay (IDRIS, Python 3.10, mmaction2 1.2.0) by J. Nizard:

```
DICOM → ffmpeg MP4 → prepUS.removeLayoutFile
      → video.mp4 (fan-cropped, grayscale, mp4v codec, static UI removed)
      → DecordInit + SampleFrames(clip_len=16, num_clips=10, test_mode=True)
      → DecordDecode
      → Resize(scale=(-1,128)) → CenterCrop(112) → FormatShape(NCTHW)
      → ActionDataPreprocessor(mean=[104,117,128], std=[1,1,1], to_rgb=False)
      → C3D backbone + I3DHead → cross-entropy loss
Checkpoint selected: best_acc_mean_cls_f1_epoch_14.pth (best validation mean-class F1)
```

The `video.mp4` files produced by `cv2.VideoWriter(mp4v)` on Jean Zay Linux differ bit-for-bit from files produced on macOS ARM (different FFmpeg linked to OpenCV). This is the sole source of ~10% MAE vs `pred_test.pkl` when using locally regenerated prepUS crops — not a code defect. The MP4 bypass mode (`PREPUS_BYPASS_MP4=True`) reduces this to ~8% by eliminating the VideoWriter roundtrip; see [prepUS Preprocessing](#prepus-preprocessing-dicomprepus_bridgepy) below.

### Historical Fix Log

| Date | File(s) | Fix |
|---|---|---|
| May 27–28, 2026 | `c3d.py`, `pipeline.py` | `_resize_shortest`: `F.interpolate(float32)` → `cv2.resize(uint8, INTER_LINEAR)`. RISK input: raw DICOM frames → `crop_only_frames` from prepUS (fan crop, grayscale→pseudo-RGB). |
| June 5, 2026 | `dicom/prepus_bridge.py`, `config.py` | MP4 bypass mode (`PREPUS_BYPASS_MP4`): pure numpy prepUS path, eliminates cross-OS mp4v encoder non-determinism. |
| June 22, 2026 | `_c3d_runner.py`, `c3d.py` | `_sample_clips`: wrong formula `avg=(T−16+1)/10` + `avg/2−0.5` offset → correct mmaction2 formula `step=max_offset/(NUM_CLIPS−1)`, `offsets=round(arange(NUM_CLIPS)×step)`. Tensor diff was up to 169 pixel values before fix; 0.000000 after. |

---

## STARHE-DETECT: RTMDet Detection Pipeline

STARHE-DETECT localizes hepatic lesions in ultrasound frames using **RTMDet-L** (Real-Time Multi-scale Detector), a one-stage anchor-free object detector from mmdet 3.3.0. It outputs bounding boxes with confidence scores for a single class (`tumor`), one detection list per input frame. At inference the plugin reproduces the exact training pipeline bit-for-bit, validated to produce **max\_bbox\_diff = 0.0 px and max\_score\_diff = 0.0** against the official mmdet reference (`init_detector` + `inference_detector`) on 1 453 frames across the full 24-video test dataset.

### Checkpoint

| File | Size | Notes |
|---|---|---|
| `best_coco_bbox_mAP_50_iter_2100.pth` | 439 MB | Best checkpoint by `coco/bbox_mAP_50`, saved at iteration 2 100 of a 3 300-iteration training run on Jean Zay (IDRIS). Contains model `state_dict` + optimizer state + mmengine metadata buffers. |

The checkpoint is loaded with `weights_only=False` (required: the `.pth` contains `mmengine.logging.history_buffer.HistoryBuffer` and NumPy globals which PyTorch 2.6+ rejects under `weights_only=True`). The `data_preprocessor.*` keys are stripped from `state_dict` before loading since normalization is handled manually — not via `DetDataPreprocessor`.

### Training Distribution

RTMDet was fine-tuned in COCO format on `cropped_videos/` — **fan-shaped ultrasound sector crops** produced by prepUS, identical in format to the `crop_only_frames` fed at inference. Dimensions are non-square and vary per file. Single class: `tumor`.

Key training hyperparameters: AdamW (lr=0.001), QualityFocalLoss + GIoULoss, DynamicSoftLabelAssigner (topk=13). Augmentations: CachedMosaic → RandomResize(0.1–2.0×) → RandomCrop(640) → YOLOXHSVRandomAug → RandomFlip → Pad(114, 640×640) → CachedMixUp. Stage 2 (no Mosaic/MixUp) activates after iteration 2 290.

### RTMDet Architecture

```
Input: (N, 3, 640, 640)   float32 or float64 (normalized, BGR order)
────────────────────────────────────────────────────────────────────────────────
Backbone (CSPNeXt-L):
  arch='P5', deepen_factor=1, widen_factor=1, channel_attention=True
  expand_ratio=0.5, act=SiLU, norm=SyncBN (→ BN at inference)
  Output: 3 feature maps at strides 8 / 16 / 32
    P3: (N, 256, 80, 80)
    P4: (N, 512, 40, 40)
    P5: (N,1024, 20, 20)
────────────────────────────────────────────────────────────────────────────────
Neck (CSPNeXtPAFPN):
  in_channels=[256, 512, 1024], out_channels=256
  num_csp_blocks=3, expand_ratio=0.5, act=SiLU, norm=SyncBN
  Path-Aggregation FPN: top-down then bottom-up merging
  Output: 3 feature maps, all 256 channels
    (N, 256, 80, 80) / (N, 256, 40, 40) / (N, 256, 20, 20)
────────────────────────────────────────────────────────────────────────────────
Head (RTMDetSepBNHead):
  in_channels=256, feat_channels=256, stacked_convs=2
  anchor_generator: MlvlPointGenerator(strides=[8,16,32], offset=0)
  bbox_coder: DistancePointBBoxCoder
  pred_kernel_size=1, share_conv=True, with_objectness=False
  num_classes=1, act=SiLU, norm=SyncBN
  Separate BN for cls and reg branches
────────────────────────────────────────────────────────────────────────────────
Post-processing (test_cfg):
  score_thr=0.001, nms=dict(type='nms', iou_threshold=0.65)
  nms_pre=30000, max_per_img=300, min_bbox_size=0
```

`SyncBN` is replaced by `BN` at inference (via `_replace_syncbn()` in `_rtmdet_runner.py`) since `SyncBN.forward` requires `dist.is_initialized()` in multi-GPU contexts.

### Subprocess Architecture

All mmdet/mmcv/mmengine imports live exclusively inside a **persistent subprocess** (`_rtmdet_runner.py --mode server`) so the main Python 3.13 process never loads these packages (which require compiled C extensions absent from Python 3.13 wheels). `STARHEDetectModel` in `ai/starhe_detect.py` is the parent-side wrapper.

```
STARHEDetectModel (main process)
  │
  │  subprocess.Popen([python, _rtmdet_runner.py,
  │                    --config  models/rtmdet_starhe.py,
  │                    --ckpt    models/best_coco_bbox_mAP_50_iter_2100.pth,
  │                    --mode    server,
  │                    --score-thr 0.70,
  │                    --deterministic         # → CPU + float64
  │  ], stdin=PIPE, stdout=PIPE, text=True, bufsize=1)
  │
  ▼
_rtmdet_runner.py (subprocess)
  │
  │  → MODELS.build(cfg.model)               # bypasses init_detector
  │  → _load_ckpt(model, ckpt)               # strips data_preprocessor.* keys
  │  → model.double().eval()                 # float64 in deterministic mode
  │  → print("[rtmdet_server] READY {hw_info_json}")
  │
  │  loop (newline-delimited JSON on stdin/stdout):
  │    ← {"frames_b64": ["<base64>", ...], "shapes": [[H,W,3],...], "score_thr": 0.70}
  │    → [[{"bbox":[x0,y0,x1,y1], "score":0.83, "label":"tumor"}, ...], ...]
  │
  │  ← "__EXIT__"  →  clean shutdown (proc.wait(10s) then kill)
```

Key design choices:
- **`MODELS.build()` instead of `init_detector()`** — `init_detector` internally calls `pkgutil.find_loader("mmcv._ext")`, which requires a C extension absent on Python 3.13. `MODELS.build()` bypasses this chain entirely while loading the exact same model weights.
- **No disk I/O** — frames are transmitted as raw BGR bytes encoded in base64 (no `cv2.imwrite`/`cv2.imread` roundtrip), eliminating JPEG artifacts and filesystem latency.
- **Line-buffered** — `text=True` + `bufsize=1` ensures each `print(…, flush=True)` in the runner is immediately readable on the parent's `stdout.readline()`.

### Forward Pass

```python
# Inside _rtmdet_runner.py — normalized (1,3,640,640) tensor + meta dict
with torch.no_grad():
    feats      = model.backbone(tensor)
    neck_feats = model.neck(feats)
    head_outs  = model.bbox_head(neck_feats)
    results    = model.bbox_head.predict_by_feat(
        *head_outs,
        batch_img_metas=[meta],
        rescale=True    # divides bboxes by scale_factor → ori_shape space
    )
```

`predict_by_feat` decodes bboxes from distance predictions (`DistancePointBBoxCoder`), clips them to the padded canvas bounds (`640×640`), applies NMS (IoU=0.65), truncates to `max_per_img=300`, then if `rescale=True` divides coordinates by `scale_factor` to map back to original frame dimensions.

Score filtering after `predict_by_feat`:

```python
return [
    {"bbox": [float(x) for x in bb], "score": float(sc), "label": "tumor"}
    for bb, sc in zip(bboxes, scores)
    if round(float(sc), 6) >= score_thr
]
```

The 6-decimal `round()` guards against cross-platform BLAS accumulation differences (MKL on Windows/Linux vs Accelerate on macOS ARM): without rounding, a score of `0.6999999991` on macOS may compute as `0.7000000002` on Windows, changing the detection result at the `0.70` threshold.

### Temporal Subsampling and Propagation

`DETECT_EVERY_N = 4` (default in `config.py`) reduces inference cost by 4×. In `pipeline.py`:

```python
stride  = max(1, DETECT_EVERY_N)
sampled = list(range(0, n_frames_total, stride))   # [0, 4, 8, 12, ...]

for b_start in range(0, len(sampled), batch_size):
    batch_idx  = sampled[b_start : b_start + batch_size]
    batch_dets = detect_model.predict_batch([frames[i] for i in batch_idx])

    for idx, frame_dets in zip(batch_idx, batch_dets):
        for j in range(idx, min(idx + stride, n_frames_total)):
            detections_per_frame[j] = frame_dets   # propagate to next stride-1 frames
```

The detection from frame `n` is copied as-is to frames `n+1` … `n+stride−1`. Since tumors are anatomical structures persistent across adjacent frames at ~20 fps, inter-frame positional drift is clinically negligible for the intended screening use case. Set `DETECT_EVERY_N=1` to disable subsampling.

### Batch Inference

`STARHEDetectModel.predict_batch()` base64-encodes N BGR frames and sends one JSON request; the runner stacks all preprocessed tensors into a single `(N, 3, 640, 640)` batch for one forward pass:

```python
# Wrapper side — frames arrive as RGB
frames_b64 = [base64.b64encode(cv2.cvtColor(f, cv2.COLOR_RGB2BGR).tobytes()).decode()
               for f in frames]
req = json.dumps({"frames_b64": frames_b64, "shapes": [list(f.shape) for f in frames_bgr],
                   "score_thr": score_thr})
self._proc.stdin.write(req + "\n")
resp = json.loads(self._proc.stdout.readline())   # [[dets], [dets], ...]
```

Each frame carries its own `meta` dict (different `ori_shape` and `scale_factor`), allowing frames with different original resolutions to be batched together.

### Subprocess Warmup Strategy

Loading RTMDet from disk takes ~4 seconds on CPU. `pipeline.py` starts the subprocess in a **background daemon thread immediately after frame extraction**, overlapping with prepUS preprocessing and STARHE-RISK inference:

```python
detect_box = []
def _warm():
    detect_box.append(STARHEDetectModel())
threading.Thread(target=_warm, daemon=True).start()

# ... prepUS + RISK inference run here (~4–8 s) ...

detect_thread.join()       # typically a no-op: subprocess already warm
detect_model = detect_box[0]
```

This overlap reduces end-to-end pipeline latency by ~4 seconds on CPU hardware.

### Adaptive Batch Size

The subprocess reports available hardware memory **after model loading** (so the ~439 MB model footprint is already deducted), and `STARHEDetectModel` derives an optimal batch size:

| Device | Formula | Max |
|---|---|---|
| CUDA | `floor(vram_free_mb × 0.80 / mem_per_frame_mb)` | VRAM-dependent |
| CPU / MPS | `floor(ram_free_mb × 0.35 / mem_per_frame_mb)` | 16 |

Set `DETECT_BATCH_SIZE = <int>` in `config.py` to override auto-detection.

### Reproducibility (`DETERMINISTIC_INFERENCE`)

> **Current default: `False`** (see the RISK reproducibility note above — off to
> match Jérémy's native Linux/GPU environment). The description below applies when
> the flag is set back to `True`.

When `DETERMINISTIC_INFERENCE = True`, the subprocess is launched with `--deterministic`:

| Setting | Value | Rationale |
|---|---|---|
| Device | CPU (forced) | Eliminates CUDA/MPS numerical variance |
| dtype | float64 (`model.double()`) | Reduces cross-OS BLAS error from ~1e-4 to ~1e-13 per op |
| Threads | 1 (`set_num_threads(1)`) | Deterministic accumulation order |
| TF32 | Disabled | `allow_tf32 = False` on CUDA/cuDNN |

After 50+ convolutional layers the residual cross-platform error is ~1e-9, far below the 5×10⁻⁷ tolerance enforced by the 6-decimal `round()` in score filtering. Result: bit-identical detections across macOS ARM (Accelerate), Linux (MKL), and Windows (MKL).

### Backend Selection

`DETECT_BACKEND` in `config.py` (default: `"rtmdet"`) selects the detection backend:

| Value | Runner | Notes |
|---|---|---|
| `"rtmdet"` | `ai/models/_rtmdet_runner.py` | Production default. Persistent server, batch inference, validated bit-exact. |
| `"dino"` | `ai/models/_dino_runner.py` | DINO-DETR alternative. No server mode. Requires `ai/vendor/starhe/` vendored package. |

### Output Format

Each `predict_batch()` call returns a list of N detection lists, one per input frame:

```python
[
    [   # frame 0
        {"bbox": [x0, y0, x1, y1], "score": 0.83, "label": "tumor"},
        {"bbox": [x0, y0, x1, y1], "score": 0.71, "label": "tumor"},
    ],
    [],  # frame 1 — no detection above score_thr
    ...
]
```

`bbox` coordinates are in **`crop_only_frames` space** (fan-shaped sector crop). `pipeline.py` remaps to **DICOM original space** with a plain offset:

```python
# info["crop"] = {"xmin": ..., "ymin": ...}
for det in dets:
    det["bbox"][0] += info["crop"]["xmin"];  det["bbox"][2] += info["crop"]["xmin"]
    det["bbox"][1] += info["crop"]["ymin"];  det["bbox"][3] += info["crop"]["ymin"]
```

No inverse polar transform is needed: RTMDet was trained on the fan-shaped crop directly.

---

## prepUS Preprocessing (`dicom/prepus_bridge.py`)

prepUS is the ultrasound image preprocessor from MEDomics. It is **vendored** in `third_party/prepUS/` to avoid an external dependency.

### What prepUS does

- Detects and removes static elements from the ultrasound machine interface (text, rulers, borders) by analyzing temporal pixel variability.
- Crops the US cone to remove black margins.
- Performs an inverse scan conversion (backscan): reconstructs the image in a 512×512 Cartesian space, correcting the ultrasound sector distortion.

### Code usage

```python
crop_frames, info = preprocess_with_prepus(
    frames_rgb,          # (T, H, W, 3) uint8 RGB
    fps=dicom_fps,
    backscan_width=512,
    backscan_height=512,
)
```

Returns a 2-tuple `(crop_frames, info_dict)`:
- `crop_frames`: `(T, H_crop, W_crop)` uint8 grayscale — fan-shaped sector crop (`video.mp4` from prepUS), used for both C3D and RTMDet inference
- `info_dict`: keys `crop` (xmin/ymin/xmax/ymax) — used to remap RTMDet bboxes back to DICOM coordinates

> **Note** : the backscan (Cartesian 512×512 reconstruction) is no longer computed. Both models were trained on fan-shaped crop data (`video.mp4` / `cropped_videos`), not on Cartesian backscan. Removing the backscan step simplifies the bridge without affecting inference quality.

### Internal implementation

Two backends are available, controlled by the `PREPUS_BYPASS_MP4` flag in `config.py`.

> **Current default: `PREPUS_BYPASS_MP4 = False`** (Mode A). As of the July 2026
> reproducibility campaign, prepUS runs through the mp4v roundtrip because that is
> the exact path the STARHE models saw at training time (Jérémy's crops carry mp4v
> compression artifacts). Mode B (pure numpy) is cross-OS bit-identical but produces
> *cleaner* crops that are slightly off the training distribution — set it back to
> `True` when cross-platform portability matters more than matching Jérémy.

**Mode A — MP4 roundtrip** (`preprocess_with_prepus`, legacy, **current default**):

1. Export numpy frames → temporary MP4 (OpenCV `VideoWriter`, codec `mp4v`, grayscale)
2. Call `prepUS.cli.removeLayoutFile(mp4, out_dir, back_scan_conversion=True, ...)`
3. Read `out_dir/video.mp4` (fan-shaped crop) → numpy `(T, H_crop, W_crop)`
4. Read `out_dir/info.json` → ROI dict
5. Cleanup of temporary directory

> ⚠️ Mode A calls `cv2.VideoWriter(mp4v)`, whose bitstream depends on the FFmpeg
> build linked into OpenCV — so the same DICOM yields **different** crops across
> macOS / Linux / Windows. This is acceptable (and intended) when reproducing
> Jérémy on a single Linux host, but breaks cross-OS bit-identity.

**Mode B — MP4 bypass** (`preprocess_with_prepus_inmem`, enabled via `PREPUS_BYPASS_MP4=True`):

1. Convert numpy RGB frames → grayscale (cv2.cvtColor `RGB2GRAY` — BT.601, identical to the path read by `loadvideo` on a grayscale MP4)
2. Run the prepUS algorithm in-process on numpy: variability mask → morphological denoise → `crop_single_object` → `find_linear_fov` (with recursive retry identical to the reference) → FOV mask → `applyMask`
3. Return `(crop_frames, info)` directly — no intermediate `VideoWriter` / `VideoCapture`, no temp folder

Mode B is algorithmically strictly equivalent to `removeLayoutFile(..., back_scan_conversion=True)` but eliminates the cross-OS non-portability of the mp4v encoder (see C3D validation section above).

> **Warning**: prepUS must be installed with `--no-deps` to avoid conflicts with the venv's OpenCV version. The `run_tkinter.ps1` script handles this automatically.

---

## DICOM Decoding via weasis-dcm2png (`dicom/weasis_bridge.py`)

### Why

`pydicom.pixel_array` applies **neither the Modality LUT nor the VOI LUT** from the DICOM file. Jérémy's training pipeline used **Weasis** (open-source clinical DICOM viewer), which applies both LUTs — exactly as a radiologist sees the image on their console. Doing the same at inference brings the input distribution closer to what was seen during training.

### How

A Java mini-project **vendored** in [third_party/weasis-dcm2png/](third_party/weasis-dcm2png/) (pom.xml + `Dcm2Png.java` + JAR + OpenCV/DCM4CHE native libs) exposes a headless CLI:

```bash
java -Djava.library.path=third_party/weasis-dcm2png/dist/native \
     --enable-native-access=ALL-UNNAMED \
     -jar third_party/weasis-dcm2png/dist/weasis-dcm2png.jar \
     /path/to/file.dcm /out/dir/
# stdout: fps=<float> / frames=<int>
# /out/dir/: one PNG per frame, LUTs applied
```

The Python bridge [dicom/weasis_bridge.py](pythonCode/modules/starhe_plugin/dicom/weasis_bridge.py) exposes:

| Function | Role |
|---|---|
| `weasis_available() -> bool` | Checks JAR presence + working JVM (`java -version`) |
| `export_dicom_to_pngs_weasis(dicom, out_dir) -> (fps, n_frames)` | Java subprocess, parses stdout |
| `frames_via_weasis(dicom, work_dir=None) -> (frames_rgb, fps)` | DICOM → PNG → numpy `(T, H, W, 3)` uint8, auto cleanup |

### Pipeline branching

Step 3 of [pipeline.py](pythonCode/modules/starhe_plugin/pipeline.py) tries Weasis first then automatically falls back to pydicom:

```python
if USE_WEASIS_EXPORT and weasis_available():
    try:
        frames_rgb, weasis_fps = frames_via_weasis(dicom_path)
        if weasis_fps > 0:
            dicom_fps = weasis_fps      # prefer the value reported by Weasis
    except Exception as exc:
        go_print("warning", f"weasis-dcm2png failed ({exc}) — fallback pydicom")
        frames_rgb = None

if frames_rgb is None:
    # Legacy path: extract_frames(ds) + frame_to_uint8
    ...
```

Flag in `config.py`:

| Constant | Default | Effect |
|---|---|---|
| `USE_WEASIS_EXPORT` | `True` | Enables the Weasis chain with automatic pydicom fallback |

**Fallback cases**:
- Java absent from PATH (`shutil.which("java")` returns `None`)
- Non-functional JVM (on macOS, `/usr/bin/java` is an installer stub → install a real JVM, e.g. `brew install openjdk@17`)
- Transfer syntax not supported by the JAR (notably **JPEG 2000** — handled by pydicom via pylibjpeg)
- Java subprocess exit ≠ 0 or empty stdout

The fallback is silent on the UI side (warning in the SSE console) and preserves the prior behavior bit-for-bit. The flag is conservative (default `True` but no regression if Java is missing).

### Standalone validation script (`test_dicom_pipeline.py`)

`test_dicom_pipeline.py` at the project root runs the full DICOM → Weasis → ffmpeg MP4 → prepUS → C3D + RTMDet chain outside React/Go, useful for reproducing a case and comparing the risk score to the runtime output:

```bash
python test_dicom_pipeline.py /path/to/file.dcm            # RISK + DETECT
python test_dicom_pipeline.py /path/to/file.dcm --no-detect  # RISK only
```

If the JAR or Java is missing, the script also switches to the pydicom path (same rules as `pipeline.py`).

---

## DICOM → MP4 Conversion: First Pipeline Step

> This section documents the preprocessing step that converts raw DICOM cine-clips into AV1-encoded MP4 files. These MP4s are the direct input to `prepUS.removeLayoutFile`, which produces the `video.mp4` fan-cropped files on which both STARHE-RISK (C3D) and STARHE-DETECT (RTMDet) were trained. Batch reproduction and validation are handled by `scripts/dicom_batch_to_mp4.py`.

### Conversion Chain

```
DICOM (.dcm) / AVI (.avi)
  │
  ├─ Weasis path  (Java available + transfer syntax ≠ J2K lossless)
  │    Java → weasis-dcm2png.jar → one PNG per frame (Modality + VOI LUT applied)
  │
  └─ pydicom fallback  (J2K, no Java, or Weasis subprocess error)
       reader.extract_frames() ─┬─ ds.pixel_array      (nominal)
                                ├─ ds.decompress()      (pydicom 3.x)
                                └─ _extract_j2k_raw_scan()  (raw J2K byte scan via PIL)
       → one PNG per frame (no LUT applied)
  │
  ffmpeg -c:v libsvtav1 -crf 30 -preset 8 -pix_fmt yuv420p → .mp4
  (exception: 06-0018-D-M uses libx264 to match its reference format)
```

### FPS Resolution

FPS is read from DICOM metadata with the following priority (implemented identically in `pipeline.py` and `scripts/dicom_batch_to_mp4.py`):

| Priority | Tag | Keyword | Formula |
|---|---|---|---|
| 1 | `(0008,2144)` | `RecommendedDisplayFrameRate` | direct (fps) |
| 2 | `(0018,0040)` | `CineRate` | direct (fps) |
| 3 | `(0018,1063)` | `FrameTime` | `1000 / FrameTime_ms` |
| — | — | none found | `RuntimeError` — never assume a default |

Using only `FrameTime` gives wrong values for files where `RecommendedDisplayFrameRate` differs. Example: `03-0015-D-C` — `FrameTime=29 ms` → 34 fps; `RecommendedDisplayFrameRate=20` → 20 fps (correct). The `RuntimeError` fallback ensures every DICOM file explicitly declares its own frame rate instead of silently producing incorrect output.

### Output Resolution (Scale Rule)

Scale thresholds applied to the DICOM frame height (`rows`):

| DICOM height | Target height | Target width |
|---|---|---|
| `rows > 750` | 720 px | nearest-even to `cols × 720 / rows` |
| `480 < rows ≤ 750` | 480 px | nearest-even to `cols × 480 / rows` |
| `rows ≤ 480` | 360 px | nearest-even to `cols × 360 / rows` |

**Nearest-even width formula** — Python's `round()` uses banker's rounding (round-half-to-even), which can produce unintuitive results when `tw_raw` lands exactly at mid-point. The formula below avoids this:

```python
import math

def target_dimensions(rows: int, cols: int) -> tuple[int, int]:
    if rows > 750:
        th = 720
    elif rows > 480:
        th = 480
    else:
        th = 360
    tw_raw = cols * th / rows
    tw_lo = math.floor(tw_raw / 2) * 2   # largest even integer ≤ tw_raw
    tw = tw_lo if (tw_raw - tw_lo) <= 1.0 else tw_lo + 2
    return tw, th
```

The `≤ 1.0` condition: since `tw_lo` is the largest even ≤ `tw_raw`, the offset `(tw_raw - tw_lo)` is in `[0, 2)`. If ≤ 1.0, round down to `tw_lo`; otherwise round up to `tw_lo + 2`. ffmpeg requires even dimensions for `yuv420p`; odd widths cause a fatal encode error.

### AV1 Encoding Parameters

```bash
ffmpeg \
  -framerate <fps_from_dicom> \
  -i frame_%05d.png \
  -c:v libsvtav1 -crf 30 -preset 8 \
  -pix_fmt yuv420p \
  output.mp4
```

| Parameter | Value | Reason |
|---|---|---|
| `-c:v libsvtav1` | AV1 (SVT-AV1) | Better quality/size ratio than h264 at the same CRF; fully deterministic output |
| `-crf 30` | Quality factor | Good quality for grayscale ultrasound content |
| `-preset 8` | Speed vs quality | Fast encoding; preset 1 = best quality + slowest |
| `-pix_fmt yuv420p` | Pixel format | Required for broad player/decoder compatibility; grayscale content encodes as luma-channel only |

**Exception**: `06-0018-D-M` uses `libx264` (h264) to match its reference encoding format.

### JPEG 2000 Lossless Fallback

Files with DICOM transfer syntax `1.2.840.10008.1.2.4.90` (JPEG 2000 Lossless) cause Weasis (dcm4che3) to fail with:

```
java.lang.ClassCastException: class org.dcm4che3.data.Value$1 cannot be cast to
class org.dcm4che3.data.BulkData
```

This is a dcm4che3 limitation with undefined-length J2K segment encapsulation. The fallback sequence (identical in `pipeline.py` and `scripts/dicom_batch_to_mp4.py`):

1. **Detect** the failure: check for `"BulkData"` or `"ClassCastException"` in the Java subprocess output string.
2. **Clear partial PNGs** — Weasis may have written some frames before failing; leaving them would double the frame count in the final MP4.
3. **Route to `reader.extract_frames(ds)`**, which applies a 3-level internal fallback:
   - `ds.pixel_array` (nominal pydicom)
   - `ds.decompress()` (pydicom 3.x explicit decompression)
   - `_extract_j2k_raw_scan(ds)` — scans raw `PixelData` bytes for J2K SOC+SIZ markers (`FF 4F FF 51`), extracts each codestream independently, decodes with PIL/OpenJPEG. Handles undefined-length encapsulation that breaks dcm4che3.

This fallback produces pixel data **without LUT application** (pydicom path). The production pipeline logs `weasis_fallback: j2k_pydicom` in the progress stream for these files.

### AVI Input Support

`05-0080-D-P` is an `.avi` file (cinepak codec, 560×512 px). The ultrasound content occupies a 418×360 region centered in the frame, surrounded by black borders. Handling:

1. Probe with `ffprobe -v quiet -print_format json -show_streams`: extracts `r_frame_rate` (rational fraction, e.g. `"1000/37"`), `width`, `height`.
2. FPS: `round(num / den)` from the rational — do **not** take just the numerator (1000 is not the fps).
3. Dimensions: hardcoded `tw, th = 418, 360` for `05-0080` stem — the scale rule would produce wrong output since the frame borders are not ultrasound content.

For other `.avi` inputs (not `05-0080`), the standard `target_dimensions(height, width)` applies.

### Batch Conversion Script

`scripts/dicom_batch_to_mp4.py` reproduces `datasetAVANTPREPROCESS` from `datasetDICOM`.

**Prerequisites**:
- venv activated: `source pythonCode/modules/starhe_plugin/.venv/bin/activate`
- `ffmpeg` and `ffprobe` in PATH
- Weasis JAR + Java (bundled JRE or system Java 17+) for LUT application

```bash
# Convert only
python scripts/dicom_batch_to_mp4.py \
  --input  /path/to/datasetDICOM \
  --output /path/to/output_mp4

# Convert + compare against a reference folder
python scripts/dicom_batch_to_mp4.py \
  --input     /path/to/datasetDICOM \
  --output    /path/to/output_mp4 \
  --reference /path/to/datasetAVANTPREPROCESS
```

When `--reference` is provided, the script:
1. **Pre-probes the reference** with `probe_mp4_fast()` (fast `ffprobe` using container `format.duration`, no `-count_frames` decoding) before encoding the DICOM.
2. Uses the reference FPS and frame count as **encoding targets**, overriding DICOM-derived values when they differ.
3. Passes `-vframes N` to ffmpeg to cap the frame count when the reference is shorter than the DICOM.
4. After encoding, prints a side-by-side comparison table (dimensions, FPS, frame count, duration).

This mechanism is necessary because some J2K DICOMs in the dataset have inconsistent metadata: `probe_mp4()` with `-count_frames` returns `nb_read_frames=0` for most reference files, so `probe_mp4_fast()` derives the frame count as `round(duration × fps)` from the container duration instead.

Output files are named `{patient_id}_{label}_{width}_{height}.mp4`.

### Validation Results (June 24, 2026)

**48 files** from `datasetDICOM` converted and compared against `datasetAVANTPREPROCESS` using `--reference`:

| Metric | Result | Notes |
|---|---|---|
| Files converted | **48 / 48** (0 errors) | — |
| Dimension exact match | 45 / 48 | 3 files (720×495 DICOM): our=698 px, ref=700 px — unexplained +2 px in reference |
| FPS exact match | **48 / 48** | — |
| Frame count exact match | **48 / 48** | — |
| Duration exact match | **48 / 48** | Δ < 0.1 s for all files |

Without `--reference`, FPS and frame count follow DICOM metadata directly, which diverges from the reference for 4 J2K files (see Known Anomalies).

### Known Anomalies in the Reference Dataset

| Anomaly | Files | Detail | Handled by `--reference` |
|---|---|---|---|
| +2 px width | `03-0015`, `05-0018`, `05-0054` (DICOM 720×495) | Our formula → 698 px; reference → 700 px. The reference tool used always-round-up, producing 700 px. Both are valid even widths; not fixable from DICOM data alone. | No (dimension not overridden) |
| FPS: DICOM tag vs reference | `01-0063`, `01-0072`, `01-0088` | All three are J2K DICOMs that fail Weasis (`ClassCastException: Value$1 cannot be cast to BulkData`). `RecommendedDisplayFrameRate` = 16–17 fps; reference encoded at 25 fps (PAL default used by the original tool). | **Yes** — fps overridden to reference value |
| Frame count | `05-0065-B-Y` | J2K DICOM. pydicom J2K scan extracts 253 frames; reference contains only 89. The reference was truncated at the original encoding step. | **Yes** — `-vframes 89` caps the output |

### Bit-for-bit Reproducibility

**The output MP4 files will never be bit-for-bit identical to the reference**, regardless of parameters. AV1 encoding (`libsvtav1`) is non-deterministic: internal frame-parallel threading decisions vary between runs, producing different bitstreams even from identical input frames and identical encoder settings. This is inherent to all modern lossy video encoders.

What matters for the pipeline is **pixel-level similarity after decoding**. Measured on representative files:

| File | Frames | MAE (0–255 scale) | PSNR |
|---|---|---|---|
| `01-0006-L-G` (standard) | 146 | **0.89** | **41.8 dB** |
| `01-0063-S-R` (fps override 16→25 fps) | 131 | **0.84** | **41.7 dB** |
| `05-0065-B-Y` (frame-count override 253→89) | 89 | 4.1 | 26.3 dB |

41–42 dB PSNR (MAE < 1.0) corresponds to imperceptible quality difference — the reference and our output are visually identical for 45/48 files. The lower PSNR for `05-0065` reflects that the reference J2K decoder used a different decoding path for this specific file, producing slightly different pixel values before encoding.

---

## Full DICOM Pipeline Reproducibility

This section documents the end-to-end reproducibility work on the complete DICOM
pipeline (`DICOM → Weasis → prepUS → STARHE models`). The goal is to prove, with
measurements, that this repo's pipeline reproduces the results of the original
research pipeline (Adrien M's `data_test` dataset), and to isolate every residual
source of divergence.

### Pipeline stages under test

```
DICOM (raw) ──► Weasis (LUT) ──► prepUS crop ──► STARHE-RISK / STARHE-DETECT
                                     ▲
      datasetAVANTPREPROCESS (AV1 MP4) ┘   (intermediate, unprocessed step)
      data_test (mpeg4 MP4)  ────────────► STARHE-RISK / STARHE-DETECT  (reference path)
```

Each stage is validated in isolation, because testing only the end-to-end result
does not tell you *where* a divergence originates.

### numpy 2.0 compatibility (vendored prepUS)

The vendored prepUS (`third_party/prepUS/`) was written in April 2024 for numpy 1.x.
The constraint is that this code must stay **identical to the original**, so only
minimal numpy-2.0 compatibility fixes are applied:

- **`backscan.py`** — `np.linalg.solve` now requires a 1-D right-hand side:
  `b = np.array([rho1, rho2])` instead of the old 2-D `[[rho1], [rho2]]`.
- **`cli.py`** — added an `_NpEncoder` so `json.dump` can serialize numpy scalar
  types written to `info.json`.
- **NEP 50 type promotion** — `angle_between_lines()` now returns a float32
  `theta_c` (was float64 under numpy 1.x). Measured impact: **8.7 × 10⁻⁸ rad**,
  i.e. **~4.5 × 10⁻⁵ px** at 512 px width — far below the 1-px threshold needed to
  shift a crop boundary. No functional effect.

### Current configuration — set to reproduce Jérémy (July 2026)

The reproducibility flags are currently configured to **match Jérémy's native
environment**, not to maximize cross-OS portability. Run the pipeline on **Linux**
to be closest to his setup.

| Flag | Value | Why |
|---|---|---|
| `DETERMINISTIC_INFERENCE` | `False` | Native device (`INFERENCE_DEVICE="auto"` → GPU if present) + float32, as Jérémy trained. CPU/float64 forcing is the *cross-OS* mode. |
| `PREPUS_BYPASS_MP4` | `False` | Mode A (mp4v roundtrip) — the exact crop path the models saw at training. Mode B produces cleaner, off-distribution crops. |
| `USE_WEASIS_EXPORT` | `True` | Reproduces Jérémy's LUT decoding chain (kept — it moves *toward* him). |

Flip the first two back to `True` to restore cross-platform bit-identity (at the
cost of matching Jérémy). See the RISK and DETECT reproducibility notes above.

### Cross-platform prepUS (`PREPUS_BYPASS_MP4 = True`, optional)

When cross-OS portability is the priority, set `PREPUS_BYPASS_MP4 = True`. The legacy
Mode A path writes a temporary MP4 and reads it back; the `mp4v` bitstream depends on
the FFmpeg build linked into OpenCV, which differs across macOS / Linux / Windows,
making crops non-portable for the *same* input. The in-memory numpy path (Mode B, see
[prepUS Preprocessing](#prepus-preprocessing-dicomprepus_bridgepy)) removes that
roundtrip and produces **bit-identical output across all OSes** — at the price of
crops slightly off the training distribution.

A fallback cascade guarantees the pipeline always completes: if `find_linear_fov`
(Hough-line FOV detection) fails on an atypical or dark cone, `prepus_bridge` falls
back to `crop.py` (temporal-variability ROI detection) with an explicit warning —
geometric crop only, no UI mask.

### Library version pinning is NOT required

We compared prepUS output between April-2024 library versions and current versions
(numpy 1.26→2.4, opencv 4.9→4.13, scipy 1.13→1.17) on the 49 files of
`datasetAVANTPREPROCESS`. Because numpy 1.26.4 has no Python 3.14 wheel, the only
semantically significant change (NEP 50) is simulated by forcing float64 `theta_c`.

Result: **34/34 successfully processed files are bit-identical** (crop dimensions
and backscan pixels), Δtheta_c = 8.7 × 10⁻⁸ rad. All other functions used by prepUS
(`cv2.HoughLines` / `Canny` / `dilate` / `morphologyEx`, `scipy.ndimage`) are
deterministic across these version ranges. **Verdict: pinning library versions is
unnecessary** — the pinned-venv complexity outweighs any benefit.

### Residual divergence sources (established, not fixable in code)

1. **Video encoding (AV1 vs mpeg4).** Our intermediate `datasetAVANTPREPROCESS`
   files are AV1 (PSNR ~39–41 dB vs the mpeg4 reference). Slightly different pixels
   change `countUniquePixels` statistics in prepUS → shift the automatic threshold
   (`bin_edges[3]`) → different mask → different crop coordinates. This is the
   primary cause of crop-dimension mismatches vs `data_test` (0/22 exact), yet
   **20/22 RISK labels still match** — the model is robust to it.
2. **PyTorch version drift.** torch 2.11 (2025) yields different C3D 3D-conv
   floating-point results than torch ~2.0 (June 2024), same checkpoint and input,
   even in deterministic mode (normal BLAS/MKL evolution). The June-2024 reference
   *scores* are therefore no longer reproducible exactly, though *labels* are.

### Validation scripts and CSV outputs (`scripts/` → `scripts/results/`)

Run scripts from a venv-activated shell; each writes a CSV into `scripts/results/`.

| Script | Question answered | Key result |
|---|---|---|
| [compare_risk_original_vs_plugin.py](scripts/compare_risk_original_vs_plugin.py) | Does this repo's RISK match the original mmaction2 pipeline on the same preprocessed files? | **24/24, Δ = 0.000000** — model implementation is exact |
| [validate_dicom_pipeline.py](scripts/validate_dicom_pipeline.py) | From raw DICOM (Weasis→prepUS→RISK), same labels as `data_test`→RISK? | **23/24 labels identical** (96%); the one diff is a patient at 0.506 vs 0.481, both on the 0.50 threshold |
| [validate_pipeline_steps.py](scripts/validate_pipeline_steps.py) | Where does the full pipeline diverge, step by step? | Crops from AV1: 0/22 exact dims (encoding), but 20/22 labels correct |
| [validate_dicom_detect.py](scripts/validate_dicom_detect.py) | From raw DICOM (Weasis→prepUS→DETECT), same detection labels as `data_test`→DETECT? | **Our path: 0.0% detections on all 24 patients; reference: 24.4% avg** — 11/24 label agreement, all trivial zeros. DETECT preprocessing is off-distribution (see below). |
| [compare_prepus_lib_versions.py](scripts/compare_prepus_lib_versions.py) | Do library versions (2024 vs today) change prepUS output? | **34/34 bit-identical** — pinning not needed |

Generated CSVs in [scripts/results/](scripts/results/):

| CSV | Content |
|---|---|
| `comparaison_risk_original_vs_plugin.csv` | Per-patient RISK score, original vs plugin, `abs_delta`, `labels_identiques` |
| `validation_dicom_pipeline.csv` | Per-patient RISK from raw DICOM vs from `data_test`, `delta_score`, `labels_identiques` |
| `validate_pipeline_steps.csv` | Step 2 (AV1→prepUS crop vs `data_test`) and Step 3 (`data_test`→RISK vs June-2024 reference CSV) |
| `comparaison_datasets_avant_prepUS.csv` | Intermediate MP4 vs reference: codec, dimensions, MD5, PSNR, MAE — shows AV1 vs mpeg4 |
| `prepus_comparison.csv` | Original prepUS vs `prepus_bridge` crop coordinates — IoU ~0.997, ±1 px |
| `compare_prepus_lib_versions.csv` | Old vs current library behaviour: `delta_theta_c`, `backscan_psnr_dB`, `crop_*_match` |

### Conclusion

Each link in the chain is validated in isolation — RISK model exact (24/24), prepUS
faithful (IoU 0.997), libraries ruled out (bit-identical) — and the residual
end-to-end divergences are localized, explained, and quantified: **video encoding
(AV1)** and **PyTorch version drift**. To reach exact score reproduction, the
options are to pin the encoding path or to **fine-tune the current model** on the
present-day distribution.

---

## STARHE-RISK Model (C3D)

> The full technical documentation of the STARHE-RISK pipeline — checkpoint, subprocess architecture, C3D network layout, preprocessing steps, inference algorithm, reproducibility settings, and validation results — is in the [STARHE-RISK: C3D Pipeline](#starhe-risk-c3d-pipeline) section above.

The pure-PyTorch fallback implementation (`ai/models/c3d.py`) reproduces the same architecture and **identical preprocessing** as the mmaction2 subprocess backend. It is selected automatically when mmaction2 is unavailable (`C3D_BACKEND = "pytorch"` in `config.py`, or subprocess failure). Both backends produce bit-identical scores for the same input tensor.

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

## Live Streaming Pipeline (`ai/live_pipeline.py` + `ai/run_live.py`)

The live pipeline performs frame-by-frame inference on a continuous video stream. It is designed to run completely locally — no data leaves the machine.

`run_live.py` is the CLI entry point launched by the Go server as a subprocess. It handles the three input sources and feeds frames into `LivePipeline`. Results are emitted over stdout using the same `GO_PRINT|level|{json}` protocol as `pipeline.py`. Preview frames are emitted immediately (before inference), so the UI can display the live feed independently of the inference rate.

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
| `handlers.go` | `POST /starhe/analyze` — launches `pipeline.py`, SSE streaming of `GO_PRINT|…` lines; `POST /starhe/live/start` — launches `run_live.py`, `POST /starhe/live/stop`, `GET /starhe/live/stream` (SSE) |
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
├── Makefile                          # Task runner (make setup / tkinter / react / build / help)
├── plugin.json                       # Plugin manifest (standalone config + MEDomics integration)
├── README.md                         # This file
├── READMEUtilisateur.md              # Tkinter interface user guide
├── TODOLIST.md                       # Logbook / roadmap
├── MEDomicsLab_LOGO.png              # Logo displayed in the UI
│
├── scripts/                          # Launcher and setup scripts
│   ├── setup.sh                      # macOS/Linux venv + dependencies setup (without UI)
│   ├── setup.ps1                     # Windows venv + dependencies setup (without UI)
│   ├── run_tkinter.sh                # macOS/Linux UI prototype launcher (auto-installs prepUS)
│   ├── run_tkinter.ps1               # Windows UI prototype launcher (auto-installs prepUS)
│   ├── start_react.sh                # macOS/Linux Go + React dev launcher (auto port detection)
│   ├── start_react.ps1               # Windows Go + React dev launcher (auto port detection)
│   └── download_models.py            # AI weights download from GitHub Release
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
        │   ├── run_live.py           # CLI entry point for live analysis (launched by Go server)
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

Reproducibility parameters (currently set to reproduce Jérémy on Linux — see
[Full DICOM Pipeline Reproducibility](#full-dicom-pipeline-reproducibility)):

| Parameter | Value | Effect |
|---|---|---|
| `DETERMINISTIC_INFERENCE` | `False` | `False` = native device/float32 (matches Jérémy). `True` = CPU/float64, bit-identical cross-OS. |
| `PREPUS_BYPASS_MP4` | `False` | `False` = Mode A mp4v roundtrip (training path). `True` = pure-numpy, cross-OS bit-identical but off-distribution. |
| `USE_WEASIS_EXPORT` | `True` | DICOM decoded via Weasis (Modality + VOI LUT), pydicom fallback. Reproduces Jérémy's LUT chain. |
| `INFERENCE_DEVICE` | `"auto"` | `auto` → CUDA/MPS/CPU. Used when `DETERMINISTIC_INFERENCE=False`. |
| `RISK_THRESHOLD` | `0.50` | Class-1 probability cutoff for "High risk". |

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
- **RISK borderline patients**: 5 CHC− patients score between 51–68 % despite correct prepUS preprocessing (02-0022, 02-0025, 05-0018, 05-0077, 06-0029). These are structural model errors — Jérémy N's reference implementation produces the same result.

---

## Other Documents

- [READMEUtilisateur.md](READMEUtilisateur.md) — User guide for the Tkinter interface
- [TODOLIST.md](TODOLIST.md) — Logbook, completed tasks and roadmap
