"""
ai/models/dino.py — Inférence DINO-DETR sans mmcv C-extension
==============================================================
Stratégie identique à rtmdet.py :
  1. Stub mmcv._ext (module C absent) *avant* tout import mmdet
  2. Patch NMSop.forward  →  torchvision.ops.nms (CPU/GPU, pas de C-ext)
  3. Enregistrement des modules custom starhe (DINO, RAYDINO) via sys.path
  4. Chargement du modèle via mmdet.apis.init_detector
  5. Inférence : LoadImageFromNDArray → pipeline → inference_detector

Pipeline de prétraitement (config dino_starhe.py) :
  Resize(1333×800, keep_ratio=True)
  Normalise : mean=[123.675, 116.28, 103.53]  std=[58.395, 57.12, 57.375]
  bgr_to_rgb=True  (DetDataPreprocessor s'en charge)
  Format : BGR uint8 en entrée (convention OpenCV/MMDetection)
"""

import sys
import types
import os

import cv2
import numpy as np
import torch
import torchvision.ops as tv_ops

# ─── 1. Stub mmcv._ext ───────────────────────────────────────────────────────
# Doit être fait avant tout import de mmcv.ops, mmdet, etc.
if "mmcv._ext" not in sys.modules:
    class _CExtStub(types.ModuleType):
        """Remplace le module C mmcv._ext — chaque attribut lève RuntimeError."""
        def __getattr__(self, name):
            def _unavailable(*args, **kwargs):
                raise RuntimeError(
                    f"mmcv._ext.{name} : C-extension absente (mmcv non compilé)."
                )
            return _unavailable
    sys.modules["mmcv._ext"] = _CExtStub("mmcv._ext")

# ─── 2. Stub tqdm si absent ───────────────────────────────────────────────────
try:
    import tqdm  # noqa: F401
except ImportError:
    _tqdm_mod = types.ModuleType("tqdm")
    _tqdm_mod.tqdm = lambda it=None, *a, **kw: (it if it is not None else iter([]))
    sys.modules.setdefault("tqdm", _tqdm_mod)
    sys.modules.setdefault("tqdm.auto", _tqdm_mod)

# ─── 3. Patch inspect.getmodule (Python 3.13 / mmengine compat) ──────────────
import inspect as _inspect
import types as _types

_orig_inspect_getmodule = _inspect.getmodule


def _safe_getmodule(obj, _filename=None):
    try:
        return _orig_inspect_getmodule(obj, _filename)
    except (AttributeError, TypeError, OSError):
        if isinstance(obj, _types.FrameType):
            mod_name = obj.f_globals.get("__name__")
            if mod_name:
                import sys as _sys
                return _sys.modules.get(mod_name)
        return None


_inspect.getmodule = _safe_getmodule

# ─── 4. Patch NMSop.forward avec torchvision.ops.nms ────────────────────────
import mmcv.ops.nms           # noqa: E402
from mmcv.ops.nms import NMSop  # noqa: E402


def _tv_nms_fwd(ctx, bboxes, scores, iou_threshold,
                offset, score_threshold, max_num):
    """Remplace ext_module.nms() par torchvision.ops.nms (pas de C-ext)."""
    is_filtering = score_threshold > 0
    if is_filtering:
        valid_mask = scores > score_threshold
        valid_inds = valid_mask.nonzero(as_tuple=False).squeeze(dim=1)
        bboxes = bboxes[valid_mask]
        scores = scores[valid_mask]
    else:
        valid_inds = None

    inds = tv_ops.nms(bboxes.float(), scores.float(), float(iou_threshold))

    if max_num > 0:
        inds = inds[:max_num]
    if is_filtering and valid_inds is not None:
        inds = valid_inds[inds]
    return inds


NMSop.forward = staticmethod(_tv_nms_fwd)

# ─── 5. Imports mmdet (désormais sûrs après stub + patch) ────────────────────
from mmcv.transforms import Compose        # noqa: E402
from mmdet.apis import init_detector, inference_detector  # noqa: E402


# ─── 6. Enregistrement des modules custom starhe ─────────────────────────────

def _ensure_starhe_importable(starhe_share_root: str) -> None:
    """
    Ajoute starhe_share_root au sys.path pour que `import starhe` fonctionne.
    Cela déclenche les @MODELS.register_module() du package starhe.
    """
    if starhe_share_root not in sys.path:
        sys.path.insert(0, starhe_share_root)
    try:
        import starhe.models  # noqa: F401 — enregistre DINO, RAYDINO, etc.
    except ImportError as e:
        raise ImportError(
            f"Impossible d'importer le package starhe depuis {starhe_share_root}.\n"
            "Vérifiez que STARHE_SHARE_ROOT (config.py) pointe vers le dossier "
            "contenant le package `starhe/`."
        ) from e


# ─── Classe principale ────────────────────────────────────────────────────────

class DINOInference:
    """
    Chargement et inférence DINO-DETR (mmdet + modules custom starhe).

    Usage
    -----
    detector = DINOInference.from_checkpoint(
        cfg_path, ckpt_path, starhe_share_root, device
    )
    dets = detector.detect(frame)   # frame : (H, W, 3) uint8 RGB
    """

    def __init__(self, model, test_pipeline, class_names: list[str], device: str):
        self._model         = model
        self._test_pipeline = test_pipeline
        self._class_names   = class_names
        self._device        = device

    @classmethod
    def from_checkpoint(
        cls,
        cfg_path:          str,
        ckpt_path:         str,
        starhe_share_root: str,
        device:            str | None = None,
    ) -> "DINOInference":
        """
        Construit et charge le modèle DINO depuis un checkpoint mmdet.

        Parameters
        ----------
        cfg_path          : chemin vers dino_starhe.py (config mmdet)
        ckpt_path         : chemin vers le .pth mmdet
        starhe_share_root : racine du dépôt starhe_share contenant `starhe/`
        device            : 'cpu' | 'cuda' | None (auto-détecté)
        """
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # Enregistrer les modules custom avant init_detector
        _ensure_starhe_importable(starhe_share_root)

        model = init_detector(cfg_path, ckpt_path, device=device)

        # Remplacer le loader fichier par un loader en mémoire (array numpy)
        cfg = model.cfg.copy()
        cfg.test_dataloader.dataset.pipeline[0].type = "LoadImageFromNDArray"
        test_pipeline = Compose(cfg.test_dataloader.dataset.pipeline)

        class_names = list(model.dataset_meta.get("classes", ["tumor"]))

        return cls(model, test_pipeline, class_names, device)

    @torch.no_grad()
    def detect(self, frame: np.ndarray, score_thr: float = 0.001) -> list[dict]:
        """
        Détecte les lésions sur un frame RGB.

        Parameters
        ----------
        frame     : (H, W, 3) uint8 RGB
        score_thr : seuil de confiance minimum

        Returns
        -------
        list of dict {"bbox": [x0,y0,x1,y1], "score": float, "label": str}
        Coordonnées xyxy en pixels de l'image originale.
        """
        # MMDetection attend BGR (convention OpenCV)
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        result = inference_detector(
            self._model, bgr, test_pipeline=self._test_pipeline
        )

        pred    = result.pred_instances
        bboxes  = pred.bboxes.cpu().numpy()   # (N, 4) xyxy
        scores  = pred.scores.cpu().numpy()   # (N,)
        labels  = pred.labels.cpu().numpy()   # (N,)

        return [
            {
                "bbox":  [float(x) for x in bb],
                "score": float(sc),
                "label": (
                    self._class_names[int(lb)]
                    if int(lb) < len(self._class_names) else str(lb)
                ),
            }
            for bb, sc, lb in zip(bboxes, scores, labels)
            if sc >= score_thr
        ]
