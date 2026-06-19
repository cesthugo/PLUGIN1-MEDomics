#!/usr/bin/env bash
# medomics_register.sh — Enregistre le plugin STARHE dans MEDomics
#
# Copie plugin.json dans tous les dossiers userData MEDomics détectés
# (production : MEDomics, développement : medomics-platform (development)).
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

# Liste des dossiers userData possibles (prod + dev)
TARGETS=(
  "$BASE/MEDomics"
  "$BASE/medomics-platform"
  "$BASE/medomics-platform (development)"
)

INSTALLED=0
for TARGET in "${TARGETS[@]}"; do
  # N'installe que dans les dossiers qui existent déjà (app déjà lancée au moins une fois)
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
