"""
ai/starhe_risk.py — STARHE-RISK wrapper (C3D)
=============================================
Two backends selectable via C3D_BACKEND in config.py:

  "mmaction2" (default): persistent _c3d_runner.py subprocess that loads
      mmaction2's C3D backbone and I3DHead head directly (without the
      mmengine registry, compatible with Python 3.13 + mmcv-lite).
      Requires: mmaction2==1.2.0 installed with --no-deps in the venv.

  "pytorch": pure PyTorch implementation (C3DRecognizer in c3d.py),
      validated bit-identical to mmaction2 on the same input tensors.
      No mmaction2 dependency.

Input  : numpy frames (T, H, W, 3) uint8 RGB
Output : {"risk_score": float, "risk_label": str, "scores": list}
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


# ─── mmaction2 backend (persistent subprocess) ───────────────────────────────

class _MMAction2Backend:
    """Launches _c3d_runner.py as a subprocess and exposes predict(frames)."""

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
        """Sends the frames to the subprocess and returns (score_low, score_high)."""
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


# ─── Pure PyTorch backend ────────────────────────────────────────────────────

class _PyTorchBackend:
    """Loads C3DRecognizer (pure PyTorch) and exposes predict(frames)."""

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


# ─── Public interface ─────────────────────────────────────────────────────────

class STARHERiskModel:
    """
    Interface for STARHE-RISK (C3D).

    Selects the backend according to C3D_BACKEND (config.py):
      "mmaction2" → _c3d_runner.py subprocess (official mmaction2)
      "pytorch"   → pure PyTorch (local C3DRecognizer, bit-identical)

    Usage:
        model = STARHERiskModel()
        result = model.predict(frames)  # frames: (T, H, W, 3) uint8 RGB
        model.close()                   # releases the subprocess if mmaction2

    Or with a context manager:
        with STARHERiskModel() as model:
            result = model.predict(frames)
    """

    LABELS = {0: "Risque faible", 1: "Risque élevé"}

    def __init__(self, device: str | None = None):
        # Device resolution
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
        frames: (T, H, W, 3) uint8 RGB

        Returns:
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
