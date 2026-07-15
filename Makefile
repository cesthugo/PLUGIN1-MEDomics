# Makefile — STARHE / MEDomics Plugin
# ======================================
# Works on macOS, Linux and Windows (Git Bash or WSL).
#
# Available commands:
#   make setup            — installs the Python venv, the dependencies and prepUS
#   make download-models  — downloads the STARHE AI weights (RISK + DETECT)
#   make tkinter          — launches the Tkinter prototype interface
#   make react            — builds and starts the Go server + the React/Vite UI
#   make electron         — launches the Electron application in development mode
#   make build            — compiles the Electron files (without launching the app)
#   make pack             — builds + packages the distributable installer
#   make cross-compile    — cross-compiles the Go server for mac/linux/win
#   make build-worker     — bundles the Python worker (PyInstaller)
#   make help             — shows this help

# ── OS detection ──────────────────────────────────────────────────────────────
ifeq ($(OS),Windows_NT)
    # Windows: Git Bash or MSYS2 required (make via choco install make)
    SHELL_SETUP   = powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
    SHELL_TKINTER = powershell -ExecutionPolicy Bypass -File scripts/run_tkinter.ps1
    SHELL_REACT   = powershell -ExecutionPolicy Bypass -File scripts/start_react.ps1
    PYTHON        = python
else
    SHELL_SETUP   = ./scripts/setup.sh
    SHELL_TKINTER = ./scripts/run_tkinter.sh
    SHELL_REACT   = ./scripts/start_react.sh
    PYTHON        = python3
endif

# ── Targets ───────────────────────────────────────────────────────────────────
.PHONY: help setup download-models tkinter react electron build pack cross-compile build-worker

help:
	@echo ""
	@echo "STARHE — MEDomics Plugin"
	@echo "========================"
	@echo ""
	@echo "  make setup            Installs the Python venv, dependencies and prepUS"
	@echo "  make download-models  Downloads the STARHE AI weights (RISK + DETECT) into models/"
	@echo "  make tkinter          Launches the Tkinter prototype interface"
	@echo "  make react            Starts the Go server + React UI (development)"
	@echo "  make electron         Launches the Electron app in development mode (Vite + Electron)"
	@echo "  make build            Compiles the Electron files (renderer + main, without launching)"
	@echo "  make pack             Builds + packages the distributable installer"
	@echo "  make cross-compile    Cross-compiles the Go server (mac/linux/win) → renderer/build-resources/go-server/"
	@echo "  make build-worker     Bundles the Python worker via PyInstaller → renderer/build-resources/starhe_worker/"
	@echo ""

setup:
	$(SHELL_SETUP)

download-models:
	$(PYTHON) scripts/download_models.py $(if $(FORCE),--force,)

tkinter:
	$(SHELL_TKINTER)

react:
	$(SHELL_REACT)

electron:
	cd renderer && npm run dev:electron

build:
	cd renderer && npm run build:electron

pack:
	cd renderer && npm run electron:pack

cross-compile:
	@echo "Cross-compiling the Go server for all platforms..."
	@mkdir -p renderer/build-resources/go-server
	cd go_server && GOOS=darwin  GOARCH=arm64 go build -o ../renderer/build-resources/go-server/go-server-mac-arm64  .
	cd go_server && GOOS=darwin  GOARCH=amd64 go build -o ../renderer/build-resources/go-server/go-server-mac-x64    .
	cd go_server && GOOS=linux   GOARCH=amd64 go build -o ../renderer/build-resources/go-server/go-server-linux-x64  .
	cd go_server && GOOS=windows GOARCH=amd64 go build -o ../renderer/build-resources/go-server/go-server-win-x64.exe .
	@echo "Done → renderer/build-resources/go-server/"
	@ls -lh renderer/build-resources/go-server/

build-worker:
	@echo "Building the Python worker via PyInstaller..."
	cd pythonCode/modules && \
	  source starhe_plugin/.venv/bin/activate && \
	  pyinstaller ../../scripts/starhe_worker.spec --noconfirm \
	              --distpath ../../renderer/build-resources
	@echo "Done → renderer/build-resources/starhe_worker/"
