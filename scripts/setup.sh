#!/usr/bin/env bash
# setup.sh — Installation automatique de l'environnement STARHE (macOS / Linux)
# Usage : ./setup.sh
#
# Ce script :
#   1. Vérifie que Python 3.13 est installé
#   2. Crée le venv si absent
#   3. Installe requirements.txt
#   4. Installe sonocrop + prepUS (third_party/)
#
# Aucune interface graphique n'est lancée (contrairement à run_tkinter.sh).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$SCRIPT_DIR/pythonCode/modules/starhe_plugin/.venv"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
REQUIREMENTS="$SCRIPT_DIR/pythonCode/modules/starhe_plugin/requirements.txt"
PREPUS="$SCRIPT_DIR/third_party/prepUS"

# ── 1. Trouver Python 3.13 ──────────────────────────────────────────────────
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

# ── 2. Créer le venv ────────────────────────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
    echo "⚙️  Création du venv dans $VENV_DIR …"
    "$PYTHON_SYS" -m venv "$VENV_DIR"
else
    echo "✅ Venv existant : $VENV_DIR"
fi

# ── 3. Installer les dépendances ────────────────────────────────────────────
echo "⚙️  Installation des dépendances (requirements.txt) …"
"$PIP" install --upgrade pip --quiet
"$PIP" install -r "$REQUIREMENTS" --quiet
echo "✅ Dépendances installées."

# ── 4. Installer prepUS + sonocrop ──────────────────────────────────────────
if ! "$PYTHON" -c "import prepUS" 2>/dev/null; then
    echo "⚙️  Installation de sonocrop + prepUS …"
    "$PIP" install sonocrop --no-deps --quiet
    "$PIP" install "$PREPUS" --no-deps --quiet
    echo "✅ prepUS installé."
else
    echo "✅ prepUS déjà présent."
fi

# ── Résumé ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo " Setup terminé avec succès."
echo " Python venv : $PYTHON"
echo " Pour lancer le pipeline :"
echo "   source $VENV_DIR/bin/activate"
echo "   cd $SCRIPT_DIR/pythonCode/modules"
echo "   python -m starhe_plugin.pipeline <fichier.dcm>"
echo "══════════════════════════════════════════════════════════"
