#!/usr/bin/env bash
# fetch_jre.sh — Downloads a Temurin 17 JRE for the current platform
# (or the one passed as an argument) from the Adoptium API.
#
# Usage:
#   ./scripts/fetch_jre.sh                # auto-detect (uname)
#   ./scripts/fetch_jre.sh mac-arm64
#   ./scripts/fetch_jre.sh mac-x64
#   ./scripts/fetch_jre.sh linux-x64
#
# Output: renderer/build-resources/jre-<platform>/  (contains bin/java)
# package.json convention: extraResources copies this directory to "jre/"
# in STARHE.app/Contents/Resources/jre/bin/java.
#
# For Windows, use scripts/fetch_jre.ps1 (Windows zip not handled here).

set -euo pipefail

JRE_VERSION="${JRE_VERSION:-17}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_ROOT="$ROOT/renderer/build-resources"

# ── Platform detection ────────────────────────────────────────────────────────
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

# ── Mapping to Adoptium API parameters ────────────────────────────────────────
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

# Idempotence: skip if already downloaded and bin/java is executable
if [[ -x "$OUT_DIR/bin/java" ]]; then
    echo "[fetch_jre] JRE déjà présente : $OUT_DIR"
    "$OUT_DIR/bin/java" -version
    exit 0
fi

# ── Download ──────────────────────────────────────────────────────────────────
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

# Adoptium ships `jdk-17.x.x+x-jre/` at the root of the tarball.
# On mac: contains `Contents/Home/{bin,lib,...}` (.app-like bundle).
# On linux: contains `{bin,lib,...}` directly.
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

# ── Verification ──────────────────────────────────────────────────────────────
if [[ ! -x "$OUT_DIR/bin/java" ]]; then
    echo "[fetch_jre] ERREUR : $OUT_DIR/bin/java introuvable après extraction" >&2
    ls -la "$OUT_DIR" >&2
    exit 1
fi

echo "[fetch_jre] OK : $OUT_DIR"
"$OUT_DIR/bin/java" -version
echo "[fetch_jre] Taille : $(du -sh "$OUT_DIR" | cut -f1)"
