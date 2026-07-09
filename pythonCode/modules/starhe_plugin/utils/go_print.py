"""
utils/go_print.py — Communication protocol to the Go server
==================================================================
MEDomics uses a stdout protocol based on prefixed JSON lines
so that the parent Go process can parse the Python worker's events.

Expected format:
  GO_PRINT|<level>|<message>

Supported levels: info, warning, error, progress, result

Example of parsing on the Go side:
  scanner.Scan() → "GO_PRINT|info|Plugin chargé"
"""

import json
import sys
from typing import Callable

# Force UTF-8 on stdout to avoid Unicode encoding errors on Windows
# (PowerShell uses cp1252 by default, incompatible with characters like →, —, etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── Log sink (injection for non-Go UI / tests) ────────────────────────────────
# fn(level: str, message: str) → None  |  None = stdout behavior (Go mode)
_log_sink: "Callable | None" = None


def set_log_sink(fn: "Callable | None") -> None:
    """
    Redirects go_print() to an arbitrary callback instead of stdout.

    Tkinter usage:
        set_log_sink(lambda level, msg: app._log(msg, level=level))
    Go pipeline usage (default):
        set_log_sink(None)
    """
    global _log_sink
    _log_sink = fn


def go_print(level: str, message: str, data: dict | None = None) -> None:
    """
    Emits a log message.

    In Go mode (default): writes a prefixed line to stdout that the
    Go server can intercept.
    In UI mode (sink active): calls the callback injected via set_log_sink().

    Parameters:
      level   : "info" | "warning" | "error" | "success" | "progress" | "result"
      message : human-readable text
      data    : optional dictionary of structured data (ignored by the sink)
    """
    if _log_sink is not None:
        _log_sink(level, message)
        return

    payload = {"level": level, "message": message}
    if data is not None:
        payload["data"] = data

    line = "GO_PRINT|" + level + "|" + json.dumps(payload, ensure_ascii=False)
    print(line, flush=True)


def go_progress(step: int, total: int, label: str = "") -> None:
    """
    Shortcut to emit a progress event.

    Parameters:
      step  : current step (0-based)
      total : total number of steps
      label : description of the current step (optional)
    """
    pct = int(step / total * 100) if total > 0 else 0
    go_print("progress", label or f"Étape {step}/{total}", {
        "step": step, "total": total, "percent": pct
    })


def go_result(data: dict) -> None:
    """
    Emits the final structured result of the processing.
    The Go server parses this line to return the HTTP response.
    """
    go_print("result", "Traitement terminé", data)
