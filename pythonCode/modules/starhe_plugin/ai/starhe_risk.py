"""
ai/starhe_risk.py — Wrapper STARHE-RISK (modèle C3D)
=====================================================
Entrée : ciné-clip rognés sous forme de tensor PyTorch (B, C, T, H, W)
Sortie : score de risque [0.0 – 1.0] + classe prédite {0: faible, 1: élevé}

Architecture attendue : C3D (3D-ConvNet)
  Li et al. « Learning Spatiotemporal Features with 3D Convolutional Networks »

Le wrapper est agnostique du poids exact : il charge simplement un fichier .pth
qui expose une architecture state_dict compatible.
"""

import numpy as np
import torch
import torch.nn as nn
import cv2
from starhe_plugin.config import (
    STARHE_RISK_WEIGHTS,
    C3D_INPUT_DEPTH,
    C3D_INPUT_HEIGHT,
    C3D_INPUT_WIDTH,
)
from starhe_plugin.utils.go_print import go_print


# ── Architecture C3D allégée (stub remplaçable par les vrais poids) ───────────

class C3D(nn.Module):
    """
    C3D simplifié — 5 blocs conv3D + 3 FC.
    Remplacer cette classe par l'architecture exacte de STARHE-RISK si différente.
    """
    def __init__(self, num_classes: int = 2):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv3d(3, 64, kernel_size=3, padding=1), nn.ReLU(),
            nn.MaxPool3d(kernel_size=(1, 2, 2), stride=(1, 2, 2)),

            nn.Conv3d(64, 128, kernel_size=3, padding=1), nn.ReLU(),
            nn.MaxPool3d(kernel_size=2, stride=2),

            nn.Conv3d(128, 256, kernel_size=3, padding=1), nn.ReLU(),
            nn.MaxPool3d(kernel_size=2, stride=2),

            nn.Conv3d(256, 256, kernel_size=3, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool3d((1, 4, 4)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(256 * 1 * 4 * 4, 512), nn.ReLU(), nn.Dropout(0.5),
            nn.Linear(512, num_classes),
        )

    def forward(self, x):
        return self.classifier(self.features(x))


class STARHERiskModel:
    """
    Interface haut-niveau pour STARHE-RISK.
    Usage :
        model = STARHERiskModel()
        result = model.predict(frames_array)   # frames_array : (T, H, W, 3) uint8
    """

    def __init__(self, weights_path: str = STARHE_RISK_WEIGHTS,
                 device: str | None = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model  = C3D(num_classes=2).to(self.device)
        self._load_weights(weights_path)
        self.model.eval()
        go_print("info", f"STARHE-RISK chargé sur {self.device}.")

    def _load_weights(self, path: str):
        import os
        if not os.path.exists(path):
            go_print("warning", f"Poids STARHE-RISK introuvables : {path}. Mode stub activé.")
            return
        state = torch.load(path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)
        go_print("info", f"Poids STARHE-RISK chargés depuis {path}.")

    def _preprocess(self, frames: np.ndarray) -> torch.Tensor:
        """
        frames : (T, H, W) ou (T, H, W, 3) uint8
        → tensor (1, 3, T', H', W') float32 normalisé [0,1]
        """
        # Assure 3 canaux
        if frames.ndim == 3:
            frames = np.stack([frames] * 3, axis=-1)  # (T, H, W, 3)

        # Rééchantillonnage temporel → C3D_INPUT_DEPTH frames
        t = frames.shape[0]
        indices = np.linspace(0, t - 1, C3D_INPUT_DEPTH, dtype=int)
        frames  = frames[indices]  # (T', H, W, 3)

        # Resize spatial
        resized = np.stack([
            cv2.resize(f, (C3D_INPUT_WIDTH, C3D_INPUT_HEIGHT)) for f in frames
        ])  # (T', H', W', 3)

        # (T', H', W', 3) → (3, T', H', W')
        tensor = torch.from_numpy(resized).permute(3, 0, 1, 2).float() / 255.0
        return tensor.unsqueeze(0).to(self.device)   # (1, 3, T', H', W')

    @torch.no_grad()
    def predict(self, frames: np.ndarray) -> dict:
        """
        Retourne un dict :
          {
            "risk_score"  : float   [0.0 – 1.0],
            "risk_class"  : int     {0: faible, 1: élevé},
            "risk_label"  : str     {"Faible" | "Élevé"},
            "probabilities": [p0, p1]
          }
        """
        tensor = self._preprocess(frames)
        logits = self.model(tensor)                    # (1, 2)
        probs  = torch.softmax(logits, dim=1).cpu().numpy()[0]
        cls    = int(np.argmax(probs))
        score  = float(probs[1])

        result = {
            "risk_score"   : score,
            "risk_class"   : cls,
            "risk_label"   : "Élevé" if cls == 1 else "Faible",
            "probabilities": probs.tolist(),
        }
        go_print("info", f"STARHE-RISK : score={score:.3f} → {result['risk_label']}")
        return result
