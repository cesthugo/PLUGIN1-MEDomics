"""
ai/models/c3d.py — C3D en PyTorch pur
======================================
Architecture identique à mmaction2 C3D (ConvModule) + I3DHead.
Les noms de sous-modules reproduisent exactement ceux du framework
mmaction2 afin que les checkpoints .pth soient chargés directement
sans aucune remise en correspondance des clés.

Correspondance des clés state_dict mmaction2 → ce module :
  backbone.conv1a.conv.weight   ← _CvM.conv  (ConvModule → sous-attr .conv)
  backbone.fc6.weight
  backbone.fc7.weight
  cls_head.fc_cls.weight
  cls_head.fc_cls.bias
  (data_preprocessor.* ignorés — non présents dans ce modèle)

Référence :
  Tran et al., "Learning Spatiotemporal Features with 3D Convolutional
  Networks", ICCV 2015.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ── _CvM : reproduction minimale de mmcv.cnn.ConvModule (Conv3d + ReLU) ───────

class _CvM(nn.Module):
    """
    Reproduit la structure d'un mmcv.ConvModule (Conv3d, sans BN, avec ReLU).
    Les noms des attributs correspondent aux clés du checkpoint :
      .conv      → Conv3d (clé : backbone.convXx.conv.weight)
      .activate  → ReLU   (pas de paramètres enregistrés)
    """

    def __init__(self, in_c: int, out_c: int,
                 kernel_size=(3, 3, 3),
                 padding=(1, 1, 1),
                 bias: bool = True):
        super().__init__()
        self.conv     = nn.Conv3d(in_c, out_c,
                                  kernel_size=kernel_size,
                                  padding=padding,
                                  bias=bias)
        self.activate = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.activate(self.conv(x))


# ── C3DBackbone : identique à mmaction2/models/backbones/c3d.py ───────────────

class C3DBackbone(nn.Module):
    """
    Backbone C3D avec les mêmes noms de sous-modules que mmaction2 :
      conv1a … conv5b  (wrapped dans _CvM → clé .conv)
      pool1  … pool5
      fc6, fc7, relu, dropout
    Sortie : tenseur (N, 4096) après fc6/fc7.
    """

    def __init__(self, dropout_ratio: float = 0.5, out_dim: int = 8192):
        super().__init__()
        kw = dict(kernel_size=(3, 3, 3), padding=(1, 1, 1))

        self.conv1a = _CvM(3,   64,  **kw)
        self.pool1  = nn.MaxPool3d(kernel_size=(1, 2, 2), stride=(1, 2, 2))

        self.conv2a = _CvM(64,  128, **kw)
        self.pool2  = nn.MaxPool3d(kernel_size=(2, 2, 2), stride=(2, 2, 2))

        self.conv3a = _CvM(128, 256, **kw)
        self.conv3b = _CvM(256, 256, **kw)
        self.pool3  = nn.MaxPool3d(kernel_size=(2, 2, 2), stride=(2, 2, 2))

        self.conv4a = _CvM(256, 512, **kw)
        self.conv4b = _CvM(512, 512, **kw)
        self.pool4  = nn.MaxPool3d(kernel_size=(2, 2, 2), stride=(2, 2, 2))

        self.conv5a = _CvM(512, 512, **kw)
        self.conv5b = _CvM(512, 512, **kw)
        self.pool5  = nn.MaxPool3d(kernel_size=(2, 2, 2),
                                   stride=(2, 2, 2),
                                   padding=(0, 1, 1))

        self.fc6     = nn.Linear(out_dim, 4096)
        self.fc7     = nn.Linear(4096,    4096)
        self.relu    = nn.ReLU()
        self.dropout = nn.Dropout(p=dropout_ratio)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Entrée : (N, 3, T, H, W)
        x = self.conv1a(x);                 x = self.pool1(x)
        x = self.conv2a(x);                 x = self.pool2(x)
        x = self.conv3a(x); x = self.conv3b(x); x = self.pool3(x)
        x = self.conv4a(x); x = self.conv4b(x); x = self.pool4(x)
        x = self.conv5a(x); x = self.conv5b(x); x = self.pool5(x)

        x = x.flatten(start_dim=1)           # (N, out_dim)
        x = self.relu(self.fc6(x))
        x = self.dropout(x)
        x = self.relu(self.fc7(x))           # (N, 4096)
        return x


# ── I3DHead : identique à mmaction2/models/heads/i3d_head.py ─────────────────

class I3DHead(nn.Module):
    """
    Tête I3D avec spatial_type=None (pas d'avg_pool).
    Clés dans le checkpoint : cls_head.fc_cls.weight / .bias
    """

    def __init__(self, in_channels: int = 4096,
                 num_classes: int = 2,
                 dropout_ratio: float = 0.5):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout_ratio)
        self.fc_cls  = nn.Linear(in_channels, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.dropout(x)
        return self.fc_cls(x)


# ── C3DRecognizer : modèle complet = backbone + cls_head ─────────────────────

class C3DRecognizer(nn.Module):
    """
    Modèle C3D complet (backbone + cls_head).
    Structure et nommage identiques à mmaction2 Recognizer3D(C3D + I3DHead),
    ce qui permet de charger directement les checkpoints mmaction2.
    """

    def __init__(self, num_classes: int = 2,
                 dropout_ratio: float = 0.5,
                 out_dim: int = 8192):
        super().__init__()
        self.backbone = C3DBackbone(dropout_ratio=dropout_ratio, out_dim=out_dim)
        self.cls_head = I3DHead(in_channels=4096,
                                num_classes=num_classes,
                                dropout_ratio=dropout_ratio)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.cls_head(self.backbone(x))

    @classmethod
    def from_checkpoint(cls, path: str,
                        device: str = 'cpu',
                        **kwargs) -> 'C3DRecognizer':
        """Charge le modèle depuis un checkpoint mmaction2."""
        model = cls(**kwargs)
        ckpt  = torch.load(path, map_location=device, weights_only=False)
        state = ckpt.get('state_dict', ckpt)
        # Ignorer les clés data_preprocessor (non présentes dans notre module)
        state = {k: v for k, v in state.items()
                 if not k.startswith('data_preprocessor')}
        missing, unexpected = model.load_state_dict(state, strict=False)
        if missing:
            raise RuntimeError(f"Clés manquantes dans le checkpoint : {missing}")
        return model


# ── Prétraitement : équivalent du test_pipeline mmaction2 ─────────────────────

# ActionDataPreprocessor : mean=[104,117,128], std=[1,1,1] appliqués aux
# frames RGB float32 (sans division par 255 — les valeurs restent en 0-255).
_MEAN = np.array([104.0, 117.0, 128.0], dtype=np.float32)

CLIP_LEN    = 16   # frames par clip
RESIZE_SIZE = 128  # côté court cible (px)
CROP_SIZE   = 112  # crop central (px)
NUM_CLIPS   = 10   # clips de test → moyenne des probas (average_clips='prob')


def _sample_clips(total: int) -> np.ndarray:
    """
    Équivalent de SampleFrames(clip_len=16, num_clips=10, test_mode=True).
    Retourne (NUM_CLIPS, CLIP_LEN) indices de frames dans [0, total).
    """
    if total <= 0:
        return np.zeros((NUM_CLIPS, CLIP_LEN), dtype=int)

    if total < CLIP_LEN:
        base = np.arange(CLIP_LEN) % total
        return np.tile(base, (NUM_CLIPS, 1))

    avg_interval = max((total - CLIP_LEN) / float(NUM_CLIPS), 1.0)
    offsets = (np.arange(NUM_CLIPS) * avg_interval
               + avg_interval / 2.0).astype(int)
    offsets = np.clip(offsets, 0, total - CLIP_LEN)
    return np.stack([np.arange(o, o + CLIP_LEN) for o in offsets])


def _resize_shortest(frame: np.ndarray) -> np.ndarray:
    """Redimensionne pour que le côté court soit RESIZE_SIZE px.

    Utilise F.interpolate (noyau C++ identique sur toutes les plateformes)
    au lieu de cv2.resize dont l'implémentation SIMD diffère entre
    x86 (AVX2, Windows) et ARM NEON (macOS Apple Silicon).
    """
    h, w = frame.shape[:2]
    if h <= w:
        nh, nw = RESIZE_SIZE, max(1, round(w * RESIZE_SIZE / h))
    else:
        nh, nw = max(1, round(h * RESIZE_SIZE / w)), RESIZE_SIZE
    t = torch.from_numpy(
        np.ascontiguousarray(frame, dtype=np.float32)
    ).permute(2, 0, 1).unsqueeze(0)                    # (1, 3, H, W)
    t = F.interpolate(t, size=(nh, nw), mode='bilinear', align_corners=False)
    return t.squeeze(0).permute(1, 2, 0).numpy()       # (nh, nw, 3) float32


def preprocess_clips(frames: np.ndarray) -> torch.Tensor:
    """
    Prépare les tenseurs d'entrée pour C3DRecognizer.

    Args:
        frames : (T, H, W, 3) uint8 RGB

    Returns:
        Tensor (NUM_CLIPS, 3, CLIP_LEN, CROP_SIZE, CROP_SIZE) float32
    """
    T           = len(frames)
    clip_idx    = _sample_clips(T)      # (NUM_CLIPS, CLIP_LEN)
    result      = []

    for ci in clip_idx:
        clip = []
        for idx in ci:
            f = _resize_shortest(frames[int(idx)])
            h, w = f.shape[:2]
            y = (h - CROP_SIZE) // 2
            x = (w - CROP_SIZE) // 2
            f = f[y:y + CROP_SIZE, x:x + CROP_SIZE, :]  # (112, 112, 3)
            clip.append(f)

        clip_arr = np.stack(clip).astype(np.float32) - _MEAN  # (16, 112, 112, 3)
        clip_arr = clip_arr.transpose(3, 0, 1, 2)             # (3, 16, 112, 112)
        result.append(clip_arr)

    arr = np.stack(result)               # (NUM_CLIPS, 3, 16, 112, 112)
    return torch.from_numpy(arr)
