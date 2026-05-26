#!/usr/bin/env bash
# launch_medomics.command — Lanceur MEDomics + STARHE (macOS)
#
# Double-cliquer sur ce fichier dans le Finder pour lancer l'application.
# Une fenêtre Terminal s'ouvre, vérifie les prérequis, puis démarre MEDomics.
#
# Ce que ce script orchestre :
#   1. Vérifie Node.js, npm et Go
#   2. Compile le binaire Go STARHE si absent (go_server/go_server)
#   3. Installe les dépendances npm MEDomics si absentes
#   4. Construit l'UI React STARHE et la déploie dans MEDomics si le dist est absent
#   5. Lance `npm run dev` dans MEDomics → nextron démarre Electron, qui lance
#      automatiquement MongoDB, le serveur Go MEDomics et le serveur Go STARHE

# ── Résolution des chemins ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$SCRIPT_DIR"
MEDOMICS_DIR="$(cd "$PLUGIN_DIR/../MEDomics" 2>/dev/null && pwd)" || MEDOMICS_DIR=""
GO_SERVER_DIR="$PLUGIN_DIR/go_server"
REACT_UI_DIR="$PLUGIN_DIR/react_ui"

# ── Bannière ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   MEDomics + STARHE — Lanceur de développement  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── Fonction utilitaire : afficher une erreur et attendre ────────────────────
die() {
    echo ""
    echo "❌  $*"
    echo ""
    echo "Appuie sur Entrée pour fermer cette fenêtre..."
    read -r
    exit 1
}

# ── 1. Vérification des prérequis ────────────────────────────────────────────
echo "── Vérification des prérequis ──────────────────────"

# Node.js
if ! command -v node &>/dev/null; then
    die "Node.js introuvable. Installe-le depuis https://nodejs.org (LTS recommandé)."
fi
NODE_VER="$(node --version)"
echo "  ✅ Node.js $NODE_VER"

# npm
if ! command -v npm &>/dev/null; then
    die "npm introuvable. Il devrait être inclus avec Node.js."
fi
echo "  ✅ npm $(npm --version)"

# Go
if ! command -v go &>/dev/null; then
    die "Go introuvable. Installe-le depuis https://go.dev/dl/ puis relance ce script."
fi
GO_VER="$(go version | awk '{print $3}')"
echo "  ✅ Go $GO_VER"

# Répertoire MEDomics
if [ -z "$MEDOMICS_DIR" ] || [ ! -d "$MEDOMICS_DIR" ]; then
    die "Répertoire MEDomics introuvable.\n   Attendu : $PLUGIN_DIR/../MEDomics\n   Vérifie que PLUGIN1-MEDomics et MEDomics sont dans le même dossier parent."
fi
echo "  ✅ MEDomics : $MEDOMICS_DIR"

# Répertoire go_server
if [ ! -d "$GO_SERVER_DIR" ]; then
    die "Répertoire go_server introuvable : $GO_SERVER_DIR"
fi
echo ""

# ── 2. Compiler le binaire Go STARHE si absent ───────────────────────────────
echo "── Serveur Go STARHE ───────────────────────────────"
GOSERVER_BIN="$GO_SERVER_DIR/go_server"

if [ ! -f "$GOSERVER_BIN" ]; then
    echo "  🔨 Compilation du binaire (première fois)..."
    (cd "$GO_SERVER_DIR" && go build -o go_server .) \
        || die "La compilation du serveur Go STARHE a échoué.\n   Vérifie que Go est correctement installé et que go.mod est présent dans go_server/."
    echo "  ✅ Binaire compilé : $GOSERVER_BIN"
else
    echo "  ✅ Binaire présent : $GOSERVER_BIN"
fi
echo ""

# ── 3. Dépendances npm MEDomics ──────────────────────────────────────────────
echo "── Dépendances Node.js MEDomics ────────────────────"

if [ ! -d "$MEDOMICS_DIR/node_modules" ]; then
    echo "  📦 Installation des dépendances (première fois, quelques minutes)..."
    (cd "$MEDOMICS_DIR" && npm install) \
        || die "npm install a échoué dans $MEDOMICS_DIR"
    echo "  ✅ Dépendances installées."
else
    echo "  ✅ node_modules présent."
fi
echo ""

# ── 4. UI React STARHE — construire et déployer si dist absent ───────────────
echo "── UI React STARHE ─────────────────────────────────"
REACT_DIST="$REACT_UI_DIR/dist"
MEDOMICS_STARHE_APP="$MEDOMICS_DIR/app/starhe-ui"
MEDOMICS_STARHE_RENDERER="$MEDOMICS_DIR/renderer/public/starhe-ui"

if [ ! -d "$REACT_DIST" ]; then
    echo "  🔨 Construction du bundle React STARHE (dist/ absent)..."
    if [ ! -d "$REACT_UI_DIR/node_modules" ]; then
        echo "  📦 Installation des dépendances React UI..."
        (cd "$REACT_UI_DIR" && npm ci) \
            || die "npm ci a échoué dans $REACT_UI_DIR"
    fi
    (cd "$REACT_UI_DIR" && npm run build) \
        || die "npm run build a échoué dans $REACT_UI_DIR"

    mkdir -p "$MEDOMICS_STARHE_APP" "$MEDOMICS_STARHE_RENDERER"
    cp -r "$REACT_DIST/." "$MEDOMICS_STARHE_APP/"
    cp -r "$REACT_DIST/." "$MEDOMICS_STARHE_RENDERER/"
    echo "  ✅ UI React construite et déployée dans MEDomics."
else
    echo "  ✅ dist/ présent — UI déjà construite."
fi
echo ""

# ── 5. Lancer MEDomics ────────────────────────────────────────────────────────
echo "── Lancement ───────────────────────────────────────"
echo "  🚀 Démarrage de MEDomics (npm run dev)..."
echo "     → Electron → MongoDB + serveur Go MEDomics + serveur Go STARHE"
echo ""
echo "  Pour arrêter l'application, ferme la fenêtre MEDomics."
echo "  Ce terminal restera ouvert jusqu'à la fermeture de l'app."
echo ""

cd "$MEDOMICS_DIR" && npm run dev

# Ce point n'est atteint qu'après la fermeture de l'app
echo ""
echo "MEDomics s'est arrêté."
echo "Appuie sur Entrée pour fermer cette fenêtre..."
read -r
