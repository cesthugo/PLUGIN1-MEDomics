"""
ai/starhe_detect.py — Wrapper STARHE-DETECT (DINO-DETR)
========================================================
Entrée : frame individuel (H, W, 3) uint8
Sortie : liste de boîtes englobantes avec scores et classes

Architecture attendue : DINO-DETR
  Zhang et al. « DINO: DETR with Improved DeNoising Anchor Boxes »

Le wrapper produit des prédictions au format COCO-like.
"""

import numpy as np
import torch
import torch.nn as nn
import cv2
from starhe_plugin.config import (
    STARHE_DETECT_WEIGHTS,
    DINO_INPUT_SIZE,
    DETECT_SCORE_THRESHOLD,
)
from starhe_plugin.utils.go_print import go_print


# ── Stub DINO-DETR (remplacer par l'import HuggingFace / repo officiel) ───────

class DINODETRStub(nn.Module):
    """
    Stub minimal : retourne des prédictions vides.
    À remplacer par :
      from transformers import AutoModelForObjectDetection
      model = AutoModelForObjectDetection.from_pretrained("path/to/dino-detr")
    """
    def forward(self, pixel_values):
        batch = pixel_values.shape[0]
        # format : (boxes, scores, labels) toutes vides
        return {
            "pred_boxes" : torch.zeros(batch, 0, 4),
            "pred_logits": torch.zeros(batch, 0, 2),
        }


class STARHEDetectModel:
    """
    Interface haut-niveau pour STARHE-DETECT.
    Usage :
        model = STARHEDetectModel()
        detections = model.predict(frame)   # frame : (H, W, 3) uint8
    """

    LABEL_MAP = {0: "lésion_bénigne", 1: "lésion_maligne"}

    def __init__(self, weights_path: str = STARHE_DETECT_WEIGHTS,
                 device: str | None = None):
        self.device    = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model     = DINODETRStub().to(self.device)
        self.threshold = DETECT_SCORE_THRESHOLD
        self._load_weights(weights_path)
        self.model.eval()
        go_print("info", f"STARHE-DETECT chargé sur {self.device}.")

    def _load_weights(self, path: str):
        import os
        if not os.path.exists(path):
            go_print("warning", f"Poids STARHE-DETECT introuvables : {path}. Mode stub activé.")
            return
        state = torch.load(path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)
        go_print("info", f"Poids STARHE-DETECT chargés depuis {path}.")

    def _preprocess(self, frame: np.ndarray) -> torch.Tensor:
        """
        frame : (H, W, 3) uint8
        → tensor (1, 3, H', W') float32 normalisé [0,1]
        """
        h, w = DINO_INPUT_SIZE
        resized = cv2.resize(frame, (w, h))
        tensor  = torch.from_numpy(resized).permute(2, 0, 1).float() / 255.0
        return tensor.unsqueeze(0).to(self.device)

    def _postprocess(self, outputs: dict, orig_shape: tuple) -> list[dict]:
        """
        Convertit les sorties brutes du modèle en liste de détections.
        Chaque détection : {"bbox": [x0,y0,x1,y1], "score": float, "label": str}
        Les coordonnées sont ramenées à l'espace de l'image originale.
        """
        orig_h, orig_w = orig_shape[:2]
        inp_h,  inp_w  = DINO_INPUT_SIZE

        boxes  = outputs["pred_boxes"].cpu().numpy()[0]   # (N, 4)  cxcywh normalisé
        logits = outputs["pred_logits"].cpu().numpy()[0]  # (N, num_classes)

        if boxes.shape[0] == 0:
            return []

        scores = self._softmax(logits)                    # (N, num_classes)
        max_scores  = scores.max(axis=1)
        max_classes = scores.argmax(axis=1)

        detections = []
        for i, (box, score, cls) in enumerate(zip(boxes, max_scores, max_classes)):
            if score < self.threshold:
                continue
            cx, cy, bw, bh = box
            # dé-normalisation → pixels image originale
            x0 = int((cx - bw / 2) * orig_w)
            y0 = int((cy - bh / 2) * orig_h)
            x1 = int((cx + bw / 2) * orig_w)
            y1 = int((cy + bh / 2) * orig_h)
            detections.append({
                "bbox" : [max(0, x0), max(0, y0),
                          min(orig_w, x1), min(orig_h, y1)],
                "score": float(score),
                "label": self.LABEL_MAP.get(int(cls), f"classe_{cls}"),
            })

        return detections

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        e = np.exp(x - x.max(axis=1, keepdims=True))
        return e / e.sum(axis=1, keepdims=True)

    @torch.no_grad()
    def predict(self, frame: np.ndarray) -> list[dict]:
        """
        Retourne la liste des lésions détectées dans le frame.
        Chaque entrée :
          {
            "bbox"  : [x0, y0, x1, y1],   # pixels, image originale
            "score" : float,               # confiance [0–1]
            "label" : str                  # "lésion_bénigne" | "lésion_maligne"
          }
        """
        orig_shape = frame.shape
        tensor     = self._preprocess(frame)
        outputs    = self.model(tensor)
        dets       = self._postprocess(outputs, orig_shape)

        go_print("info", f"STARHE-DETECT : {len(dets)} détection(s) (seuil={self.threshold}).")
        return dets

    def draw_detections(self, frame: np.ndarray,
                        detections: list[dict]) -> np.ndarray:
        """
        Superpose les bbox de détection sur une copie du frame (BGR pour OpenCV).
        """
        vis = frame.copy()
        for det in detections:
            x0, y0, x1, y1 = det["bbox"]
            color = (0, 0, 220) if "maligne" in det["label"] else (0, 180, 0)
            cv2.rectangle(vis, (x0, y0), (x1, y1), color, 2)
            label_text = f"{det['label']} {det['score']:.2f}"
            cv2.putText(vis, label_text, (x0, max(y0 - 6, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        return vis
