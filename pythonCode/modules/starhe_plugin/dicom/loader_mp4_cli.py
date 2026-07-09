"""
dicom/loader_mp4_cli.py — CLI to load an MP4 file and return the frames as base64 JPEG
=================================================================================================
Called by the Go server to feed the React frontend (same format as loader_cli.py).

Usage:
    python -m starhe_plugin.dicom.loader_mp4_cli <mp4_path> [--quality 70] [--max-dim 640]

stdout output: single JSON with all frames encoded as base64 JPEG.
Output format identical to loader_cli.py:
{
  "file_name":          "video.mp4",
  "frame_count":        100,
  "rows":               480,
  "cols":               640,
  "modality":           "MP4",
  "pixel_spacing":      null,
  "base_fps":           25.0,
  "original_sensitive": [],
  "kept_metadata":      [["FPS", "25.00"], ["Frames", "100"], ["Durée", "4.00 s"]],
  "patient_name":       "MP4 Video",
  "study_date":         "",
  "frames_b64":         ["<jpeg-base64>", ...]
}
"""

from __future__ import annotations

import sys
import os
import json
import base64
import argparse
import traceback
from io import BytesIO

_MODULES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)


def load_mp4_and_encode(
    mp4_path: str,
    quality: int = 70,
    max_dim: int = 640,
) -> dict:
    """Loads an MP4 file, extracts the frames, encodes as base64 JPEG."""
    import cv2
    import numpy as np
    from PIL import Image

    cap = cv2.VideoCapture(mp4_path)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir le fichier MP4 : {mp4_path}")

    raw_fps     = cap.get(cv2.CAP_PROP_FPS)
    fps         = raw_fps if raw_fps > 0 else 22.0
    n_total     = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    h_orig      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w_orig      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    frames_b64: list[str] = []
    rows = h_orig
    cols = w_orig

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        # BGR → RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)

        # Downscale if needed
        if max(img.width, img.height) > max_dim:
            scale = max_dim / max(img.width, img.height)
            new_w = max(1, int(img.width  * scale))
            new_h = max(1, int(img.height * scale))
            img = img.resize((new_w, new_h), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        frames_b64.append(base64.b64encode(buf.getvalue()).decode("ascii"))

    cap.release()

    if not frames_b64:
        raise RuntimeError("Le fichier MP4 ne contient aucune frame lisible.")

    duration_s = len(frames_b64) / fps if fps > 0 else 0.0
    kept_metadata = [
        ["FPS",      f"{fps:.2f}"],
        ["Frames",   str(len(frames_b64))],
        ["Durée",    f"{duration_s:.2f} s"],
        ["Résolution", f"{w_orig}×{h_orig}"],
    ]

    return {
        "file_name":          os.path.basename(mp4_path),
        "frame_count":        len(frames_b64),
        "rows":               rows,
        "cols":               cols,
        "modality":           "MP4",
        "pixel_spacing":      None,
        "base_fps":           fps,
        "original_sensitive": [],
        "kept_metadata":      kept_metadata,
        "patient_name":       "MP4 Video",
        "study_date":         "",
        "frames_b64":         frames_b64,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m starhe_plugin.dicom.loader_mp4_cli",
        description="Loads an MP4 file and returns the frames as base64 JPEG (stdout JSON).",
    )
    parser.add_argument("mp4_path",             help="Path to the MP4 file")
    parser.add_argument("--quality",  type=int, default=70,  help="JPEG quality (1-95, default: 70)")
    parser.add_argument("--max-dim",  type=int, default=640, help="Max dimension (default: 640)")
    args = parser.parse_args()

    try:
        result = load_mp4_and_encode(args.mp4_path, args.quality, args.max_dim)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        err = {
            "error":     str(exc),
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(err, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
