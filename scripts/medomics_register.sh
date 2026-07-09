#!/usr/bin/env bash
# medomics_register.sh — Registers the STARHE plugin in MEDomics
#
# Copies plugin.json into all the detected MEDomics userData directories
# (production: MEDomics, development: medomics-platform (development)).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/../medomics_integration/plugin.json"

if [ ! -f "$MANIFEST" ]; then
  echo "Erreur : manifest introuvable → $MANIFEST" >&2
  exit 1
fi

if [ "$(uname)" = "Darwin" ]; then
  BASE="$HOME/Library/Application Support"
else
  BASE="${XDG_CONFIG_HOME:-$HOME/.config}"
fi

# List of possible userData directories (prod + dev)
TARGETS=(
  "$BASE/MEDomics"
  "$BASE/medomics-platform"
  "$BASE/medomics-platform (development)"
)

INSTALLED=0
for TARGET in "${TARGETS[@]}"; do
  # Only installs into directories that already exist (app launched at least once)
  if [ -d "$TARGET" ]; then
    PLUGINS_DIR="$TARGET/plugins/starhe"
    mkdir -p "$PLUGINS_DIR"
    cp "$MANIFEST" "$PLUGINS_DIR/plugin.json"
    echo "STARHE enregistré : $PLUGINS_DIR/plugin.json"
    INSTALLED=$((INSTALLED + 1))
  fi
done

if [ "$INSTALLED" -eq 0 ]; then
  echo "Aucun dossier MEDomics trouvé dans $BASE." >&2
  echo "Lancez MEDomics au moins une fois avant d'exécuter ce script." >&2
  exit 1
fi
