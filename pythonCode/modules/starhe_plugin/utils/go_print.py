"""
utils/go_print.py — Protocole de communication vers le serveur Go
==================================================================
MEDomics utilise un protocole stdout basé sur des lignes JSON préfixées
pour que le processus Go parent puisse parser les événements du worker Python.

Format attendu :
  GO_PRINT|<niveau>|<message>

Niveaux supportés : info, warning, error, progress, result

Exemple de parsing côté Go :
  scanner.Scan() → "GO_PRINT|info|Plugin chargé"
"""

import json
import sys

# Force UTF-8 sur stdout pour éviter les erreurs d'encodage Unicode sous Windows
# (PowerShell utilise cp1252 par défaut, incompatible avec les caractères comme →, —, etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def go_print(level: str, message: str, data: dict | None = None) -> None:
    """
    Émet une ligne sur stdout que le serveur Go peut intercepter.

    Paramètres :
      level   : "info" | "warning" | "error" | "progress" | "result"
      message : texte humain lisible
      data    : dictionnaire optionnel de données structurées

    La sortie est toujours flushée immédiatement pour garantir
    la réactivité du flux en temps réel.
    """
    payload = {"level": level, "message": message}
    if data is not None:
        payload["data"] = data

    line = "GO_PRINT|" + level + "|" + json.dumps(payload, ensure_ascii=False)
    print(line, flush=True)


def go_progress(step: int, total: int, label: str = "") -> None:
    """
    Raccourci pour émettre un événement de progression.

    Paramètre :
      step  : étape courante (0-based)
      total : nombre total d'étapes
      label : description de l'étape courante (optionnel)
    """
    pct = int(step / total * 100) if total > 0 else 0
    go_print("progress", label or f"Étape {step}/{total}", {
        "step": step, "total": total, "percent": pct
    })


def go_result(data: dict) -> None:
    """
    Émet le résultat final structuré du traitement.
    Le serveur Go parse cette ligne pour renvoyer la réponse HTTP.
    """
    go_print("result", "Traitement terminé", data)
