#!/usr/bin/env bash
# medomics_register.sh — Enregistre le plugin STARHE dans MEDomics
#
# Crée ~/Library/Application Support/MEDomics/plugins/starhe/plugin.json
# (macOS) ou ~/.config/MEDomics/plugins/starhe/plugin.json (Linux).
# MEDomics détectera automatiquement le plugin au prochain démarrage.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/../medomics_integration/plugin.json"

if [ ! -f "$MANIFEST" ]; then
  echo "Erreur : manifest introuvable → $MANIFEST" >&2
  exit 1
fi

if [ "$(uname)" = "Darwin" ]; then
  PLUGINS_DIR="$HOME/Library/Application Support/MEDomics/plugins/starhe"
else
  PLUGINS_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/MEDomics/plugins/starhe"
fi

mkdir -p "$PLUGINS_DIR"
cp "$MANIFEST" "$PLUGINS_DIR/plugin.json"
echo "STARHE enregistré : $PLUGINS_DIR/plugin.json"
