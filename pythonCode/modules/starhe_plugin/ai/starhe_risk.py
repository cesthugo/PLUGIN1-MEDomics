"""
ai/starhe_risk.py — Wrapper STARHE-RISK (C3D — inférence PyTorch pure)
=======================================================================
Entrée  : frames numpy (T, H, W, 3) uint8 RGB
Sortie  : {"risk_score": float, "risk_label": str, "scores": list}

Pas de dépendance mmaction2/mmcv : le modèle C3D est implémenté
directement dans ai/models/c3d.py avec des noms de sous-modules
identiques au checkpoint mmaction2, ce qui permet le chargement direct.

Pipeline de prétraitement reproduit du test_pipeline mmaction2 :
  clip_len=16, num_clips=10, resize=128, center_crop=112
  mean=[104,117,128], std=[1,1,1] (frames RGB float32, pas de /255)
"""

import numpy as np
import torch
import torch.nn.functional as F

from starhe_plugin.config import STARHE_RISK_CHECKPOINT
from starhe_plugin.utils.go_print import go_print
from starhe_plugin.ai.models.c3d import C3DRecognizer, preprocess_clips


class STARHERiskModel:
    """
    Interface pour STARHE-RISK (C3D pur PyTorch).
    Usage :
        model = STARHERiskModel()
        result = model.predict(frames)  # frames : (T, H, W, 3) uint8 RGB
    Retourne :
        {"risk_score": float [0-1], "risk_label": str, "scores": [float, float]}
    """

    LABELS = {0: "Risque faible", 1: "Risque élevé"}

    def __init__(self, device: str | None = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model = None
        self._load()

    def _load(self):
        self._model = C3DRecognizer.from_checkpoint(
            STARHE_RISK_CHECKPOINT,
            device=self.device,
            num_classes=2,
            dropout_ratio=0.5,
            out_dim=8192,
        )
        self._model.to(self.device)
        self._model.eval()
        go_print("info",
                 f"STARHE-RISK (C3D pur PyTorch) chargé sur {self.device}.")

    @torch.no_grad()
    def predict(self, frames: np.ndarray) -> dict:
        """
        frames : (T, H, W, 3) uint8 RGB

        Inférence sur 10 clips (NUM_CLIPS), moyenne des softmax
        → identique à average_clips='prob' dans mmaction2.
        """
        clips = preprocess_clips(frames).to(self.device)  # (10, 3, 16, 112, 112)

        logits = self._model(clips)              # (10, 2)
        probs  = F.softmax(logits, dim=1)        # (10, 2)
        avg    = probs.mean(dim=0)               # (2,)

        scores     = avg.cpu().numpy().tolist()
        pred_cls   = int(avg.argmax().item())
        risk_score = float(scores[1])            # proba classe 1 (risque élevé)

        go_print("info",
                 f"RISK : {self.LABELS[pred_cls]} | score={risk_score:.3f}")
        return {
            "risk_score": risk_score,
            "risk_label": self.LABELS[pred_cls],
            "scores":     scores,
        }

