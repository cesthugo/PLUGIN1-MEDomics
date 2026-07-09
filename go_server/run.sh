#!/usr/bin/env bash
# go_server/run.sh — Watchdog: launches go_server and restarts it automatically
# after a crash, with exponential backoff.
#
# Usage:
#   ./go_server/run.sh          # from the project root
#   cd go_server && ./run.sh    # from the go_server directory
#
# Clean shutdown: Ctrl+C (SIGINT) or kill <script_pid>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$SCRIPT_DIR/go_server"

# ── Compile if needed ─────────────────────────────────────────────────────────

if [[ ! -f "$BIN" ]]; then
  echo "[watchdog] Binaire introuvable — compilation en cours…"
  (cd "$SCRIPT_DIR" && go build -o go_server .)
fi

# ── Exponential backoff ───────────────────────────────────────────────────────

DELAYS=(1 2 5 10 30)   # delays in seconds
attempt=0
running=true

trap 'echo "[watchdog] Arrêt demandé."; running=false; kill "$SERVER_PID" 2>/dev/null || true; exit 0' INT TERM

# ── Restart loop ──────────────────────────────────────────────────────────────

while $running; do
  echo "[watchdog] Démarrage du serveur Go (tentative $((attempt + 1)))…"

  "$BIN" &
  SERVER_PID=$!

  START_TIME=$SECONDS

  # Wait for the process to finish
  wait "$SERVER_PID" 2>/dev/null
  EXIT_CODE=$?

  # Shutdown via signal trap (running=false) → do not loop
  $running || break

  # Compute the uptime
  UPTIME=$(( SECONDS - START_TIME ))

  if [[ $EXIT_CODE -eq 0 ]]; then
    echo "[watchdog] Serveur Go terminé proprement (code 0). Arrêt du watchdog."
    break
  fi

  echo "[watchdog] Serveur Go arrêté (code=$EXIT_CODE, durée=${UPTIME}s)."

  # If the server stayed up more than 30 s, reset the counter
  if [[ $UPTIME -ge 30 ]]; then
    attempt=0
  fi

  DELAY=${DELAYS[$((attempt < ${#DELAYS[@]} ? attempt : ${#DELAYS[@]} - 1))]}
  echo "[watchdog] Redémarrage dans ${DELAY}s…"
  sleep "$DELAY"

  attempt=$(( attempt + 1 ))
done
