"""
ai/models/_c3d_runner.py — mmaction2 C3D subprocess (server mode)
=================================================================
Runs mmaction2's C3D backbone and I3DHead head directly
(without going through the mmengine registry, incompatible with mmdet
under Python 3.13). Loads the checkpoint identically to init_recognizer.

Usage (launched as a subprocess by starhe_risk.py):
    python _c3d_runner.py \\
        --ckpt  <path/best_xxx.pth>  \\
        [--device cpu]               \\
        [--deterministic]

stdin/stdout protocol (JSON, one line per message):
  Startup  : [c3d_server] READY
  Request  : {"frames_b64": "<numpy uint8 T×H×W×3 in base64>", "shape": [T,H,W,3]}
  Response : {"score_low": 0.35, "score_high": 0.65}
  Shutdown : {"__EXIT__": true}
"""

import argparse
import base64
import json
import sys

import cv2
import numpy as np
import torch
import torch.nn.functional as F


# ── Preprocessing constants (identical to c3d.py + mmaction2 pipeline) ───────
CLIP_LEN    = 16
NUM_CLIPS   = 10
RESIZE_SIZE = 128
CROP_SIZE   = 112
_MEAN       = np.array([104.0, 117.0, 128.0], dtype=np.float32)


# ── Preprocessing — exact copy of c3d.py (validated bit-identical to mmaction2) ─

def _sample_clips(total: int) -> np.ndarray:
    """Reproduces exactly mmaction2 SampleFrames 3D (clip_len=16, num_clips=10, test_mode=True).

    Actual formula of mmaction2 1.2.0 _get_test_clips (3D recognizer):
      max_offset    = max(total - clip_len, 0)
      offset_between = max_offset / (num_clips - 1)
      clip_offsets  = round(arange(num_clips) * offset_between)
    Out-of-bound indices are wrapped by modulo (out_of_bound_opt='loop').
    """
    if total <= 0:
        return np.zeros((NUM_CLIPS, CLIP_LEN), dtype=int)
    max_offset = max(total - CLIP_LEN, 0)
    if NUM_CLIPS > 1:
        offset_between = max_offset / float(NUM_CLIPS - 1)
        offsets = np.round(np.arange(NUM_CLIPS) * offset_between).astype(int)
    else:
        offsets = np.array([max_offset // 2], dtype=int)
    return np.stack([np.arange(o, o + CLIP_LEN) % total for o in offsets])


def _resize_shortest(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    if h <= w:
        nh, nw = RESIZE_SIZE, max(1, round(w * RESIZE_SIZE / h))
    else:
        nh, nw = max(1, round(h * RESIZE_SIZE / w)), RESIZE_SIZE
    return cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)


def _preprocess(frames: np.ndarray) -> torch.Tensor:
    """(T, H, W, 3) uint8 RGB → (NUM_CLIPS, 3, CLIP_LEN, CROP_SIZE, CROP_SIZE) float32"""
    T = len(frames)
    clip_idx = _sample_clips(T)
    cache: dict[int, np.ndarray] = {}

    def _get(idx: int) -> np.ndarray:
        if idx not in cache:
            cache[idx] = _resize_shortest(frames[idx])
        return cache[idx]

    result = []
    for ci in clip_idx:
        clip = []
        for idx in ci:
            f = _get(int(idx))
            h, w = f.shape[:2]
            y = (h - CROP_SIZE) // 2
            x = (w - CROP_SIZE) // 2
            clip.append(f[y:y + CROP_SIZE, x:x + CROP_SIZE, :])
        arr = np.stack(clip).astype(np.float32) - _MEAN   # (16, 112, 112, 3)
        result.append(arr.transpose(3, 0, 1, 2))           # (3, 16, 112, 112)
    return torch.from_numpy(np.stack(result))              # (10, 3, 16, 112, 112)


# ── mmaction2 loading (direct import, without the mmengine registry) ──────────

def _load_model(ckpt_path: str, device: str):
    """
    Loads mmaction2's C3D backbone + I3DHead head directly from
    their Python modules, without going through init_recognizer / MODELS.build.
    Avoids the mmengine ↔ mmdet registry conflict under Python 3.13.
    """
    from mmaction.models.backbones.c3d import C3D
    from mmaction.models.heads.i3d_head import I3DHead

    backbone = C3D(dropout_ratio=0.5)
    cls_head = I3DHead(num_classes=2, in_channels=4096, dropout_ratio=0.5)

    ckpt  = torch.load(ckpt_path, map_location='cpu', weights_only=False)
    state = ckpt.get('state_dict', ckpt)

    backbone.load_state_dict(
        {k[len('backbone.'):]: v for k, v in state.items() if k.startswith('backbone.')}
    )
    cls_head.load_state_dict(
        {k[len('cls_head.'):]: v for k, v in state.items() if k.startswith('cls_head.')}
    )

    backbone.to(device).eval()
    cls_head.to(device).eval()
    return backbone, cls_head


# ── Inference ─────────────────────────────────────────────────────────────────

@torch.no_grad()
def _infer(backbone, cls_head, frames: np.ndarray, device: str) -> tuple[float, float]:
    tensor = _preprocess(frames).to(device)               # (10, 3, 16, 112, 112)
    feats  = backbone(tensor)                              # (10, 4096)
    logits = cls_head.fc_cls(cls_head.dropout(feats))     # (10, 2)
    probs  = F.softmax(logits, dim=1).mean(0)             # (2,)
    return float(probs[0].item()), float(probs[1].item())


# ── Server mode ───────────────────────────────────────────────────────────────

def _run_server(backbone, cls_head, device: str) -> None:
    print("[c3d_server] READY", flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        if req.get("__EXIT__"):
            break
        shape  = req["shape"]                                   # [T, H, W, 3]
        frames = np.frombuffer(
            base64.b64decode(req["frames_b64"]), dtype=np.uint8
        ).reshape(shape)
        score_low, score_high = _infer(backbone, cls_head, frames, device)
        print(json.dumps({"score_low": score_low, "score_high": score_high}), flush=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt",          required=True, help="Path to best_xxx.pth")
    parser.add_argument("--device",        default="cpu",   help="cpu | cuda | mps")
    parser.add_argument("--deterministic", action="store_true",
                        help="Force single-threaded CPU + disable TF32 (reproducibility)")
    args = parser.parse_args()

    device = args.device
    if args.deterministic:
        device = "cpu"
        torch.set_num_threads(1)

    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32      = False
        torch.backends.cudnn.deterministic   = True
        torch.backends.cudnn.benchmark       = False

    torch.use_deterministic_algorithms(True, warn_only=True)

    backbone, cls_head = _load_model(args.ckpt, device)
    _run_server(backbone, cls_head, device)


if __name__ == "__main__":
    main()
