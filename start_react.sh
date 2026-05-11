  #!/usr/bin/env bash
# start_react.sh — lance le serveur Go STARHE puis l'UI React/Vite.
#
# Usage :
#   ./start_react.sh
#
# Logs :
#   logs/go_server.log
#   logs/react_ui.log
#   logs/starhe_dev.log

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
GO_LOG="$LOG_DIR/go_server.log"
REACT_LOG="$LOG_DIR/react_ui.log"
MAIN_LOG="$LOG_DIR/starhe_dev.log"

GO_PID=""
REACT_PID=""
STOPPED=false

mkdir -p "$LOG_DIR"
: > "$GO_LOG"
: > "$REACT_LOG"
: > "$MAIN_LOG"

log() {
  local msg="$1"
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$msg" | tee -a "$MAIN_LOG"
}

stop_all() {
  if [[ "$STOPPED" == true ]]; then
    return
  fi
  STOPPED=true
  log "Arrêt demandé, fermeture des processus..."
  if [[ -n "${REACT_PID:-}" ]] && kill -0 "$REACT_PID" 2>/dev/null; then
    kill "$REACT_PID" 2>/dev/null || true
  fi
  if [[ -n "${GO_PID:-}" ]] && kill -0 "$GO_PID" 2>/dev/null; then
    kill "$GO_PID" 2>/dev/null || true
  fi
}

trap stop_all INT TERM EXIT

if ! command -v go >/dev/null 2>&1; then
  log "ERREUR: Go est introuvable dans le PATH."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  log "ERREUR: npm est introuvable dans le PATH."
  exit 1
fi

# ── Choix du port Go ─────────────────────────────────────────────────────────
# Si STARHE_PORT est déjà défini dans l'environnement, on le respecte.
# Sinon on part de 8082 et on cherche le premier port libre.
find_free_port() {
  local port="${1:-8082}"
  while lsof -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; do
    port=$((port + 1))
  done
  echo "$port"
}

if [[ -z "${STARHE_PORT:-}" ]]; then
  STARHE_PORT="$(find_free_port 8082)"
fi
export STARHE_PORT
log "Port Go : $STARHE_PORT"

if command -v curl >/dev/null 2>&1 && curl -fsS "http://localhost:${STARHE_PORT}/health" >/dev/null 2>&1; then
  log "Serveur Go déjà disponible sur http://localhost:${STARHE_PORT}, réutilisation du processus existant."
else
  log "Compilation et lancement du serveur Go..."
  (
    cd "$ROOT_DIR/go_server"
    go build -o go_server .
    PORT="$STARHE_PORT" ./go_server
  ) >>"$GO_LOG" 2>&1 &
  GO_PID=$!
  log "Serveur Go démarré avec PID $GO_PID. Logs: $GO_LOG"
fi

log "Attente du healthcheck Go sur http://localhost:${STARHE_PORT}/health..."
for _ in {1..30}; do
  if command -v curl >/dev/null 2>&1 && curl -fsS "http://localhost:${STARHE_PORT}/health" >/dev/null 2>&1; then
    log "Serveur Go prêt."
    break
  fi
  if ! kill -0 "$GO_PID" 2>/dev/null; then
    log "ERREUR: le serveur Go s'est arrêté. Consulte $GO_LOG"
    exit 1
  fi
  sleep 1
done

if [[ ! -d "$ROOT_DIR/react_ui/node_modules" ]]; then
  log "Dépendances React absentes: exécution de npm install..."
  (cd "$ROOT_DIR/react_ui" && npm install) >>"$REACT_LOG" 2>&1
fi

log "Lancement de React/Vite sur http://localhost:5173..."
(
  cd "$ROOT_DIR/react_ui"
  npm run dev
) >>"$REACT_LOG" 2>&1 &
REACT_PID=$!
log "React démarré avec PID $REACT_PID. Logs: $REACT_LOG"

log "Prêt. Ouvre http://localhost:5173 (si le port est occupé, consulte $REACT_LOG pour le port choisi par Vite)."
log "Appuie sur Ctrl+C pour arrêter Go + React."

wait "$REACT_PID"
