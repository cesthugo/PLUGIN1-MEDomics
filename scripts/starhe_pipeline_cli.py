#!/usr/bin/env python3
"""
starhe_pipeline_cli.py — Containerised STARHE pipeline (DICOM → results)
=======================================================================
Deterministic, batch-capable command-line entry point used as the Docker
image's ENTRYPOINT. Runs the full processing + inference chain:

    DICOM  →  decode (pydicom)
           →  encode intermediate MP4  (H.264 CRF 0, RGB = bit-exact)
           →  prepUS  (UI removal + US-cone crop)
           →  STARHE-RISK (C3D)  +  STARHE-DETECT (RTMDet)
           →  results.json / results.csv

Why this is reproducible
------------------------
* The container pins every binary (ffmpeg, OpenCV, BLAS, Python, torch), so
  even codec output is identical on every host.
* The intermediate MP4 uses **libx264rgb at CRF 0** → no colour conversion, so
  the frames prepUS decodes are the encoded array byte-for-byte (verified by
  scripts/test_encoding_roundtrip.py).
* Inference runs on CPU / float64 / single thread (STARHE_DETERMINISTIC=1).
* A SHA-256 of every crop is reported so runs can be compared byte-for-byte
  ("golden hash").

Model weights are NOT bundled in the image: pass --weights pointing at a
mounted directory that holds the .pth files.

Usage
-----
    starhe-pipeline --input /data/in --output /data/out --weights /weights
    starhe-pipeline --input /data/in/case.dcm --output /data/out --no-detect
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

# The plugin package lives next to this script in the image (/app/pythonCode/modules)
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "pythonCode" / "modules"))

# ── Intermediate encoding: H.264 CRF 0, RGB (truly lossless) ─────────────────
# CRF 0 is lossless for the pixel format the encoder receives — it does NOT
# undo a colour conversion applied before it. Feeding RGB frames with
# -pix_fmt yuv420p inserts an RGB → YUV 4:2:0 step (chroma subsampling + matrix
# rounding) whose result depends on the swscale build, so two hosts decode
# slightly different pixels. Measured on a synthetic clip
# (scripts/test_encoding_roundtrip.py):
#     libx264    crf 0 yuv420p → max error 2, mean 1.71   (not exact)
#     libx264    crf 0 yuv444p → max error 1, mean 0.13   (not exact)
#     libx264rgb crf 0 rgb24   → max error 0, mean 0.00   (bit-exact)
# libx264rgb encodes RGB directly, so the decoded frames are the input array
# byte-for-byte and cannot depend on which ffmpeg built the file. Files are
# ~3x larger, which is irrelevant for a temporary intermediate.
H264_LOSSLESS = ["-c:v", "libx264rgb", "-crf", "0", "-preset", "medium",
                 "-pix_fmt", "rgb24"]


def _log(msg: str) -> None:
    print(f"[starhe] {msg}", flush=True)


def dicom_fps(ds) -> float:
    """FPS from DICOM tags, same priority as pipeline.py."""
    rdp = float(getattr(ds, "RecommendedDisplayFrameRate", 0) or 0)
    if rdp > 0:
        return rdp
    cr = float(getattr(ds, "CineRate", 0) or 0)
    if cr > 0:
        return cr
    ft = float(getattr(ds, "FrameTime", 0) or 0)
    if ft > 0:
        return 1000.0 / ft
    return 25.0


def decode_dicom(path: str):
    """DICOM → (frames_rgb uint8 (T,H,W,3), fps).

    Uses Weasis when explicitly enabled AND available (needs a JVM); inside the
    container STARHE_USE_WEASIS=0, so this is the pure-Python pydicom path.
    """
    from starhe_plugin.config import USE_WEASIS_EXPORT
    from starhe_plugin.dicom.reader import load_dicom, extract_frames, frame_to_uint8

    ds = load_dicom(path)
    fps = dicom_fps(ds)

    if USE_WEASIS_EXPORT:
        try:
            from starhe_plugin.dicom.weasis_bridge import weasis_available, frames_via_weasis
            if weasis_available():
                frames, wfps = frames_via_weasis(path)
                return frames, (wfps if wfps > 0 else fps)
        except Exception as exc:  # pragma: no cover - container has no JVM
            _log(f"weasis unavailable ({exc}) → pydicom")

    raw = extract_frames(ds)
    norm = np.stack([frame_to_uint8(f) for f in raw])
    frames = np.stack([norm] * 3, axis=-1) if norm.ndim == 3 else norm
    return frames, fps


def encode_lossless_mp4(frames: np.ndarray, fps: float, out_mp4: str) -> None:
    """(T,H,W,3) uint8 RGB → H.264 CRF 0 MP4, piped straight into ffmpeg."""
    T, H, W, _ = frames.shape
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", f"{fps:.6f}", "-i", "pipe:0"] + H264_LOSSLESS + [out_mp4]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in frames:
            proc.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.read().decode()[-400:]}")


def sha256_array(arr: np.ndarray) -> str:
    """Stable content hash of an array (golden-hash reproducibility check)."""
    h = hashlib.sha256()
    h.update(str(arr.shape).encode())
    h.update(str(arr.dtype).encode())
    h.update(np.ascontiguousarray(arr).tobytes())
    return h.hexdigest()


def process_one(dcm: Path, workdir: Path, risk_model, detect_model,
                detect_every_n: int, detect_thr: float) -> dict:
    """Full chain for a single DICOM. Returns a result dict."""
    from starhe_plugin.dicom.prepus_bridge import preprocess_with_prepus_from_video

    t0 = time.time()
    out: dict = {"file": dcm.name}

    frames, fps = decode_dicom(str(dcm))
    out["num_frames_source"] = int(frames.shape[0])
    out["fps"] = round(fps, 3)

    # Step 1 — lossless intermediate MP4 (this is what prepUS consumes)
    mp4 = workdir / f"{dcm.stem}.mp4"
    encode_lossless_mp4(frames, fps, str(mp4))

    # Step 2 — prepUS: UI removal + US-cone crop, read straight from the MP4
    crop, info = preprocess_with_prepus_from_video(str(mp4))
    mp4.unlink(missing_ok=True)
    out["crop_shape"] = list(crop.shape)
    out["crop_sha256"] = sha256_array(crop)
    out["prepus_fallback"] = bool(info and info.get("fallback") == "crop.py")
    if info and "crop" in info:
        c = info["crop"]
        out["roi"] = [int(c["xmin"]), int(c["ymin"]), int(c["xmax"]), int(c["ymax"])]

    # Model input: grayscale crop replicated to pseudo-RGB (as in pipeline.py)
    frames_model = np.stack([crop, crop, crop], axis=-1)

    # Step 3 — STARHE-RISK
    if risk_model is not None:
        r = risk_model.predict(frames_model)
        out["risk"] = {"score": r["risk_score"], "label": r["risk_label"]}

    # Step 4 — STARHE-DETECT (temporal subsampling + propagation, as pipeline.py)
    if detect_model is not None:
        n = len(frames_model)
        dets: list[list] = [[] for _ in range(n)]
        sampled = list(range(0, n, max(1, detect_every_n)))
        bs = max(1, detect_model.batch_size)
        for i in range(0, len(sampled), bs):
            idx = sampled[i:i + bs]
            batch = detect_model.predict_batch([frames_model[j] for j in idx],
                                               score_thr=detect_thr)
            for j, frame_dets in zip(idx, batch):
                for k in range(j, min(j + detect_every_n, n)):
                    dets[k] = frame_dets
        # Remap boxes from crop space back to source-image space
        from starhe_plugin.dicom.prepus_bridge import map_detections_to_dicom_coords
        dets = map_detections_to_dicom_coords(dets, info)
        out["detections_per_frame"] = dets
        out["frames_with_detection"] = sum(1 for d in dets if d)

    out["elapsed_s"] = round(time.time() - t0, 2)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="starhe-pipeline",
        description="Deterministic STARHE pipeline: DICOM → prepUS → RISK/DETECT.")
    ap.add_argument("--input", "-i", required=True,
                    help="DICOM file, or directory containing DICOM files")
    ap.add_argument("--output", "-o", required=True, help="Output directory")
    ap.add_argument("--weights", "-w", default=None,
                    help="Directory holding the .pth weights (sets STARHE_WEIGHTS_DIR)")
    ap.add_argument("--no-risk", action="store_true", help="Skip STARHE-RISK")
    ap.add_argument("--no-detect", action="store_true", help="Skip STARHE-DETECT")
    ap.add_argument("--pattern", default="*", help="Glob for directory input (default: all files)")
    args = ap.parse_args()

    if args.weights:
        os.environ["STARHE_WEIGHTS_DIR"] = str(Path(args.weights).resolve())

    # Imported after STARHE_WEIGHTS_DIR is set (config resolves paths at import)
    from starhe_plugin.config import (DETERMINISTIC_INFERENCE, DETECT_EVERY_N,
                                      DETECT_SCORE_THRESHOLD, C3D_BACKEND,
                                      USE_WEASIS_EXPORT, WEIGHTS_DIR)

    in_path = Path(args.input)
    dicoms = ([in_path] if in_path.is_file()
              else sorted(p for p in in_path.glob(args.pattern) if p.is_file()))
    if not dicoms:
        _log(f"no input file found in {in_path}")
        return 2

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    _log(f"files={len(dicoms)}  weights={WEIGHTS_DIR}  deterministic={DETERMINISTIC_INFERENCE}")
    _log(f"c3d_backend={C3D_BACKEND}  weasis={USE_WEASIS_EXPORT}  "
         f"detect_thr={DETECT_SCORE_THRESHOLD}  detect_every_n={DETECT_EVERY_N}")
    _log("intermediate encoding: H.264 CRF 0 RGB (libx264rgb, bit-exact)")

    # Models are loaded ONCE and reused for the whole batch (the expensive part)
    risk_model = detect_model = None
    try:
        if not args.no_risk:
            from starhe_plugin.ai.starhe_risk import STARHERiskModel
            risk_model = STARHERiskModel()
        if not args.no_detect:
            from starhe_plugin.ai.starhe_detect import STARHEDetectModel
            detect_model = STARHEDetectModel()

        results = []
        with tempfile.TemporaryDirectory(prefix="starhe_work_") as tmp:
            for i, dcm in enumerate(dicoms, 1):
                _log(f"[{i}/{len(dicoms)}] {dcm.name}")
                try:
                    res = process_one(dcm, Path(tmp), risk_model, detect_model,
                                      DETECT_EVERY_N, DETECT_SCORE_THRESHOLD)
                except Exception as exc:
                    res = {"file": dcm.name, "error": f"{type(exc).__name__}: {exc}"}
                    _log(f"    ERROR {res['error']}")
                results.append(res)
                if "risk" in res:
                    _log(f"    risk={res['risk']['score']:.4f}  "
                         f"detections={res.get('frames_with_detection', '-')}  "
                         f"crop_sha256={res.get('crop_sha256', '')[:12]}")
    finally:
        for m in (risk_model, detect_model):
            if m is not None:
                try:
                    m.close()
                except Exception:
                    pass

    # ── Outputs ──────────────────────────────────────────────────────────────
    (out_dir / "results.json").write_text(
        json.dumps({"pipeline": "starhe-docker/1.0",
                    "encoding": "h264_crf0_lossless",
                    "deterministic": bool(DETERMINISTIC_INFERENCE),
                    "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8")

    with open(out_dir / "results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["file", "risk_score", "risk_label", "frames_with_detection",
                    "crop_shape", "crop_sha256", "prepus_fallback", "error"])
        for r in results:
            w.writerow([r.get("file", ""),
                        r.get("risk", {}).get("score", ""),
                        r.get("risk", {}).get("label", ""),
                        r.get("frames_with_detection", ""),
                        "x".join(map(str, r.get("crop_shape", []))),
                        r.get("crop_sha256", ""),
                        r.get("prepus_fallback", ""),
                        r.get("error", "")])

    ok = sum(1 for r in results if "error" not in r)
    _log(f"done: {ok}/{len(results)} processed → {out_dir}/results.json | results.csv")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
