"""
ai/starhe_detect.py — Wrapper STARHE-DETECT (RTMDet ou DINO via subprocess)
============================================================================
Stratégie : subprocess persistant (mode serveur) pour RTMDet.
Le runner est lancé UNE SEULE FOIS par instance STARHEDetectModel,
le modèle reste en mémoire, les frames sont envoyées via stdin JSON.

  - Aucun import de mmdet / mmcv côté plugin principal
  - Le runner applique ses propres stubs et patches Python 3.13
  - Communication : stdin/stdout JSON (une ligne par requête/réponse)
  - Fallback one-shot pour DINO (pas de mode serveur implémenté)

Backend sélectionné par DETECT_BACKEND dans config.py :
  "rtmdet" (défaut) → ai/models/_rtmdet_runner.py  (mode serveur)
  "dino"            → ai/models/_dino_runner.py     (mode one-shot)
"""

import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path

import base64
import numpy as np
import cv2

from starhe_plugin.config import (
    DETECT_BACKEND,
    DETECT_BATCH_SIZE,
    DETERMINISTIC_INFERENCE,
    INFERENCE_DEVICE,
    STARHE_DETECT_CONFIG,
    STARHE_DETECT_CHECKPOINT,
    STARHE_DINO_CONFIG,
    STARHE_DINO_CHECKPOINT,
    STARHE_SHARE_ROOT,
    DETECT_SCORE_THRESHOLD,
)
from starhe_plugin.utils.go_print import go_print

# Chemins vers les scripts runner (même dossier que ce fichier + models/)
_RTMDET_RUNNER = Path(__file__).parent / "models" / "_rtmdet_runner.py"
_DINO_RUNNER   = Path(__file__).parent / "models" / "_dino_runner.py"


# ─── Fonction one-shot (legacy / DINO) ───────────────────────────────────────

def run_inference(image_path: str,
                  score_thr: float = DETECT_SCORE_THRESHOLD,
                  backend: str = DETECT_BACKEND) -> list:
    """
    Lance l'inférence de détection sur une image via subprocess one-shot.
    Utilisé pour DINO ou comme fallback si le mode serveur n'est pas disponible.
    """
    image_path = Path(image_path).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image introuvable : {image_path}")

    tmp_fd, tmp_out = tempfile.mkstemp(suffix=".json", prefix="starhe_det_")
    os.close(tmp_fd)

    try:
        if backend == "dino":
            cmd = [
                sys.executable,
                str(_DINO_RUNNER),
                "--config",      str(STARHE_DINO_CONFIG),
                "--ckpt",        str(STARHE_DINO_CHECKPOINT),
                "--starhe-root", str(STARHE_SHARE_ROOT),
                "--image",       str(image_path),
                "--out",         tmp_out,
                "--score-thr",   str(score_thr),
            ]
            backend_label = "DINO-DETR"
        else:
            cmd = [
                sys.executable,
                str(_RTMDET_RUNNER),
                "--config",    str(STARHE_DETECT_CONFIG),
                "--ckpt",      str(STARHE_DETECT_CHECKPOINT),
                "--image",     str(image_path),
                "--out",       tmp_out,
                "--score-thr", str(score_thr),
            ]
            backend_label = "RTMDet"

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            tail_err = (result.stderr or "")[-2000:]
            raise RuntimeError(
                f"runner {backend_label} a échoué (code {result.returncode}): {tail_err}"
            )

        return json.loads(Path(tmp_out).read_text(encoding="utf-8"))

    finally:
        try:
            os.unlink(tmp_out)
        except OSError:
            pass


# ─── Classe de haut niveau ────────────────────────────────────────────────────

class STARHEDetectModel:
    """
    Interface pour STARHE-DETECT avec subprocess persistant (RTMDet).

    Au premier appel à predict(), lance le runner en mode serveur et
    maintient le processus ouvert pour toute la durée de vie de l'objet.
    Le modèle RTMDet (428 MB) est chargé UNE SEULE FOIS.

    Usage
    -----
    with STARHEDetectModel() as model:
        for frame in frames:
            dets = model.predict(frame)

    Ou sans context manager (close() manuel obligatoire) :
        model = STARHEDetectModel()
        dets  = model.predict(frame)
        model.close()
    """

    def __init__(self, device: str | None = None, backend: str = DETECT_BACKEND):
        self._backend    = backend
        self._device     = device or INFERENCE_DEVICE  # "auto" | "cpu" | "cuda" | "mps"
        self._proc       = None          # subprocess.Popen
        self._tmp_dir    = None          # dossier temporaire (fallback one-shot)
        self.batch_size  = 1             # updated by _start_server() if auto
        if backend == "rtmdet":
            self._start_server()
        else:
            go_print("info", f"STARHE-DETECT initialisé (backend={backend}, mode one-shot).")

    # ── Cycle de vie du serveur ───────────────────────────────────────────────

    def _start_server(self):
        """Lance le runner RTMDet en mode serveur et attend le signal READY."""
        cmd = [
            sys.executable,
            str(_RTMDET_RUNNER),
            "--config",    str(STARHE_DETECT_CONFIG),
            "--ckpt",      str(STARHE_DETECT_CHECKPOINT),
            "--score-thr", str(DETECT_SCORE_THRESHOLD),
            "--mode",      "server",
        ]
        if self._device != "auto":
            cmd += ["--device", self._device]
        if DETERMINISTIC_INFERENCE:
            # Force CPU + float64 dans le subprocess runner pour reproductibilité
            # cross-plateforme (élimine MPS/CUDA vs CPU et BLAS MKL↔Accelerate).
            cmd += ["--deterministic"]
        go_print("info", "STARHE-DETECT : démarrage du serveur RTMDet (chargement modèle)…")
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,          # line-buffered
        )
        # Attendre le signal READY du runner (inclut les infos hardware)
        ready_line = self._proc.stdout.readline().strip()
        if "[rtmdet_server] READY" not in ready_line:
            stderr_out = self._proc.stderr.read(2000) if self._proc.stderr else ""
            self._proc = None
            raise RuntimeError(
                f"Le serveur RTMDet n'a pas répondu READY. Reçu: {ready_line!r}\n{stderr_out}"
            )

        # ── Parse hardware info from READY message ────────────────────────
        hw_info = {}
        hw_json = ready_line.split("READY", 1)[-1].strip()
        if hw_json:
            try:
                hw_info = json.loads(hw_json)
            except json.JSONDecodeError:
                pass

        # ── Compute optimal batch size ────────────────────────────────────
        if DETECT_BATCH_SIZE == "auto":
            from starhe_plugin.utils.hardware import compute_optimal_batch_size
            self.batch_size = compute_optimal_batch_size(
                device=hw_info.get("device", "cpu"),
                vram_free_mb=hw_info.get("vram_free_mb"),
                ram_free_mb=hw_info.get("ram_free_mb"),
            )
        else:
            self.batch_size = int(DETECT_BATCH_SIZE)

        device_str = hw_info.get("device", "?")
        mem_str = ""
        if "vram_free_mb" in hw_info:
            mem_str = f", vram_free={hw_info['vram_free_mb']:.0f} MB"
        elif "ram_free_mb" in hw_info:
            mem_str = f", ram_free={hw_info['ram_free_mb']:.0f} MB"
        go_print("info",
                 f"STARHE-DETECT : serveur prêt — batch_size={self.batch_size}"
                 f", device={device_str}{mem_str}")

    def close(self):
        """Ferme proprement le subprocess serveur."""
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.stdin.write("__EXIT__\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=10)
            except Exception:
                self._proc.kill()
            self._proc = None
        # Nettoyage du dossier temporaire
        if self._tmp_dir and os.path.isdir(self._tmp_dir):
            import shutil
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
            self._tmp_dir = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # ── Inférence ─────────────────────────────────────────────────────────────

    def predict(self, frame: np.ndarray,
                score_thr: float = DETECT_SCORE_THRESHOLD) -> list:
        """
        frame     : (H, W, 3) uint8 RGB
        score_thr : seuil de confiance minimum
        """
        return self.predict_batch([frame], score_thr=score_thr)[0]

    def predict_batch(self, frames: list[np.ndarray],
                      score_thr: float = DETECT_SCORE_THRESHOLD) -> list[list]:
        """
        Batch inference: sends N frames in a single request to the server
        via base64 encoding (no disk I/O).
        Returns a list of N detection lists.

        frames    : list of (H, W, 3) uint8 RGB
        score_thr : minimum confidence threshold
        """
        if not frames:
            return []
        if self._backend != "rtmdet" or self._proc is None:
            return [self._predict_oneshot(f, score_thr) for f in frames]

        # Encode all frames as base64 BGR
        frames_b64 = []
        shapes = []
        for frame in frames:
            bgr = cv2.cvtColor(np.ascontiguousarray(frame), cv2.COLOR_RGB2BGR)
            frames_b64.append(base64.b64encode(bgr.tobytes()).decode("ascii"))
            shapes.append(list(bgr.shape))

        req = json.dumps({"frames_b64": frames_b64, "shapes": shapes,
                          "score_thr": score_thr})
        try:
            self._proc.stdin.write(req + "\n")
            self._proc.stdin.flush()
            resp_line = self._proc.stdout.readline().strip()
            if not resp_line:
                raise RuntimeError("Le serveur RTMDet n'a pas répondu au batch.")
            resp = json.loads(resp_line)
            if isinstance(resp, dict) and "error" in resp:
                raise RuntimeError(f"Erreur runner batch : {resp['error']}")
            return resp
        except Exception as exc:
            go_print("error", f"DETECT batch : {exc} — fallback séquentiel.")
            return [self._predict_oneshot(f, score_thr) for f in frames]

    def _predict_oneshot(self, frame: np.ndarray, score_thr: float) -> list:
        """Fallback : subprocess one-shot (ancien comportement)."""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="starhe_frm_")
        try:
            os.close(tmp_fd)
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            cv2.imwrite(tmp_path, bgr)
            return run_inference(tmp_path, score_thr=score_thr, backend=self._backend)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

