"""
ai/starhe_risk.py — Wrapper STARHE-RISK (C3D)
=============================================
Deux backends sélectionnables via C3D_BACKEND dans config.py :

  "mmaction2" (défaut) : subprocess persistant _c3d_runner.py qui charge
      le backbone C3D et la tête I3DHead de mmaction2 directement (sans
      registre mmengine, compatible Python 3.13 + mmcv-lite).
      Requiert : mmaction2==1.2.0 installé avec --no-deps dans le venv.

  "pytorch" : implémentation pure PyTorch (C3DRecognizer dans c3d.py),
      validée bit-identique à mmaction2 sur les mêmes tenseurs d'entrée.
      Aucune dépendance mmaction2.

Entrée  : frames numpy (T, H, W, 3) uint8 RGB
Sortie  : {"risk_score": float, "risk_label": str, "scores": list}
"""

import base64
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from starhe_plugin.config import (
    C3D_BACKEND,
    DETERMINISTIC_INFERENCE,
    INFERENCE_DEVICE,
    RISK_THRESHOLD,
    STARHE_RISK_CHECKPOINT,
)
from starhe_plugin.utils.go_print import go_print

_C3D_RUNNER = Path(__file__).parent / "models" / "_c3d_runner.py"


# ─── Backend mmaction2 (subprocess persistant) ───────────────────────────────

class _MMAction2Backend:
    """Lance _c3d_runner.py en subprocess et expose predict(frames)."""

    def __init__(self, device: str):
        self._proc: subprocess.Popen | None = None
        self._device = device
        self._start()

    def _start(self) -> None:
        cmd = [
            sys.executable,
            str(_C3D_RUNNER),
            "--ckpt",   STARHE_RISK_CHECKPOINT,
            "--device", self._device,
        ]
        if DETERMINISTIC_INFERENCE:
            cmd.append("--deterministic")

        go_print("info", "STARHE-RISK : démarrage du serveur mmaction2 C3D…")
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        ready = self._proc.stdout.readline().strip()
        if "[c3d_server] READY" not in ready:
            err = self._proc.stderr.read(2000) if self._proc.stderr else ""
            self._proc = None
            raise RuntimeError(
                f"Serveur C3D mmaction2 non démarré. Reçu: {ready!r}\n{err}"
            )
        go_print("info", "STARHE-RISK (mmaction2 C3D) prêt.")

    def predict(self, frames: np.ndarray) -> tuple[float, float]:
        """Envoie les frames au subprocess et retourne (score_low, score_high)."""
        assert self._proc is not None, "subprocess C3D non démarré"
        payload = {
            "frames_b64": base64.b64encode(frames.tobytes()).decode(),
            "shape":      list(frames.shape),   # [T, H, W, 3]
        }
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()
        resp = json.loads(self._proc.stdout.readline())
        return resp["score_low"], resp["score_high"]

    def close(self) -> None:
        if self._proc is not None:
            try:
                self._proc.stdin.write(json.dumps({"__EXIT__": True}) + "\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None


# ─── Backend PyTorch pur ─────────────────────────────────────────────────────

class _PyTorchBackend:
    """Charge C3DRecognizer (PyTorch pur) et expose predict(frames)."""

    def __init__(self, device: str, use_double: bool):
        from starhe_plugin.ai.models.c3d import C3DRecognizer, preprocess_clips
        self._preprocess = preprocess_clips
        self._use_double = use_double

        if torch.cuda.is_available():
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32      = False
            torch.backends.cudnn.deterministic   = True
            torch.backends.cudnn.benchmark       = False
        if device == "cpu":
            torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True, warn_only=True)

        self._model = C3DRecognizer.from_checkpoint(
            STARHE_RISK_CHECKPOINT, device=device,
            num_classes=2, dropout_ratio=0.5, out_dim=8192,
        )
        if use_double:
            self._model = self._model.double()
        self._model.to(device).eval()
        self._device = device
        dtype_str = "float64" if use_double else "float32"
        go_print("info", f"STARHE-RISK (C3D PyTorch pur) chargé sur {device} [{dtype_str}].")

    @torch.no_grad()
    def predict(self, frames: np.ndarray) -> tuple[float, float]:
        clips  = self._preprocess(frames, use_double=self._use_double).to(self._device)
        logits = self._model(clips)
        probs  = F.softmax(logits, dim=1).mean(0)
        return float(probs[0].item()), float(probs[1].item())

    def close(self) -> None:
        pass


# ─── Interface publique ───────────────────────────────────────────────────────

class STARHERiskModel:
    """
    Interface pour STARHE-RISK (C3D).

    Sélectionne le backend selon C3D_BACKEND (config.py) :
      "mmaction2" → subprocess _c3d_runner.py (mmaction2 officiel)
      "pytorch"   → pure PyTorch (C3DRecognizer local, bit-identique)

    Usage :
        model = STARHERiskModel()
        result = model.predict(frames)  # frames : (T, H, W, 3) uint8 RGB
        model.close()                   # libère le subprocess si mmaction2

    Ou avec context manager :
        with STARHERiskModel() as model:
            result = model.predict(frames)
    """

    LABELS = {0: "Risque faible", 1: "Risque élevé"}

    def __init__(self, device: str | None = None):
        # Résolution du device
        if device:
            _device = device
        elif DETERMINISTIC_INFERENCE:
            _device = "cpu"
        elif INFERENCE_DEVICE != "auto":
            _device = INFERENCE_DEVICE
        elif torch.cuda.is_available():
            _device = "cuda"
        elif torch.backends.mps.is_available():
            _device = "mps"
        else:
            _device = "cpu"

        backend = C3D_BACKEND
        if backend == "mmaction2":
            try:
                self._backend: _MMAction2Backend | _PyTorchBackend = \
                    _MMAction2Backend(_device)
                self._active_backend = "mmaction2"
            except Exception as e:
                go_print("warning",
                         f"STARHE-RISK: mmaction2 backend indisponible ({e}), "
                         "fallback PyTorch pur.")
                self._backend = _PyTorchBackend(_device, DETERMINISTIC_INFERENCE)
                self._active_backend = "pytorch"
        else:
            self._backend = _PyTorchBackend(_device, DETERMINISTIC_INFERENCE)
            self._active_backend = "pytorch"

    def predict(self, frames: np.ndarray) -> dict:
        """
        frames : (T, H, W, 3) uint8 RGB

        Retourne :
            {"risk_score": float [0-1], "risk_label": str, "scores": [float, float]}
        """
        score_low, score_high = self._backend.predict(frames)
        pred_cls  = 1 if score_high >= RISK_THRESHOLD else 0
        go_print("info",
                 f"RISK [{self._active_backend}] : {self.LABELS[pred_cls]} "
                 f"| score={score_high:.3f} (seuil={RISK_THRESHOLD:.2f})")
        return {
            "risk_score": score_high,
            "risk_label": self.LABELS[pred_cls],
            "scores":     [score_low, score_high],
        }

    def close(self) -> None:
        self._backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
