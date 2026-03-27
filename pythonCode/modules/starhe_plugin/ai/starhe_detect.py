"""
ai/starhe_detect.py — Wrapper STARHE-DETECT (RTMDet ou DINO via subprocess)
============================================================================
Stratégie : appel externe au script runner via subprocess (Python du venv).

  - Aucun import de mmdet / mmcv côté plugin principal
  - Le runner applique ses propres stubs et patches Python 3.13
  - Les résultats sont échangés via un fichier JSON temporaire

Backend sélectionné par DETECT_BACKEND dans config.py :
  "rtmdet" (défaut) → ai/models/_rtmdet_runner.py
  "dino"            → ai/models/_dino_runner.py

RTMDet :
  Config     : models/det/bs_4/rtmdet_starhe.py
  Checkpoint : models/det/bs_4/best_coco_bbox_mAP_50_iter_2100.pth

DINO :
  Config     : starhe_share/configs/custom/dino_starhe.py
  Checkpoint : models/det/bs_4/best_coco_bbox_mAP_50_iter_2100.pth
  Nécessite  : STARHE_SHARE_ROOT (package `starhe` enregistré dans le runner)
"""

import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path

import numpy as np
import cv2

from starhe_plugin.config import (
    DETECT_BACKEND,
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


# ─── Fonction principale ──────────────────────────────────────────────────────

def run_inference(image_path: str,
                  score_thr: float = DETECT_SCORE_THRESHOLD,
                  backend: str = DETECT_BACKEND) -> list:
    """
    Lance l'inférence de détection sur une image via subprocess.

    Parameters
    ----------
    image_path : chemin vers le fichier image (JPEG, PNG…)
    score_thr  : seuil de confiance minimum
    backend    : "rtmdet" ou "dino" (priorité sur DETECT_BACKEND de config.py)

    Returns
    -------
    list of dict {"bbox": [x0,y0,x1,y1], "score": float, "label": str}
    Coordonnées en pixels xyxy, repère de l'image originale.
    """
    image_path = Path(image_path).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image introuvable : {image_path}")

    # Fichier de sortie JSON temporaire
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

        go_print("info", f"DETECT : inférence {backend_label} ({image_path.name})…")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            tail_err = (result.stderr or "")[-2000:]
            tail_out = (result.stdout or "")[-500:]
            go_print(
                "error",
                f"Runner {backend_label} a échoué (code {result.returncode}):\n"
                f"STDERR: {tail_err}\nSTDOUT: {tail_out}",
            )
            raise RuntimeError(
                f"runner a échoué avec le code {result.returncode}"
            )

        detections = json.loads(Path(tmp_out).read_text(encoding="utf-8"))
        go_print("info", f"DETECT : {len(detections)} lésion(s) détectée(s).")
        return detections

    finally:
        try:
            os.unlink(tmp_out)
        except OSError:
            pass


# ─── Classe de haut niveau ────────────────────────────────────────────────────

class STARHEDetectModel:
    """
    Interface pour STARHE-DETECT (RTMDet ou DINO via subprocess).

    Usage
    -----
    model = STARHEDetectModel()                       # backend selon config.py
    model = STARHEDetectModel(backend="dino")         # forcer DINO
    dets  = model.predict(frame)   # frame : (H, W, 3) uint8 RGB

    Retourne
    --------
    [{"bbox": [x0,y0,x1,y1], "score": float, "label": str}, ...]

    Note
    ----
    Aucun modèle maintenu en mémoire. Chaque appel à predict() lance
    un sous-processus Python dédié. Pour des images déjà sur disque,
    préférer run_inference(image_path) directement.
    """

    def __init__(self, device: str | None = None, backend: str = DETECT_BACKEND):
        # device ignoré : défini dynamiquement dans le runner
        self._backend = backend
        go_print("info", f"STARHE-DETECT initialisé (backend={backend}, mode subprocess).")

    def predict(self, frame: np.ndarray,
                score_thr: float = DETECT_SCORE_THRESHOLD) -> list:
        """
        frame     : (H, W, 3) uint8 RGB
        score_thr : seuil de confiance minimum
        """
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
