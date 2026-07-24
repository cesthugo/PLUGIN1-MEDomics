#!/usr/bin/env python3
"""
diag_stage_hashes.py — where exactly do two platforms stop agreeing?
====================================================================
Hashes every intermediate stage of the pipeline so a divergence can be pinned
to one step instead of only being visible in the final result.

Stages
------
  1. dicom_decode   frames straight out of pydicom (+ normalisation)
  2. mp4_bytes      the encoded intermediate file itself
  3. mp4_decoded    frames decoded back from that file  (+ error vs stage 1)
  4. prepus_crop    the array actually handed to the models

Run it on two platforms and diff the output: the first stage whose hash differs
is the culprit. Stage 3 also reports the roundtrip error directly, so a lossy
encoding shows up without needing a second machine.

    python scripts/diag_stage_hashes.py --input <file.dcm>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "pythonCode" / "modules"))


def sha_array(arr: np.ndarray) -> str:
    h = hashlib.sha256()
    h.update(str(arr.shape).encode())
    h.update(str(arr.dtype).encode())
    h.update(np.ascontiguousarray(arr).tobytes())
    return h.hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="A single .dcm file")
    ap.add_argument("--json", help="Optional path to dump the report as JSON")
    ap.add_argument("--dump-crop", help="Optional .npy path to save the prepUS crop "
                                        "(lets two platforms be diffed pixel-wise)")
    args = ap.parse_args()

    import cv2
    from starhe_plugin.dicom.reader import extract_frames, frame_to_uint8
    from starhe_plugin.dicom.prepus_bridge import preprocess_with_prepus_from_video
    import pydicom

    report: dict = {
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "pydicom": pydicom.__version__,
        },
        "input": str(args.input),
        "stages": {},
    }

    # ── 1. DICOM decode ──────────────────────────────────────────────────────
    ds = pydicom.dcmread(args.input)
    fps = float(getattr(ds, "CineRate", 0) or getattr(ds, "RecommendedDisplayFrameRate", 0) or 17)
    raw = extract_frames(ds)
    norm = np.stack([frame_to_uint8(f) for f in raw])
    frames = np.stack([norm] * 3, axis=-1) if norm.ndim == 3 else norm
    report["stages"]["1_dicom_decode"] = {
        "shape": list(frames.shape), "dtype": str(frames.dtype),
        "sha256": sha_array(frames),
        "mean": float(frames.mean()), "std": float(frames.std()),
    }

    with tempfile.TemporaryDirectory() as td:
        mp4 = Path(td) / "intermediate.mp4"

        # ── 2. Encode ────────────────────────────────────────────────────────
        from starhe_pipeline_cli import H264_LOSSLESS  # same recipe as the pipeline
        T, H, W, _ = frames.shape
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", f"{fps:.6f}",
               "-i", "pipe:0"] + H264_LOSSLESS + [str(mp4)]
        p = subprocess.run(cmd, input=np.ascontiguousarray(frames).tobytes(),
                           capture_output=True)
        if p.returncode != 0:
            print(p.stderr.decode()[-2000:], file=sys.stderr)
            return 2
        report["stages"]["2_mp4_bytes"] = {
            "encoder": " ".join(H264_LOSSLESS),
            "size_bytes": mp4.stat().st_size,
            "sha256": sha_file(mp4),
        }

        # ── 3. Decode back ───────────────────────────────────────────────────
        cap = cv2.VideoCapture(str(mp4))
        back = []
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            back.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        cap.release()
        back_arr = np.asarray(back, dtype=np.uint8)
        same_shape = back_arr.shape == frames.shape
        diff = (np.abs(back_arr.astype(np.int16) - frames.astype(np.int16))
                if same_shape else None)
        report["stages"]["3_mp4_decoded"] = {
            "shape": list(back_arr.shape), "sha256": sha_array(back_arr),
            "roundtrip_exact": bool(same_shape and diff.max() == 0),
            "roundtrip_max_err": int(diff.max()) if same_shape else None,
            "roundtrip_mean_err": float(diff.mean()) if same_shape else None,
        }

        # ── 4. prepUS crop ───────────────────────────────────────────────────
        crop, info = preprocess_with_prepus_from_video(str(mp4))
        crop = np.asarray(crop)
        report["stages"]["4_prepus_crop"] = {
            "shape": list(crop.shape), "dtype": str(crop.dtype),
            "sha256": sha_array(crop),
            "mean": float(crop.mean()), "std": float(crop.std()),
            "info": info if isinstance(info, dict) else None,
            # Marginal profiles: a crop taken at a different offset shows up as a
            # shifted profile, which a scalar mean cannot distinguish from noise.
            "frame0_row_mean_head": [round(float(v), 4)
                                     for v in crop[0].mean(axis=1)[:12]],
            "frame0_col_mean_head": [round(float(v), 4)
                                     for v in crop[0].mean(axis=0)[:12]],
            "per_frame_mean_head": [round(float(v), 6)
                                    for v in crop.reshape(len(crop), -1).mean(axis=1)[:8]],
        }
        if args.dump_crop:
            np.save(args.dump_crop, crop)

    print(json.dumps(report, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
