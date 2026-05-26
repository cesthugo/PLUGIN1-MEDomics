#!/usr/bin/env bash
# launch_plugin.command — Lanceur standalone STARHE Plugin (macOS)
#
# Double-cliquer dans le Finder pour lancer le plugin SANS MEDomics.
# Une fenêtre Terminal s'ouvre et orchestre :
#   1. Vérification des prérequis (Python 3.13, Node.js, Go)
#   2. Création du venv Python si absent + installation des dépendances
#   3. Compilation du binaire Go STARHE si absent
#   4. Démarrage de MongoDB sur le port 54017
#   5. Démarrage du serveur Go STARHE → http://localhost:8082
#   6. Démarrage du serveur de développement React → http://localhost:5173
#   7. Ouverture automatique du navigateur
#
# Ctrl+C dans ce terminal arrête tous les services.

# ── Chemins ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$SCRIPT_DIR"
GO_SERVER_DIR="$PLUGIN_DIR/go_server"
REACT_UI_DIR="$PLUGIN_DIR/react_ui"
VENV_DIR="$PLUGIN_DIR/pythonCode/modules/starhe_plugin/.venv"
PYTHON_VENV="$VENV_DIR/bin/python"
PREPUS_DIR="$PLUGIN_DIR/third_party/prepUS"
REQUIREMENTS="$PLUGIN_DIR/pythonCode/modules/starhe_plugin/requirements.txt"
MODELS_DIR="$PLUGIN_DIR/pythonCode/modules/starhe_plugin/models"
DATA_DIR="$PLUGIN_DIR/data"
MONGO_DBPATH="$DATA_DIR/mongodb"

# ── PIDs des services démarrés ────────────────────────────────────────────────
MONGO_PID=""
GOSERVER_PID=""
REACT_PID=""
MONGO_STARTED=false

# ── Bannière ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   STARHE Plugin — Lanceur standalone             ║"
echo "║   Go :8082  ·  React :5173  ·  MongoDB :54017   ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── Utilitaires ───────────────────────────────────────────────────────────────
die() {
    echo ""
    echo "❌  $*"
    echo ""
    echo "Appuie sur Entrée pour fermer cette fenêtre..."
    read -r
    exit 1
}

cleanup() {
    echo ""
    echo "Arrêt des services en cours..."
    [ -n "$REACT_PID" ]    && kill "$REACT_PID"    2>/dev/null || true
    [ -n "$GOSERVER_PID" ] && kill "$GOSERVER_PID" 2>/dev/null || true
    if $MONGO_STARTED && [ -n "$MONGO_PID" ]; then
        kill "$MONGO_PID" 2>/dev/null || true
        echo "  MongoDB arrêté."
    fi
    echo "Tous les services sont arrêtés. À bientôt !"
}
trap cleanup INT TERM EXIT

# ── 1. Prérequis système ──────────────────────────────────────────────────────
echo "── Prérequis ──────────────────────────────────────────"

# Python 3.13
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
    die "Python 3.13 introuvable.\n   Installe-le via : brew install python@3.13"
fi
echo "  ✅ Python 3.13 ($PYTHON_SYS)"

# Node.js
command -v node &>/dev/null \
    || die "Node.js introuvable. Installe-le depuis https://nodejs.org"
echo "  ✅ Node.js $(node --version)"

# npm
command -v npm &>/dev/null || die "npm introuvable."
echo "  ✅ npm $(npm --version)"

# Go
command -v go &>/dev/null \
    || die "Go introuvable. Installe-le depuis https://go.dev/dl/"
echo "  ✅ Go $(go version | awk '{print $3}')"

echo ""

# ── 2. Environnement Python ───────────────────────────────────────────────────
echo "── Environnement Python ───────────────────────────────"

if [ ! -f "$PYTHON_VENV" ]; then
    echo "  🔨 Création du venv Python 3.13..."
    "$PYTHON_SYS" -m venv "$VENV_DIR" \
        || die "Création du venv échouée."
    echo "  📦 Installation des dépendances (première fois, quelques minutes)..."
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet
    "$VENV_DIR/bin/pip" install -r "$REQUIREMENTS" --quiet \
        || die "pip install requirements.txt échoué."
    echo "  ✅ Venv créé et dépendances installées."
else
    echo "  ✅ Venv présent."
fi

# prepUS
if ! "$PYTHON_VENV" -c "import prepUS" 2>/dev/null; then
    echo "  📦 Installation de prepUS..."
    "$PYTHON_VENV" -m pip install sonocrop --no-deps --quiet
    "$PYTHON_VENV" -m pip install "$PREPUS_DIR" --no-deps --quiet \
        || die "Installation de prepUS échouée."
    echo "  ✅ prepUS installé."
fi

# Poids IA
if [ ! -f "$MODELS_DIR/best_acc_mean_cls_f1_epoch_14.pth" ] || \
   [ ! -f "$MODELS_DIR/best_coco_bbox_mAP_50_iter_2100.pth" ]; then
    echo "  📥 Téléchargement des poids IA..."
    "$PYTHON_VENV" "$PLUGIN_DIR/download_models.py" \
        || die "Téléchargement des poids IA échoué."
    echo "  ✅ Poids IA présents."
fi

echo ""

# ── 3. Binaire Go STARHE ──────────────────────────────────────────────────────
echo "── Serveur Go STARHE ──────────────────────────────────"
GOSERVER_BIN="$GO_SERVER_DIR/go_server"

if [ ! -f "$GOSERVER_BIN" ]; then
    echo "  🔨 Compilation du binaire Go (première fois)..."
    (cd "$GO_SERVER_DIR" && go build -o go_server .) \
        || die "Compilation du serveur Go échouée.\n   Vérifie que go.mod est présent dans go_server/."
    echo "  ✅ Binaire compilé : $GOSERVER_BIN"
else
    echo "  ✅ Binaire présent : $GOSERVER_BIN"
fi

echo ""

# ── 4. MongoDB (port 54017) ───────────────────────────────────────────────────
echo "── MongoDB (port 54017) ───────────────────────────────"

if lsof -i :54017 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "  ✅ MongoDB déjà actif sur le port 54017."
else
    # Chercher mongod dans les emplacements connus
    MONGOD=""
    for p in \
        "$HOME/.medomics/mongodb/bin/mongod" \
        "/opt/homebrew/bin/mongod" \
        "/usr/local/bin/mongod"; do
        [ -f "$p" ] && MONGOD="$p" && break
    done
    if [ -z "$MONGOD" ] && command -v mongod &>/dev/null; then
        MONGOD="$(command -v mongod)"
    fi

    if [ -n "$MONGOD" ]; then
        mkdir -p "$MONGO_DBPATH"
        echo "  🚀 Démarrage de MongoDB ($MONGOD)..."
        "$MONGOD" --port 54017 --dbpath "$MONGO_DBPATH" \
            > "$MONGO_DBPATH/mongod.log" 2>&1 &
        MONGO_PID=$!
        MONGO_STARTED=true
        sleep 2
        if ! kill -0 "$MONGO_PID" 2>/dev/null; then
            echo "  ⚠️  MongoDB n'a pas démarré (voir data/mongodb/mongod.log)."
            echo "      Le plugin fonctionnera mais les résultats ne seront pas persistés."
        else
            echo "  ✅ MongoDB démarré (PID $MONGO_PID)."
        fi
    else
        echo "  ⚠️  mongod introuvable — les résultats ne seront pas persistés."
        echo "      Lance MEDomics d'abord pour démarrer MongoDB, ou installe"
        echo "      MongoDB Community depuis https://www.mongodb.com/try/download/community"
    fi
fi

echo ""

# ── 5. Dépendances React UI ───────────────────────────────────────────────────
echo "── UI React STARHE ────────────────────────────────────"

if [ ! -d "$REACT_UI_DIR/node_modules" ]; then
    echo "  📦 Installation des dépendances React UI (première fois)..."
    (cd "$REACT_UI_DIR" && npm ci) \
        || die "npm ci échoué dans $REACT_UI_DIR"
    echo "  ✅ Dépendances installées."
else
    echo "  ✅ node_modules présent."
fi

echo ""

# ── 6. Démarrage des services ─────────────────────────────────────────────────
mkdir -p "$DATA_DIR"

echo "── Lancement des services ─────────────────────────────"

# Serveur Go STARHE
echo "  🚀 Serveur Go STARHE → http://localhost:8082"
"$GOSERVER_BIN" > "$DATA_DIR/go_server.log" 2>&1 &
GOSERVER_PID=$!
echo "     PID $GOSERVER_PID  (logs : data/go_server.log)"

# Serveur React (Vite dev server, proxie /starhe → :8082)
echo "  🚀 UI React           → http://localhost:5173"
(cd "$REACT_UI_DIR" && npm run dev) > "$DATA_DIR/react.log" 2>&1 &
REACT_PID=$!
echo "     PID $REACT_PID  (logs : data/react.log)"

echo ""
echo "  ⏳ Attente du démarrage de l'interface React..."
for _ in $(seq 1 40); do
    curl -s http://localhost:5173 >/dev/null 2>&1 && break
    sleep 1
done

# ── 7. Ouvrir le navigateur ───────────────────────────────────────────────────
echo ""
echo "  🌐 Ouverture du navigateur → http://localhost:5173"
open http://localhost:5173

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  STARHE Plugin en cours d'exécution.             ║"
echo "║  Appuie sur Ctrl+C pour arrêter tous les         ║"
echo "║  services (MongoDB, Go, React).                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Maintenir le script actif jusqu'à Ctrl+C ou fermeture d'un service
wait "$GOSERVER_PID" "$REACT_PID"
