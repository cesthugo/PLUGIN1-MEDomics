#!/usr/bin/env bash
# run_tkinter.sh — Lanceur du prototype STARHE Tkinter (macOS / Linux)
# Équivalent de run_tkinter.ps1 pour les systèmes Unix.
#
# Ce script est autonome : il vérifie les prérequis, crée le venv si absent,
# installe les dépendances, puis lance l'interface Tkinter.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/pythonCode/modules/starhe_plugin/.venv"
PYTHON="$VENV_DIR/bin/python"
MODULES="$SCRIPT_DIR/pythonCode/modules"
PREPUS="$SCRIPT_DIR/third_party/prepUS"
REQUIREMENTS="$SCRIPT_DIR/pythonCode/modules/starhe_plugin/requirements.txt"

# ── 1. Vérifier que Python 3.13 est disponible sur le système ────────────────
PYTHON_SYS=""
for cmd in python3.13 python3; do
    if command -v "$cmd" &>/dev/null; then
        ver="$("$cmd" --version 2>&1 | grep -oE '3\.13\.[0-9]+')" || true
        if [ -n "$ver" ]; then
            PYTHON_SYS="$(command -v "$cmd")"
            break
        fi
    fi
done

if [ -z "$PYTHON_SYS" ]; then
    echo "Erreur : Python 3.13 introuvable sur le système." >&2
    if [[ "$OSTYPE" == darwin* ]]; then
        echo "  Installe-le avec : brew install python@3.13 python-tk@3.13" >&2
    else
        echo "  Installe Python 3.13 via ton gestionnaire de paquets." >&2
    fi
    exit 1
fi

# ── 2. Vérifier tkinter (macOS Homebrew ne l'inclut pas par défaut) ──────────
if ! "$PYTHON_SYS" -c "import _tkinter" 2>/dev/null; then
    echo "Erreur : tkinter n'est pas disponible pour Python 3.13." >&2
    if [[ "$OSTYPE" == darwin* ]]; then
        echo "  Installe-le avec : brew install python-tk@3.13" >&2
    else
        echo "  Installe le paquet python3-tk (ou équivalent) de ta distribution." >&2
    fi
    exit 1
fi

# ── 3. Créer le venv si absent ───────────────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
    echo "Venv introuvable — création avec $PYTHON_SYS..."
    "$PYTHON_SYS" -m venv "$VENV_DIR"
    echo "Installation des dépendances (cela peut prendre quelques minutes)..."
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet
    "$VENV_DIR/bin/pip" install -r "$REQUIREMENTS" --quiet
    echo "Venv créé et dépendances installées."
fi

# ── 4. Installer prepUS si absent ───────────────────────────────────────────
if ! "$PYTHON" -c "import prepUS" 2>/dev/null; then
    echo "prepUS absent du venv — installation depuis third_party/prepUS..."
    "$PYTHON" -m pip install sonocrop --no-deps --quiet
    "$PYTHON" -m pip install "$PREPUS" --no-deps --quiet
    echo "prepUS installé avec succès."
fi

# ── 5. Télécharger les poids IA si absents ───────────────────────────────────
MODELS_DIR="$SCRIPT_DIR/pythonCode/modules/starhe_plugin/models"
RISK_PTH="$MODELS_DIR/best_acc_mean_cls_f1_epoch_14.pth"
DET_PTH="$MODELS_DIR/best_coco_bbox_mAP_50_iter_2100.pth"
if [ ! -f "$RISK_PTH" ] || [ ! -f "$DET_PTH" ]; then
    echo "Poids IA manquants — téléchargement depuis GitHub Releases..."
    "$PYTHON" "$SCRIPT_DIR/download_models.py"
fi

# ── 6. Lancer l'interface ────────────────────────────────────────────────────
echo "Lancement STARHE Tkinter (Python $("$PYTHON" --version 2>&1))..."
cd "$MODULES"
exec "$PYTHON" -m starhe_plugin.ui.prototype_tkinter
