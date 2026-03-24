"""ai/models/rtmdet.py — Inférence RTMDet sans mmcv C-extension
=============================================================
Stratégie :
  1. Stub mmcv._ext (module C absent) *avant* tout import mmdet
  2. Patch NMSop.forward  →  torchvision.ops.nms (CPU/GPU, pas de C-ext)
  3. Charge RTMDet via mmdet.models (code Python pur après stub)
  4. Inférence : backbone → neck → head.predict_by_feat

Pipeline de prétraitement (identique à l'entraînement STARHE) :
  Resize(640×640, keep_ratio=True)  →  Pad(640×640, val=114)
  Normalise : mean=[103.53, 116.28, 123.675]  std=[57.375, 57.12, 58.395]
  Format : float32, channels-first (3, 640, 640) — pas de swap BGR/RGB
"""

import sys
import types
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
# En Python 3.13, inspect.getmodule(sys._getframe(2)) lève AttributeError lors
# de l'initialisation des registres mmengine/mmdet (bug Python 3.13).
# On patche pour extraire le module depuis f_globals du frame, ce qui préserve
# l'inférence de scope (ex. 'mmdet.registry' → scope 'mmdet').
import inspect as _inspect
import types as _types

_orig_inspect_getmodule = _inspect.getmodule


def _safe_getmodule(obj, _filename=None):
    try:
        return _orig_inspect_getmodule(obj, _filename)
    except (AttributeError, TypeError, OSError):
        # Fallback pour les frame-objects : extraire le module depuis f_globals
        if isinstance(obj, _types.FrameType):
            mod_name = obj.f_globals.get('__name__')
            if mod_name:
                import sys as _sys
                return _sys.modules.get(mod_name)
        return None


_inspect.getmodule = _safe_getmodule

# ─── 4. Patch NMSop.forward avec torchvision.ops.nms ────────────────────────
# `import mmcv.ops.nms as x` donne la *fonction* nms (nom écrasé dans
# mmcv/ops/__init__.py par `from .nms import nms`).
# On importe NMSop directement depuis le module pour éviter l'ambiguïté.
import mmcv.ops.nms           # noqa: E402  — enregistre le module dans sys.modules
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
from mmengine.config import Config                   # noqa: E402
from mmengine.registry import DefaultScope           # noqa: E402
import mmdet.models                                  # noqa: E402  — enregistre les modèles
from mmdet.registry import MODELS                    # noqa: E402  — registre des modèles mmdet


def _load_checkpoint(model: torch.nn.Module, ckpt_path: str, device: str) -> None:
    """
    Charge un checkpoint mmengine avec torch.load(weights_only=False).
    PyTorch ≥ 2.6 change le défaut weights_only=True ce qui bloque les
    checkpoints contenant des objets non-tenseurs (ex. HistoryBuffer).
    """
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    state_dict = ckpt.get("state_dict", ckpt)
    # Supprime les clés data_preprocessor (normalisees à la main)
    state_dict = {k: v for k, v in state_dict.items()
                  if not k.startswith("data_preprocessor.")}
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    if unexpected:
        print(f"  [rtmdet] clés inattendues ignorées : {len(unexpected)}")
    if missing:
        print(f"  [rtmdet] clés manquantes : {missing[:5]}{'…' if len(missing)>5 else ''}")

# ─── Constantes de prétraitement ─────────────────────────────────────────────
_INPUT_SIZE = 640
_PAD_VAL    = 114.0
_MEAN = torch.tensor([103.53, 116.28, 123.675]).view(3, 1, 1)
_STD  = torch.tensor([ 57.375,  57.12,  58.395]).view(3, 1, 1)


# ─── Utilitaires ─────────────────────────────────────────────────────────────
def _replace_syncbn(d):
    """Remplace récursivement SyncBN → BN pour l'inférence mono-processus."""
    if isinstance(d, dict):
        if d.get("type") == "SyncBN":
            d["type"] = "BN"
        for v in d.values():
            _replace_syncbn(v)
    elif isinstance(d, (list, tuple)):
        for item in d:
            _replace_syncbn(item)


def preprocess_frame(frame: np.ndarray):
    """
    Prépare un frame brut pour RTMDet (640×640, normalisé).

    Parameters
    ----------
    frame : np.ndarray  shape (H, W, 3) uint8

    Returns
    -------
    tensor : torch.Tensor  shape (1, 3, 640, 640)  float32 normalisé
    meta   : dict  {img_shape, ori_shape, scale_factor, pad_shape,
                    batch_input_shape}
    """
    orig_H, orig_W = frame.shape[:2]
    scale = min(_INPUT_SIZE / orig_H, _INPUT_SIZE / orig_W)
    new_H = int(round(orig_H * scale))
    new_W = int(round(orig_W * scale))

    resized = cv2.resize(frame, (new_W, new_H), interpolation=cv2.INTER_LINEAR)

    canvas = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), _PAD_VAL, dtype=np.float32)
    canvas[:new_H, :new_W] = resized.astype(np.float32)

    tensor = torch.from_numpy(canvas.transpose(2, 0, 1))   # (3, 640, 640)
    tensor = (tensor - _MEAN) / _STD
    tensor = tensor.unsqueeze(0)                            # (1, 3, 640, 640)

    meta = {
        "img_shape":         (_INPUT_SIZE, _INPUT_SIZE),
        "ori_shape":         (orig_H, orig_W),
        "scale_factor":      (float(new_W / orig_W), float(new_H / orig_H)),
        "pad_shape":         (_INPUT_SIZE, _INPUT_SIZE),
        "batch_input_shape": (_INPUT_SIZE, _INPUT_SIZE),
    }
    return tensor, meta


# ─── Classe principale ────────────────────────────────────────────────────────
class RTMDetInference:
    """
    Chargement et inférence RTMDet (pur PyTorch + mmdet Python).

    Usage
    -----
    detector = RTMDetInference.from_checkpoint(cfg_path, ckpt_path)
    dets      = detector.detect(frame)   # frame : (H, W, 3) uint8
    """

    def __init__(self, model: torch.nn.Module, device: str):
        self._model  = model
        self._device = device

    @classmethod
    def from_checkpoint(
        cls,
        cfg_path:  str,
        ckpt_path: str,
        device:    str | None = None,
    ) -> "RTMDetInference":
        """
        Construit et charge le modèle RTMDet depuis un checkpoint mmdet.

        Parameters
        ----------
        cfg_path  : chemin vers rtmdet_starhe.py (config mmdet aplatie)
        ckpt_path : chemin vers le .pth mmdet
        device    : 'cpu' | 'cuda' | None  (auto-détecté)
        """
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        cfg = Config.fromfile(cfg_path)
        _replace_syncbn(cfg._cfg_dict)

        # DefaultScope('mmdet') garantit que les sous-modules mmdet
        # (ex. DetDataPreprocessor) sont trouvés dans le bon registre.
        with DefaultScope.overwrite_default_scope('mmdet'):
            model = MODELS.build(cfg.model)
            _load_checkpoint(model, ckpt_path, device)
        model.to(device).eval()

        return cls(model, device)

    @torch.no_grad()
    def detect(self, frame: np.ndarray, score_thr: float = 0.001) -> list:
        """
        Détecte les lésions sur un frame.

        Parameters
        ----------
        frame     : (H, W, 3) uint8  (RGB ou grayscale-as-RGB)
        score_thr : seuil de confiance minimum (pré-filtre bas, le filtre
                    principal est dans STARHEDetectModel.predict)

        Returns
        -------
        list of dict {"bbox": [x0,y0,x1,y1], "score": float, "label": int}
        """
        tensor, meta = preprocess_frame(frame)
        tensor = tensor.to(self._device)

        # Forward : backbone → neck → head
        feats      = self._model.backbone(tensor)
        neck_feats = self._model.neck(feats)
        head_outs  = self._model.bbox_head(neck_feats)   # (cls_scores, bbox_preds)

        # Décodage : ancres + distances → boîtes rescalées vers l'image originale
        results = self._model.bbox_head.predict_by_feat(
            *head_outs,
            batch_img_metas=[meta],
            rescale=True,
        )

        instances = results[0]
        bboxes = instances.bboxes.cpu().numpy()   # (N, 4) xyxy
        scores = instances.scores.cpu().numpy()   # (N,)
        labels = instances.labels.cpu().numpy()   # (N,)

        return [
            {
                "bbox":  [float(x) for x in bb],
                "score": float(sc),
                "label": int(lb),
            }
            for bb, sc, lb in zip(bboxes, scores, labels)
            if sc >= score_thr
        ]
