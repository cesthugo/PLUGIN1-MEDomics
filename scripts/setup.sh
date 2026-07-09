#!/usr/bin/env bash
# setup.sh — Automatic setup of the STARHE environment (macOS / Linux)
# Usage: ./setup.sh
#
# This script:
#   1. Checks that Python 3.13 is installed
#   2. Creates the venv if missing
#   3. Installs requirements.txt
#   4. Installs sonocrop + prepUS (third_party/)
#
# No graphical interface is launched (unlike run_tkinter.sh).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$SCRIPT_DIR/pythonCode/modules/starhe_plugin/.venv"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
REQUIREMENTS="$SCRIPT_DIR/pythonCode/modules/starhe_plugin/requirements.txt"
PREPUS="$SCRIPT_DIR/third_party/prepUS"

# ── 1. Find Python 3.13 ─────────────────────────────────────────────────────
PYTHON_SYS=""
for cmd in python3.13 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver="$("$cmd" --version 2>&1 | grep -oE '3\.13\.[0-9]+')" || true
        if [ -n "$ver" ]; then
            PYTHON_SYS="$(command -v "$cmd")"
            break
        fi
    fi
done

if [ -z "$PYTHON_SYS" ]; then
    echo "❌ Python 3.13 introuvable." >&2
    if [[ "$OSTYPE" == darwin* ]]; then
        echo "   brew install python@3.13" >&2
    else
        echo "   Installe Python 3.13 via ton gestionnaire de paquets." >&2
    fi
    exit 1
fi
echo "✅ Python système : $PYTHON_SYS ($("$PYTHON_SYS" --version 2>&1))"

# ── 2. Create the venv ──────────────────────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
    echo "⚙️  Création du venv dans $VENV_DIR …"
    "$PYTHON_SYS" -m venv "$VENV_DIR"
else
    echo "✅ Venv existant : $VENV_DIR"
fi

# ── 3. Install the dependencies ─────────────────────────────────────────────
echo "⚙️  Installation des dépendances (requirements.txt) …"
"$PIP" install --upgrade pip --quiet
"$PIP" install -r "$REQUIREMENTS" --quiet
echo "✅ Dépendances installées."

# ── 4. Install mmaction2 (--no-deps) + venv patches ─────────────────────────
if ! "$PYTHON" -c "import mmaction" 2>/dev/null; then
    echo "⚙️  Installation de mmaction2 (sans dépendances) …"
    "$PIP" install mmaction2==1.2.0 --no-deps --quiet
    echo "✅ mmaction2 installé."
fi

# Python 3.13 + mmdet compatibility patches in the mmaction2 venv
MMACTION_PKG="$VENV_DIR/lib/$(ls "$VENV_DIR/lib/")/site-packages/mmaction"
if [ -d "$MMACTION_PKG" ]; then
    # 1. Removal of the DRN import missing from wheel 1.2.0
    sed -i.bak '/from .drn.drn import DRN/d' \
        "$MMACTION_PKG/models/localizers/__init__.py" 2>/dev/null && \
    sed -i.bak "s/__all__ = \['TEM', 'PEM', 'BMN', 'TCANet', 'DRN'\]/__all__ = ['TEM', 'PEM', 'BMN', 'TCANet']/" \
        "$MMACTION_PKG/models/localizers/__init__.py" 2>/dev/null || true

    # 2. AssertionError in roi_heads (mmdet ↔ mmengine registry conflict)
    sed -i.bak "s/except (ImportError, ModuleNotFoundError):/except (ImportError, ModuleNotFoundError, AssertionError):/" \
        "$MMACTION_PKG/models/roi_heads/__init__.py" 2>/dev/null || true

    # 3. Same patch for task_modules
    sed -i.bak "s/except (ImportError, ModuleNotFoundError):/except (ImportError, ModuleNotFoundError, AssertionError):/" \
        "$MMACTION_PKG/models/task_modules/__init__.py" 2>/dev/null || true

    # Clean up the .bak backups
    find "$MMACTION_PKG" -name "*.bak" -delete 2>/dev/null || true
    echo "✅ Patches mmaction2 appliqués."
fi

# ── 5. Install prepUS + sonocrop ────────────────────────────────────────────
if ! "$PYTHON" -c "import prepUS" 2>/dev/null; then
    echo "⚙️  Installation de sonocrop + prepUS …"
    "$PIP" install sonocrop --no-deps --quiet
    "$PIP" install "$PREPUS" --no-deps --quiet
    echo "✅ prepUS installé."
else
    echo "✅ prepUS déjà présent."
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo " Setup terminé avec succès."
echo " Python venv : $PYTHON"
echo " Pour lancer le pipeline :"
echo "   source $VENV_DIR/bin/activate"
echo "   cd $SCRIPT_DIR/pythonCode/modules"
echo "   python -m starhe_plugin.pipeline <fichier.dcm>"
echo "══════════════════════════════════════════════════════════"
