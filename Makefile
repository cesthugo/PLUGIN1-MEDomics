# Makefile — STARHE / MEDomics Plugin
# ======================================
# Fonctionne sur macOS, Linux et Windows (Git Bash ou WSL).
#
# Commandes disponibles :
#   make setup            — installe le venv Python, les dépendances et prepUS
#   make tkinter          — lance l'interface prototype Tkinter
#   make react            — compile et démarre le serveur Go + l'UI React/Vite
#   make electron         — lance l'application Electron en mode développement
#   make build            — compile les fichiers Electron (sans lancer l'app)
#   make pack             — compile + package l'installateur distributable
#   make cross-compile    — cross-compile le serveur Go pour mac/linux/win
#   make build-worker     — bundle le worker Python (PyInstaller)
#   make help             — affiche cette aide

# ── Détection OS ──────────────────────────────────────────────────────────────
ifeq ($(OS),Windows_NT)
    # Windows : Git Bash ou MSYS2 requis (make via choco install make)
    SHELL_SETUP   = powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
    SHELL_TKINTER = powershell -ExecutionPolicy Bypass -File scripts/run_tkinter.ps1
    SHELL_REACT   = powershell -ExecutionPolicy Bypass -File scripts/start_react.ps1
else
    SHELL_SETUP   = ./scripts/setup.sh
    SHELL_TKINTER = ./scripts/run_tkinter.sh
    SHELL_REACT   = ./scripts/start_react.sh
endif

# ── Cibles ────────────────────────────────────────────────────────────────────
.PHONY: help setup tkinter react electron build pack cross-compile build-worker

help:
	@echo ""
	@echo "STARHE — MEDomics Plugin"
	@echo "========================"
	@echo ""
	@echo "  make setup            Installe le venv Python, dépendances et prepUS"
	@echo "  make tkinter          Lance l'interface prototype Tkinter"
	@echo "  make react            Démarre le serveur Go + UI React (développement)"
	@echo "  make electron         Lance l'app Electron en mode développement (Vite + Electron)"
	@echo "  make build            Compile les fichiers Electron (renderer + main, sans lancer)"
	@echo "  make pack             Compile + package l'installateur distributable"
	@echo "  make cross-compile    Cross-compile le serveur Go (mac/linux/win) → renderer/build-resources/go-server/"
	@echo "  make build-worker     Bundle le worker Python via PyInstaller → renderer/build-resources/starhe_worker/"
	@echo ""

setup:
	$(SHELL_SETUP)

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
	@echo "Cross-compilation du serveur Go pour toutes les plateformes..."
	@mkdir -p renderer/build-resources/go-server
	cd go_server && GOOS=darwin  GOARCH=arm64 go build -o ../renderer/build-resources/go-server/go-server-mac-arm64  .
	cd go_server && GOOS=darwin  GOARCH=amd64 go build -o ../renderer/build-resources/go-server/go-server-mac-x64    .
	cd go_server && GOOS=linux   GOARCH=amd64 go build -o ../renderer/build-resources/go-server/go-server-linux-x64  .
	cd go_server && GOOS=windows GOARCH=amd64 go build -o ../renderer/build-resources/go-server/go-server-win-x64.exe .
	@echo "Done → renderer/build-resources/go-server/"
	@ls -lh renderer/build-resources/go-server/

build-worker:
	@echo "Build du worker Python via PyInstaller..."
	cd pythonCode/modules && \
	  source starhe_plugin/.venv/bin/activate && \
	  pyinstaller ../../scripts/starhe_worker.spec --noconfirm \
	              --distpath ../../renderer/build-resources
	@echo "Done → renderer/build-resources/starhe_worker/"
