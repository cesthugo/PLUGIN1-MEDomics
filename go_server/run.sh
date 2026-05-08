#!/usr/bin/env bash
# go_server/run.sh — Watchdog : lance go_server et le redémarre automatiquement
# après un crash, avec backoff exponentiel.
#
# Usage :
#   ./go_server/run.sh          # depuis la racine du projet
#   cd go_server && ./run.sh    # depuis le dossier go_server
#
# Arrêt propre : Ctrl+C (SIGINT) ou kill <pid_du_script>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$SCRIPT_DIR/go_server"

# ── Compilation si nécessaire ─────────────────────────────────────────────────

if [[ ! -f "$BIN" ]]; then
  echo "[watchdog] Binaire introuvable — compilation en cours…"
  (cd "$SCRIPT_DIR" && go build -o go_server .)
fi

# ── Backoff exponentiel ───────────────────────────────────────────────────────

DELAYS=(1 2 5 10 30)   # délais en secondes
attempt=0
running=true

trap 'echo "[watchdog] Arrêt demandé."; running=false; kill "$SERVER_PID" 2>/dev/null || true; exit 0' INT TERM

# ── Boucle de redémarrage ─────────────────────────────────────────────────────

while $running; do
  echo "[watchdog] Démarrage du serveur Go (tentative $((attempt + 1)))…"

  "$BIN" &
  SERVER_PID=$!

  START_TIME=$SECONDS

  # Attend la fin du processus
  wait "$SERVER_PID" 2>/dev/null
  EXIT_CODE=$?

  # Arrêt via signal trap (running=false) → ne pas boucler
  $running || break

  # Calcul de la durée de vie
  UPTIME=$(( SECONDS - START_TIME ))

  if [[ $EXIT_CODE -eq 0 ]]; then
    echo "[watchdog] Serveur Go terminé proprement (code 0). Arrêt du watchdog."
    break
  fi

  echo "[watchdog] Serveur Go arrêté (code=$EXIT_CODE, durée=${UPTIME}s)."

  # Si le serveur a tenu plus de 30 s, on remet le compteur à zéro
  if [[ $UPTIME -ge 30 ]]; then
    attempt=0
  fi

  DELAY=${DELAYS[$((attempt < ${#DELAYS[@]} ? attempt : ${#DELAYS[@]} - 1))]}
  echo "[watchdog] Redémarrage dans ${DELAY}s…"
  sleep "$DELAY"

  attempt=$(( attempt + 1 ))
done
