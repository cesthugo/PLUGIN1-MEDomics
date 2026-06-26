#!/usr/bin/env bash
# fetch_jre.sh — Télécharge une JRE Temurin 17 pour la plateforme courante
# (ou celle passée en argument) depuis l'API Adoptium.
#
# Usage :
#   ./scripts/fetch_jre.sh                # auto-detect (uname)
#   ./scripts/fetch_jre.sh mac-arm64
#   ./scripts/fetch_jre.sh mac-x64
#   ./scripts/fetch_jre.sh linux-x64
#
# Sortie : renderer/build-resources/jre-<platform>/  (contient bin/java)
# Convention package.json : extraResources copie ce dossier vers "jre/"
# dans STARHE.app/Contents/Resources/jre/bin/java.
#
# Pour Windows, utiliser scripts/fetch_jre.ps1 (zip Windows non géré ici).

set -euo pipefail

JRE_VERSION="${JRE_VERSION:-17}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_ROOT="$ROOT/renderer/build-resources"

# ── Détection plateforme ──────────────────────────────────────────────────────
detect_platform() {
    local uname_s uname_m
    uname_s="$(uname -s)"
    uname_m="$(uname -m)"
    case "$uname_s" in
        Darwin)
            case "$uname_m" in
                arm64) echo "mac-arm64" ;;
                x86_64) echo "mac-x64" ;;
                *) echo "unsupported-mac-$uname_m" ;;
            esac
            ;;
        Linux)
            case "$uname_m" in
                x86_64) echo "linux-x64" ;;
                aarch64) echo "linux-aarch64" ;;
                *) echo "unsupported-linux-$uname_m" ;;
            esac
            ;;
        *) echo "unsupported-$uname_s" ;;
    esac
}

PLATFORM="${1:-$(detect_platform)}"

# ── Mapping vers paramètres Adoptium API ──────────────────────────────────────
case "$PLATFORM" in
    mac-arm64)     ADO_OS="mac";    ADO_ARCH="aarch64" ;;
    mac-x64)       ADO_OS="mac";    ADO_ARCH="x64" ;;
    linux-x64)     ADO_OS="linux";  ADO_ARCH="x64" ;;
    linux-aarch64) ADO_OS="linux";  ADO_ARCH="aarch64" ;;
    *)
        echo "[fetch_jre] Plateforme non supportée : $PLATFORM" >&2
        exit 1
        ;;
esac

OUT_DIR="$OUT_ROOT/jre-$PLATFORM"

# Idempotence : skip si déjà téléchargée et bin/java exécutable
if [[ -x "$OUT_DIR/bin/java" ]]; then
    echo "[fetch_jre] JRE déjà présente : $OUT_DIR"
    "$OUT_DIR/bin/java" -version
    exit 0
fi

# ── Téléchargement ────────────────────────────────────────────────────────────
URL="https://api.adoptium.net/v3/binary/latest/${JRE_VERSION}/ga/${ADO_OS}/${ADO_ARCH}/jre/hotspot/normal/eclipse?project=jdk"
TMP_TAR="$(mktemp -t jre-temurin.XXXXXX).tar.gz"

echo "[fetch_jre] Téléchargement Temurin ${JRE_VERSION} pour ${PLATFORM}…"
echo "[fetch_jre]   URL : $URL"
curl -sSL -o "$TMP_TAR" -H "Accept: application/octet-stream" "$URL"

# ── Extraction ────────────────────────────────────────────────────────────────
mkdir -p "$OUT_DIR"
TMP_EXTRACT="$(mktemp -d -t jre-extract.XXXXXX)"
trap 'rm -rf "$TMP_TAR" "$TMP_EXTRACT"' EXIT

tar -xzf "$TMP_TAR" -C "$TMP_EXTRACT"

# Adoptium livre `jdk-17.x.x+x-jre/` à la racine du tarball.
# Sur mac : contient `Contents/Home/{bin,lib,...}` (bundle .app-like).
# Sur linux : contient directement `{bin,lib,...}`.
INNER="$(find "$TMP_EXTRACT" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "$INNER" ]]; then
    echo "[fetch_jre] Extraction vide ?" >&2
    exit 1
fi

if [[ -d "$INNER/Contents/Home/bin" ]]; then
    # macOS bundle
    cp -R "$INNER/Contents/Home/." "$OUT_DIR/"
else
    cp -R "$INNER/." "$OUT_DIR/"
fi

# ── Vérification ──────────────────────────────────────────────────────────────
if [[ ! -x "$OUT_DIR/bin/java" ]]; then
    echo "[fetch_jre] ERREUR : $OUT_DIR/bin/java introuvable après extraction" >&2
    ls -la "$OUT_DIR" >&2
    exit 1
fi

echo "[fetch_jre] OK : $OUT_DIR"
"$OUT_DIR/bin/java" -version
echo "[fetch_jre] Taille : $(du -sh "$OUT_DIR" | cut -f1)"
