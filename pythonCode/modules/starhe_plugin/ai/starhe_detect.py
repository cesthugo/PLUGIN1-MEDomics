"""
ai/starhe_detect.py — Wrapper STARHE-DETECT (RTMDet via subprocess)
===================================================================
Stratégie : appel externe au script `ai/models/_rtmdet_runner.py`
  via subprocess (Python du venv).

  - Aucun import de mmdet / mmcv côté plugin principal
  - Le runner applique ses propres stubs et patches Python 3.13
  - Les résultats sont échangés via un fichier JSON temporaire

Commande lancée :
  python ai/models/_rtmdet_runner.py \\
      --config  <rtmdet_starhe.py>        \\
      --ckpt    <best_xxx.pth>            \\
      --image   <frame_tmp.png>           \\
      --out     <results.json>            \\
      --score-thr 0.001

  Config     : models/det/bs_4/rtmdet_starhe.py
  Checkpoint : models/det/bs_4/best_coco_bbox_mAP_50_iter_2100.pth
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
    STARHE_DETECT_CONFIG,
    STARHE_DETECT_CHECKPOINT,
    DETECT_SCORE_THRESHOLD,
)
from starhe_plugin.utils.go_print import go_print

# Chemin absolu vers le script runner (même dossier que ce fichier + models/)
_RUNNER_SCRIPT = Path(__file__).parent / "models" / "_rtmdet_runner.py"


# ─── Fonction principale ──────────────────────────────────────────────────────

def run_inference(image_path: str,
                  score_thr: float = DETECT_SCORE_THRESHOLD) -> list:
    """
    Lance RTMDet sur une image via le script runner (subprocess).

    Parameters
    ----------
    image_path : chemin vers le fichier image (JPEG, PNG…)
    score_thr  : seuil de confiance minimum

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
        cmd = [
            sys.executable,
            str(_RUNNER_SCRIPT),
            "--config",    str(STARHE_DETECT_CONFIG),
            "--ckpt",      str(STARHE_DETECT_CHECKPOINT),
            "--image",     str(image_path),
            "--out",       tmp_out,
            "--score-thr", str(score_thr),
        ]

        go_print("info", f"DETECT : inférence RTMDet ({image_path.name})…")
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
                f"Runner RTMDet a échoué (code {result.returncode}):\n"
                f"STDERR: {tail_err}\nSTDOUT: {tail_out}",
            )
            raise RuntimeError(
                f"_rtmdet_runner.py a échoué avec le code {result.returncode}"
            )

        # Lire les résultats JSON
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
    Interface pour STARHE-DETECT (RTMDet via subprocess).

    Usage
    -----
    model = STARHEDetectModel()
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

    def __init__(self, device: str | None = None):
        # device ignoré : défini dynamiquement dans le runner
        go_print("info", "STARHE-DETECT initialisé (mode subprocess runner).")

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
            return run_inference(tmp_path, score_thr=score_thr)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
