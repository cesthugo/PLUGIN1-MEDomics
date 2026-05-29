# Makefile — STARHE / MEDomics Plugin
# ======================================
# Fonctionne sur macOS, Linux et Windows (Git Bash ou WSL).
#
# Commandes disponibles :
#   make setup      — installe le venv Python, les dépendances et prepUS
#   make tkinter    — lance l'interface prototype Tkinter
#   make react      — compile et démarre le serveur Go + l'UI React/Vite
#   make build      — compile l'application Electron distribuable
#   make help       — affiche cette aide

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
.PHONY: help setup tkinter react build

help:
	@echo ""
	@echo "STARHE — MEDomics Plugin"
	@echo "========================"
	@echo ""
	@echo "  make setup      Installe le venv Python, dépendances et prepUS"
	@echo "  make tkinter    Lance l'interface prototype Tkinter"
	@echo "  make react      Démarre le serveur Go + UI React (développement)"
	@echo "  make build      Compile l'app Electron distribuable"
	@echo ""

setup:
	$(SHELL_SETUP)

tkinter:
	$(SHELL_TKINTER)

react:
	$(SHELL_REACT)

build:
	cd react_ui && npm run build:electron
