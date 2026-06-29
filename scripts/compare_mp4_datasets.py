#!/usr/bin/env python3
"""
compare_mp4_datasets.py — Compare two folders of MP4 files frame-by-frame.

For each matched pair, reports:
  • Container metadata  : duration, fps, resolution, codec, pixel format, bitrate
  • Frame count         : from container metadata + optional -count_frames
  • File size + MD5     : bit-exact identity check
  • Delta columns       : Δduration, Δfps, Δwidth, Δheight, Δsize
  • Match flags         : dim_match, fps_match, dur_match (Δ < 0.1 s), md5_identical
  • Pixel-level stats   : mean/std per channel R, G, B for each file (sampled frames)
  • Pixel comparison    : MAE overall, PSNR, MAE_R, MAE_G, MAE_B (sampled frames)

Usage:
    python scripts/compare_mp4_datasets.py \\
        --dir_a '/path/to/datasetAVANTPREPROCESS' \\
        --dir_b '/path/to/datasetMP4' \\
        --output comparison_mp4.csv \\
        --n_frames 20
"""

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import cv2


# ─────────────────────────────────────────────────────────────────────────────
# ffprobe helpers
# ─────────────────────────────────────────────────────────────────────────────

def ffprobe_meta(path: Path) -> dict:
    """Return container + first video stream metadata via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(path),
    ]
    try:
        raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        data = json.loads(raw)
    except Exception as e:
        return {"error": str(e)}

    result = {}
    fmt = data.get("format", {})
    result["duration_s"]    = round(float(fmt.get("duration") or 0), 6)
    result["size_bytes"]    = int(fmt.get("size") or 0)
    result["bitrate_kbps"]  = round(float(fmt.get("bit_rate") or 0) / 1000, 1)
    result["format_name"]   = fmt.get("format_name", "")

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            result["width"]   = stream.get("width", 0)
            result["height"]  = stream.get("height", 0)
            result["codec"]   = stream.get("codec_name", "")
            result["pix_fmt"] = stream.get("pix_fmt", "")

            r = stream.get("r_frame_rate", "0/1")
            try:
                n, d = map(int, r.split("/"))
                result["fps"] = round(n / d, 6) if d else 0.0
            except Exception:
                result["fps"] = 0.0

            result["nb_frames_meta"] = int(stream.get("nb_frames") or 0)
            break

    return result


def count_frames_exact(path: Path) -> int:
    """Count frames by actually reading them (slow, accurate)."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "v:0",
        "-count_frames",
        "-show_entries", "stream=nb_read_frames",
        "-print_format", "json",
        str(path),
    ]
    try:
        raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        streams = json.loads(raw).get("streams", [])
        return int(streams[0].get("nb_read_frames") or 0) if streams else 0
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# MD5
# ─────────────────────────────────────────────────────────────────────────────

def md5_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Frame sampling + pixel statistics
# ─────────────────────────────────────────────────────────────────────────────

def sample_frames(path: Path, n: int) -> list[np.ndarray]:
    """
    Return n evenly-spaced BGR frames from the video.
    Falls back to sequential read if total frame count is unavailable.
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total <= 0:
        # Sequential read, then subsample
        all_frames: list[np.ndarray] = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            all_frames.append(frame)
        cap.release()
        total = len(all_frames)
        if total == 0:
            return []
        idxs = np.linspace(0, total - 1, min(n, total), dtype=int)
        return [all_frames[i] for i in idxs]

    idxs = np.linspace(0, total - 1, min(n, total), dtype=int)
    frames: list[np.ndarray] = []
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()
    return frames


def pixel_stats_bgr(frames: list[np.ndarray]) -> dict[str, dict]:
    """
    Return per-channel mean and std (BGR order → reported as B, G, R).
    Values computed in 0-255 range over all sampled frames.
    """
    empty = {ch: {"mean": None, "std": None} for ch in ("B", "G", "R")}
    if not frames:
        return empty

    arr = np.concatenate(
        [f.reshape(-1, 3).astype(np.float32) for f in frames], axis=0
    )
    result = {}
    for i, ch in enumerate(("B", "G", "R")):
        result[ch] = {
            "mean": round(float(arr[:, i].mean()), 3),
            "std":  round(float(arr[:, i].std()),  3),
        }
    return result


def compare_frame_pairs(
    frames_a: list[np.ndarray],
    frames_b: list[np.ndarray],
) -> dict:
    """
    Pixel-level comparison between two frame lists (same positions).
    Frames at different resolutions are resized to match A.
    Returns: mae_overall, psnr_dB, mae_B, mae_G, mae_R.
    """
    n = min(len(frames_a), len(frames_b))
    empty = {"mae_overall": None, "psnr_dB": None,
             "mae_B": None, "mae_G": None, "mae_R": None}
    if n == 0:
        return empty

    maes: list[float] = []
    psnrs: list[float] = []
    ch_maes: dict[str, list[float]] = {"B": [], "G": [], "R": []}

    for fa, fb in zip(frames_a[:n], frames_b[:n]):
        if fa.shape != fb.shape:
            fb = cv2.resize(fb, (fa.shape[1], fa.shape[0]),
                            interpolation=cv2.INTER_LINEAR)

        diff = np.abs(fa.astype(np.float32) - fb.astype(np.float32))
        maes.append(float(diff.mean()))

        for i, ch in enumerate(("B", "G", "R")):
            ch_maes[ch].append(float(diff[:, :, i].mean()))

        mse = float((diff ** 2).mean())
        if mse > 0:
            psnrs.append(20.0 * math.log10(255.0 / math.sqrt(mse)))

    return {
        "mae_overall": round(float(np.mean(maes)), 4),
        "psnr_dB":     round(float(np.mean(psnrs)), 2) if psnrs else None,
        "mae_B":       round(float(np.mean(ch_maes["B"])), 4),
        "mae_G":       round(float(np.mean(ch_maes["G"])), 4),
        "mae_R":       round(float(np.mean(ch_maes["R"])), 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# File matching
# ─────────────────────────────────────────────────────────────────────────────

def build_pairs(
    dir_a: Path, dir_b: Path
) -> list[tuple[str, Path | None, Path | None]]:
    """
    Match MP4 files between dir_a (reference) and dir_b (generated).
    Strategy: exact filename match, then report unmatched files separately.
    Returns list of (display_label, path_a_or_None, path_b_or_None).
    """
    files_a = {f.name: f for f in sorted(dir_a.glob("*.mp4"))}
    files_b = {f.name: f for f in sorted(dir_b.glob("*.mp4"))}
    all_names = sorted(set(files_a) | set(files_b))

    pairs = []
    for name in all_names:
        fa = files_a.get(name)
        fb = files_b.get(name)
        pairs.append((name, fa, fb))
    return pairs


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Pixel-level + metadata comparison of two MP4 folders."
    )
    ap.add_argument("--dir_a",   required=True,
                    help="Reference folder (datasetAVANTPREPROCESS)")
    ap.add_argument("--dir_b",   required=True,
                    help="Generated folder (datasetMP4)")
    ap.add_argument("--output",  default="comparison_mp4_bitabit.csv",
                    help="Output CSV path")
    ap.add_argument("--n_frames", type=int, default=20,
                    help="Frames sampled per video for pixel comparison (default: 20)")
    ap.add_argument("--count_frames", action="store_true",
                    help="Count actual frames via ffprobe -count_frames (slow, ~2× longer)")
    ap.add_argument("--skip_pixels", action="store_true",
                    help="Skip pixel-level comparison (metadata only, much faster)")
    args = ap.parse_args()

    dir_a = Path(args.dir_a)
    dir_b = Path(args.dir_b)

    for d in (dir_a, dir_b):
        if not d.exists():
            sys.exit(f"[error] Directory not found: {d}")

    pairs = build_pairs(dir_a, dir_b)
    n_both = sum(1 for _, fa, fb in pairs if fa and fb)
    print(f"Pairs: {len(pairs)} total  |  {n_both} with both files present")
    print(f"Sampling {args.n_frames} frames per video for pixel stats\n")

    rows: list[dict] = []

    for idx, (name, fa, fb) in enumerate(pairs, 1):
        status = ("both" if (fa and fb)
                  else "A_only" if fa
                  else "B_only")
        print(f"[{idx:02d}/{len(pairs)}] {name}  ({status})", end="  ", flush=True)

        row: dict = {"filename": name, "status": status}

        # ── Metadata ─────────────────────────────────────────────────────────
        ma = ffprobe_meta(fa) if fa else {}
        mb = ffprobe_meta(fb) if fb else {}

        for prefix, meta in (("REF", ma), ("GEN", mb)):
            row[f"{prefix}_size_MB"]      = (round(meta.get("size_bytes", 0) / 1e6, 3)
                                              if meta else "")
            row[f"{prefix}_size_bytes"]   = meta.get("size_bytes", "")
            row[f"{prefix}_duration_s"]   = meta.get("duration_s", "")
            row[f"{prefix}_fps"]          = meta.get("fps", "")
            row[f"{prefix}_width"]        = meta.get("width", "")
            row[f"{prefix}_height"]       = meta.get("height", "")
            row[f"{prefix}_codec"]        = meta.get("codec", "")
            row[f"{prefix}_pix_fmt"]      = meta.get("pix_fmt", "")
            row[f"{prefix}_bitrate_kbps"] = meta.get("bitrate_kbps", "")
            row[f"{prefix}_nb_frames_meta"] = meta.get("nb_frames_meta", "")

        # ── MD5 ──────────────────────────────────────────────────────────────
        row["REF_md5"] = md5_file(fa) if fa else ""
        row["GEN_md5"] = md5_file(fb) if fb else ""
        row["md5_identical"] = (
            (row["REF_md5"] == row["GEN_md5"]) if (fa and fb) else ""
        )

        # ── Deltas + match flags ──────────────────────────────────────────────
        if fa and fb and ma and mb:
            dur_a = ma.get("duration_s") or 0
            dur_b = mb.get("duration_s") or 0
            fps_a = ma.get("fps") or 0
            fps_b = mb.get("fps") or 0
            w_a   = ma.get("width") or 0
            w_b   = mb.get("width") or 0
            h_a   = ma.get("height") or 0
            h_b   = mb.get("height") or 0
            sz_a  = ma.get("size_bytes") or 0
            sz_b  = mb.get("size_bytes") or 0

            row["delta_duration_s"] = round(dur_b - dur_a, 6)
            row["delta_fps"]        = round(fps_b - fps_a, 6)
            row["delta_width_px"]   = w_b - w_a
            row["delta_height_px"]  = h_b - h_a
            row["delta_size_bytes"] = sz_b - sz_a
            row["dur_match"]        = abs(row["delta_duration_s"]) < 0.1
            row["fps_match"]        = abs(row["delta_fps"]) < 0.01
            row["dim_match"]        = (row["delta_width_px"] == 0 and
                                       row["delta_height_px"] == 0)
        else:
            for k in ("delta_duration_s", "delta_fps", "delta_width_px",
                      "delta_height_px", "delta_size_bytes",
                      "dur_match", "fps_match", "dim_match"):
                row[k] = ""

        # ── Frame count (optional, slow) ─────────────────────────────────────
        if args.count_frames:
            row["REF_nb_frames_actual"] = count_frames_exact(fa) if fa else ""
            row["GEN_nb_frames_actual"] = count_frames_exact(fb) if fb else ""
            if fa and fb and row["REF_nb_frames_actual"] and row["GEN_nb_frames_actual"]:
                row["delta_frames"] = (int(row["GEN_nb_frames_actual"])
                                       - int(row["REF_nb_frames_actual"]))
            else:
                row["delta_frames"] = ""

        # ── Pixel-level comparison ────────────────────────────────────────────
        if not args.skip_pixels and fa and fb:
            frames_a = sample_frames(fa, args.n_frames)
            frames_b = sample_frames(fb, args.n_frames)

            stats_a = pixel_stats_bgr(frames_a)
            stats_b = pixel_stats_bgr(frames_b)

            for ch in ("B", "G", "R"):
                row[f"REF_mean_{ch}"] = stats_a[ch]["mean"]
                row[f"REF_std_{ch}"]  = stats_a[ch]["std"]
                row[f"GEN_mean_{ch}"] = stats_b[ch]["mean"]
                row[f"GEN_std_{ch}"]  = stats_b[ch]["std"]
                delta_mean = (
                    round(stats_b[ch]["mean"] - stats_a[ch]["mean"], 3)
                    if (stats_a[ch]["mean"] is not None
                        and stats_b[ch]["mean"] is not None)
                    else None
                )
                row[f"delta_mean_{ch}"] = delta_mean

            cmp = compare_frame_pairs(frames_a, frames_b)
            row["mae_overall"] = cmp["mae_overall"]
            row["psnr_dB"]     = cmp["psnr_dB"]
            row["mae_B"]       = cmp["mae_B"]
            row["mae_G"]       = cmp["mae_G"]
            row["mae_R"]       = cmp["mae_R"]

            mae  = cmp["mae_overall"]
            psnr = cmp["psnr_dB"]
            print(f"MAE={mae:.3f}  PSNR={psnr:.1f} dB  "
                  f"(B={cmp['mae_B']:.3f} G={cmp['mae_G']:.3f} R={cmp['mae_R']:.3f})",
                  end="")
        else:
            if not args.skip_pixels:
                print("(skipped — missing file)", end="")

        print()
        rows.append(row)

    # ── Write CSV ─────────────────────────────────────────────────────────────
    if not rows:
        print("No files found.")
        return

    fieldnames = list(rows[0].keys())
    # Ensure all rows have all keys (missing ones from partial metadata)
    for row in rows:
        for k in fieldnames:
            row.setdefault(k, "")

    out = Path(args.output)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # ── Summary ───────────────────────────────────────────────────────────────
    both_rows = [r for r in rows if r["status"] == "both"]
    n_md5_id  = sum(1 for r in both_rows if r.get("md5_identical") is True)
    n_dur_ok  = sum(1 for r in both_rows if r.get("dur_match") is True)
    n_fps_ok  = sum(1 for r in both_rows if r.get("fps_match") is True)
    n_dim_ok  = sum(1 for r in both_rows if r.get("dim_match") is True)

    print(f"\n{'='*70}")
    print(f"Total pairs : {len(rows)}  |  both present: {len(both_rows)}")
    print(f"  MD5 identical  : {n_md5_id}/{len(both_rows)}")
    print(f"  Duration match : {n_dur_ok}/{len(both_rows)}  (Δ < 0.1 s)")
    print(f"  FPS match      : {n_fps_ok}/{len(both_rows)}")
    print(f"  Dimension match: {n_dim_ok}/{len(both_rows)}")

    if not args.skip_pixels:
        maes  = [r["mae_overall"] for r in both_rows
                 if r.get("mae_overall") not in (None, "")]
        psnrs = [r["psnr_dB"]     for r in both_rows
                 if r.get("psnr_dB")     not in (None, "")]
        if maes:
            print(f"  MAE overall — mean: {np.mean(maes):.3f}  "
                  f"min: {min(maes):.3f}  max: {max(maes):.3f}")
        if psnrs:
            print(f"  PSNR (dB)   — mean: {np.mean(psnrs):.1f}  "
                  f"min: {min(psnrs):.1f}  max: {max(psnrs):.1f}")

    print(f"\nCSV → {out.resolve()}")


if __name__ == "__main__":
    main()
