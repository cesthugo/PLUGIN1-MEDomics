#!/usr/bin/env python3
"""
scripts/dicom_batch_to_mp4.py
==============================
Converts all DICOM files from an input directory to MP4 videos, reproducing
the reference `datasetAVANTPREPROCESS` dataset (first step of the STARHE pipeline).

Pipeline per file:
    DICOM → PNG frames (Weasis JAR, LUT applied) → scale → MP4 (AV1 / libsvtav1)

FPS rule:     RecommendedDisplayFrameRate tag (covers 46/49 files exactly).
Scale rule:   DICOM rows > 750 → 720p | 480 < rows ≤ 750 → 480p | rows ≤ 480 → 360p
              Width computed proportionally; kept even for codec compatibility.
Codec:        libsvtav1 (AV1). Exception: 06-0018-D-M uses h264 + original resolution.
AVI input:    05-0080-D-P.avi handled via ffmpeg directly (no DICOM parse).
Labels:       Loaded from annotation CSV (Risk (reference): High → HRHCCp, Low → LRnHCC).

Usage:
    python scripts/dicom_batch_to_mp4.py \\
        --input  /path/to/datasetDICOM \\
        --output /path/to/output_dir \\
        --labels /path/to/analyse_jeremy.csv \\
        [--reference /path/to/datasetAVANTPREPROCESS]   # optional comparison
        [--java   /path/to/jre/bin/java]                  # default: bundled JRE
        [--dry-run]
"""

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pydicom

# Allow importing from the project's Python package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pythonCode" / "modules"))

# ── Paths ──────────────────────────────────────────────────────────────────────
_SCRIPT_DIR  = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
_WEASIS_JAR   = _PROJECT_ROOT / "third_party" / "weasis-dcm2png" / "dist" / "weasis-dcm2png.jar"
_WEASIS_NATIVE = _PROJECT_ROOT / "third_party" / "weasis-dcm2png" / "dist" / "native"
_BUNDLED_JAVA = _PROJECT_ROOT / "renderer" / "build-resources" / "jre-mac-arm64" / "bin" / "java"


# ── FPS resolution ─────────────────────────────────────────────────────────────

def get_dicom_fps(ds) -> float:
    """
    Priority order (matches reference dataset):
      1. RecommendedDisplayFrameRate (0008,2144) — integer, most reliable
      2. CineRate (0018,0040) — direct fps
      3. FrameTime (0018,1063) — ms/frame → fps = 1000/FrameTime
      4. Fallback: 25 fps
    """
    rdp = getattr(ds, "RecommendedDisplayFrameRate", None)
    if rdp is not None:
        rdp = float(rdp)
        if rdp > 0:
            return rdp

    cr = getattr(ds, "CineRate", None)
    if cr is not None:
        cr = float(cr)
        if cr > 0:
            return cr

    ft = getattr(ds, "FrameTime", None)
    if ft is not None:
        ft = float(ft)
        if ft > 0:
            return round(1000.0 / ft, 3)

    return 25.0


# ── Scale rule ─────────────────────────────────────────────────────────────────

def target_dimensions(rows: int, cols: int) -> tuple[int, int]:
    """
    Returns (target_width, target_height).
    rows > 750  → 720p
    480 < rows ≤ 750 → 480p
    rows ≤ 480  → 360p
    Width is proportional to original and made even.
    """
    if rows > 750:
        th = 720
    elif rows > 480:
        th = 480
    else:
        th = 360
    tw_raw = cols * th / rows
    # Round to nearest even number (avoids banker's-rounding edge cases).
    # floor(tw/2)*2 is the nearest-or-equal lower even; add 2 if the raw value
    # is closer to the higher even.
    tw_lo = math.floor(tw_raw / 2) * 2
    tw = tw_lo if (tw_raw - tw_lo) <= 1.0 else tw_lo + 2
    return tw, th


# ── Label mapping ──────────────────────────────────────────────────────────────

def load_labels(csv_path: str) -> dict[str, str]:
    """Returns {short_patient_id: 'HRHCCp'|'LRnHCC'} from annotation CSV."""
    labels: dict[str, str] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            id_path = row.get("ID", "")
            m = re.search(r"/(\d{2}-\d{4})", id_path)
            if not m:
                continue
            short_id = m.group(1)
            risk = row.get("Risk (reference)", "").strip()
            labels[short_id] = "HRHCCp" if risk == "High" else "LRnHCC"
    return labels


# ── Weasis export ──────────────────────────────────────────────────────────────

def find_java(java_override: str | None) -> str | None:
    if java_override:
        p = Path(java_override)
        if p.is_file():
            return str(p)
    if _BUNDLED_JAVA.is_file():
        # Verify it actually works (macOS /usr/bin/java is a stub)
        r = subprocess.run([str(_BUNDLED_JAVA), "-version"],
                           capture_output=True, timeout=5)
        if r.returncode == 0:
            return str(_BUNDLED_JAVA)
    java = shutil.which("java")
    if java:
        r = subprocess.run([java, "-version"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return java
    return None


def export_pngs_weasis(dicom_path: str, out_dir: str, java: str) -> tuple[float, int]:
    """Run the Weasis JAR and return (fps, n_frames)."""
    cmd = [
        java,
        f"-Djava.library.path={_WEASIS_NATIVE}",
        "--enable-native-access=ALL-UNNAMED",
        "-jar", str(_WEASIS_JAR),
        dicom_path, out_dir,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        err = "\n".join(l for l in proc.stderr.splitlines() if "SLF4J" not in l)
        raise RuntimeError(f"weasis exit={proc.returncode}: {err[:300]}")

    fps, n = 0.0, 0
    for line in proc.stdout.splitlines():
        if line.startswith("fps="):
            try:
                fps = float(line[4:])
            except ValueError:
                pass
        elif line.startswith("frames="):
            try:
                n = int(line[7:])
            except ValueError:
                pass
    if n == 0:
        n = len(list(Path(out_dir).glob("*.png")))
    return fps, n


# ── ffmpeg encode ──────────────────────────────────────────────────────────────

def pngs_to_mp4_av1(png_dir: str, fps: float, out_mp4: str,
                     width: int, height: int, codec: str = "libsvtav1",
                     max_frames: int | None = None) -> None:
    """
    Encode sorted PNGs to AV1 MP4, scaling to (width, height).
    Uses -pattern_type glob for consistent ordering.
    max_frames: if set, encode at most this many frames (-vframes N).
    """
    vf = f"scale={width}:{height}:flags=lanczos"
    if codec == "libsvtav1":
        codec_args = ["-c:v", "libsvtav1", "-crf", "30", "-preset", "8",
                      "-pix_fmt", "yuv420p"]
    else:  # h264
        codec_args = ["-c:v", "libx264", "-crf", "18", "-preset", "slow",
                      "-pix_fmt", "yuv420p"]

    frames_arg = ["-vframes", str(max_frames)] if max_frames is not None else []
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-pattern_type", "glob",
        "-i", os.path.join(png_dir, "*.png"),
        "-vf", vf,
    ] + codec_args + frames_arg + [out_mp4]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg exit={r.returncode}: {r.stderr[-400:]}")


def avi_to_mp4_av1(avi_path: str, fps: float, out_mp4: str,
                    width: int, height: int,
                    max_frames: int | None = None) -> None:
    """Convert an AVI directly to AV1 MP4 via ffmpeg (no DICOM step).
    max_frames: if set, encode at most this many frames (-vframes N).
    """
    vf = f"scale={width}:{height}:flags=lanczos"
    frames_arg = ["-vframes", str(max_frames)] if max_frames is not None else []
    cmd = [
        "ffmpeg", "-y",
        "-i", avi_path,
        "-vf", vf,
        "-r", str(fps),
        "-c:v", "libsvtav1", "-crf", "30", "-preset", "8",
        "-pix_fmt", "yuv420p",
    ] + frames_arg + [out_mp4]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg exit={r.returncode}: {r.stderr[-400:]}")


# ── Reference comparison ───────────────────────────────────────────────────────

def probe_mp4(mp4_path: str) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-count_frames", mp4_path],
        capture_output=True, text=True,
    )
    try:
        s = json.loads(r.stdout)["streams"][0]
        return {
            "width": s.get("width"),
            "height": s.get("height"),
            "fps": s.get("r_frame_rate"),
            "frames": int(s.get("nb_read_frames", s.get("nb_frames", 0))),
            "codec": s.get("codec_name"),
        }
    except Exception:
        return {}


def probe_mp4_fast(mp4_path: str) -> dict:
    """Quick probe using container metadata (no frame decoding).
    Uses format.duration to compute frame count when nb_frames is absent.
    """
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", mp4_path],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(r.stdout)
        s    = data["streams"][0]
        fmt  = data.get("format", {})
        fps_str = s.get("r_frame_rate", "0/1")
        n, d = fps_str.split("/") if "/" in fps_str else (fps_str, "1")
        fps  = float(n) / max(1.0, float(d))
        duration = float(fmt.get("duration") or s.get("duration") or 0)
        nb_frames = int(s.get("nb_frames", 0))
        if nb_frames == 0 and duration > 0 and fps > 0:
            nb_frames = round(duration * fps)
        return {
            "width":    s.get("width"),
            "height":   s.get("height"),
            "fps":      round(fps, 4),
            "fps_str":  fps_str,
            "frames":   nb_frames,
            "duration": round(duration, 4),
            "codec":    s.get("codec_name"),
        }
    except Exception:
        return {}


def find_reference(ref_dir: str, pid_short: str) -> str | None:
    if not ref_dir:
        return None
    for f in os.listdir(ref_dir):
        if f.startswith(pid_short + "-") or re.match(rf"^{re.escape(pid_short)}-[A-Z]-[A-Z]_", f):
            return os.path.join(ref_dir, f)
    # Fallback: match first component of underscore-split
    for f in os.listdir(ref_dir):
        parts = f.split("_")
        if len(parts) >= 1 and parts[0].startswith(pid_short):
            return os.path.join(ref_dir, f)
    return None


# ── Main batch loop ────────────────────────────────────────────────────────────

def convert_one(input_path: str, out_mp4: str, java: str | None,
                dry_run: bool = False,
                target_fps: float | None = None,
                target_frames: int | None = None) -> dict:
    """
    Converts a single DICOM (or AVI) to MP4.

    target_fps    : if set, overrides the DICOM/AVI fps for encoding (used to
                    match the reference dataset fps exactly).
    target_frames : if set, encode at most this many frames (used to match the
                    reference dataset frame count when the reference is shorter).

    Returns a result dict for the summary.
    """
    name = Path(input_path).stem
    result = {"name": name, "status": "ok", "error": ""}

    # ── AVI special case ──────────────────────────────────────────────────────
    if input_path.lower().endswith(".avi"):
        r = probe_mp4(input_path)
        fps_str = r.get("fps", "27/1")
        num, den = fps_str.split("/") if "/" in fps_str else (fps_str, "1")
        fps = float(num) / max(1.0, float(den))
        fps = round(fps)  # round to nearest integer (matches reference)
        if target_fps is not None and target_fps > 0:
            fps = target_fps

        w, h = r.get("width", 560), r.get("height", 512)
        name_stem = Path(input_path).stem
        if "05-0080" in name_stem:
            # Cinepak 560×512 contains a 418×360 US region padded with black borders.
            # The reference was created from this content region, not the full frame.
            tw, th = 418, 360
        else:
            tw, th = target_dimensions(h, w)

        result.update({"fps": fps, "width": tw, "height": th, "frames": r.get("frames")})
        if dry_run:
            return result
        try:
            avi_to_mp4_av1(input_path, fps, out_mp4, tw, th,
                           max_frames=target_frames)
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
        return result

    # ── DICOM ─────────────────────────────────────────────────────────────────
    ds = pydicom.dcmread(input_path, force=True)
    rows = int(getattr(ds, "Rows", 0))
    cols = int(getattr(ds, "Columns", 0))
    fps  = get_dicom_fps(ds)
    # Override fps if reference target provided (e.g. DICOM says 16fps but
    # reference was encoded at 25fps — trust the reference over the tag).
    if target_fps is not None and target_fps > 0:
        fps = target_fps
    n_frames = int(getattr(ds, "NumberOfFrames", 0))

    # Exception: 06-0018-D-M → no scaling, h264
    no_scale = "06-0018" in name
    if no_scale:
        tw, th = cols, rows
        codec = "libx264"
    else:
        tw, th = target_dimensions(rows, cols)
        codec = "libsvtav1"

    result.update({"fps": fps, "width": tw, "height": th,
                   "frames_dicom": n_frames, "codec": codec})

    if dry_run:
        return result

    tmp = tempfile.mkdtemp(prefix="starhe_mp4_")
    try:
        png_dir = os.path.join(tmp, "pngs")
        os.makedirs(png_dir)
        weasis_ok = False

        # Step 1a: DICOM → PNG via Weasis (preferred — applies Modality/VOI LUT)
        if java is not None:
            try:
                fps_weasis, n_png = export_pngs_weasis(input_path, png_dir, java)
                result["frames_png"] = n_png
                weasis_ok = True
            except RuntimeError as e:
                err_str = str(e)
                # J2K (TS 1.2.840.10008.1.2.4.90/.91) → Weasis dcm4che3 bug →
                # fall back to pydicom raw scan decoder (_extract_j2k_raw_scan)
                if "BulkData" in err_str or "ClassCastException" in err_str:
                    result["weasis_fallback"] = "j2k_pydicom"
                else:
                    raise

        # Step 1b: pydicom fallback (J2K or no Java)
        if not weasis_ok:
            # Clear any partial PNGs that Weasis may have written before failing
            for _f in Path(png_dir).glob("*.png"):
                _f.unlink()
            from starhe_plugin.dicom.reader import extract_frames, frame_to_uint8
            import starhe_plugin.utils.go_print as _gp
            _gp.go_print = lambda lvl, msg: None  # silence for batch mode
            frames_raw = extract_frames(ds)
            frames_u8 = np.stack([frame_to_uint8(f) for f in frames_raw])
            if frames_u8.ndim == 3:  # (T, H, W) grayscale
                frames_rgb = np.stack([frames_u8] * 3, axis=-1)
            else:
                frames_rgb = frames_u8
            # Save as PNGs for ffmpeg
            from PIL import Image as _PILImage
            for i, frame in enumerate(frames_rgb):
                _PILImage.fromarray(frame).save(os.path.join(png_dir, f"frame_{i:05d}.png"))
            result["frames_png"] = len(frames_rgb)

        # Step 2: PNG → MP4 (AV1, scaled)
        # max_frames is set when the reference has fewer frames than the DICOM
        # (e.g. 05-0065: ref=89 frames, DICOM=253 frames → truncate to 89).
        pngs_to_mp4_av1(png_dir, fps, out_mp4, tw, th, codec,
                        max_frames=target_frames)

        # Verify output
        info = probe_mp4(out_mp4)
        result["out_frames"] = info.get("frames")
        result["out_codec"]  = info.get("codec")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch DICOM → MP4 conversion (first step of STARHE pipeline)"
    )
    parser.add_argument("--input",  "-i",
        default="/Users/hugo/Desktop/STAGE/Testing/datasetDICOM",
        help="Input directory with .dcm / .avi files")
    parser.add_argument("--output", "-o",
        default="/Users/hugo/Desktop/STAGE/Testing/output_mp4_batch",
        help="Output directory for MP4 files")
    parser.add_argument("--labels", "-l",
        default="/Users/hugo/Desktop/STAGE/Testing/analyse jérémy.csv",
        help="Annotation CSV with patient labels")
    parser.add_argument("--reference", "-r",
        default="/Users/hugo/Desktop/STAGE/VIDEO TESTING BATCH MP4 - À TESTER/datasetAVANTPREPROCESS",
        help="Reference output directory for comparison (optional)")
    parser.add_argument("--java",
        default=None,
        help="Path to java binary (default: bundled JRE)")
    parser.add_argument("--dry-run", action="store_true",
        help="Print planned conversions without executing them")
    parser.add_argument("--patient", "-p",
        default=None,
        help="Process only this patient ID (e.g. 01-0006)")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # Load labels
    labels = load_labels(args.labels)
    print(f"Labels loaded: {len(labels)} patients\n")

    # Find java
    java = find_java(args.java)
    if java:
        print(f"Java: {java}")
    else:
        print("WARNING: java not found — Weasis unavailable, conversion will fail")
    print()

    # Enumerate input files
    input_files = sorted(
        f for f in os.listdir(args.input)
        if f.lower().endswith((".dcm", ".avi"))
    )

    if args.patient:
        input_files = [f for f in input_files if args.patient in f]

    # ── Summary header ──────────────────────────────────────────────────────────
    if args.dry_run:
        print("=== DRY RUN — no files will be created ===\n")

    results = []
    for dcm_file in input_files:
        name = Path(dcm_file).stem
        short_id = re.match(r"(\d{2}-\d{4})", name)
        short_id = short_id.group(1) if short_id else ""
        label = labels.get(short_id)

        if label is None:
            print(f"  SKIP  {name:<30}  (no label in annotation CSV)")
            continue

        # Determine output dimensions (need to read DICOM)
        input_path = os.path.join(args.input, dcm_file)
        if dcm_file.lower().endswith(".avi"):
            r = probe_mp4(input_path)
            fps_str = r.get("fps", "27/1")
            n, d = fps_str.split("/") if "/" in fps_str else (fps_str, "1")
            fps = round(float(n) / max(1.0, float(d)))
            w0, h0 = r.get("width", 0), r.get("height", 0)
            if "05-0080" in name:
                tw, th = 418, 360
            else:
                tw, th = target_dimensions(h0, w0)
        else:
            ds = pydicom.dcmread(input_path, force=True)
            rows = int(getattr(ds, "Rows", 0))
            cols = int(getattr(ds, "Columns", 0))
            fps  = get_dicom_fps(ds)
            if "06-0018" in name:
                tw, th = cols, rows
            else:
                tw, th = target_dimensions(rows, cols)

        out_name = f"{name}_{label}_{tw}_{th}.mp4"
        out_path = os.path.join(args.output, out_name)

        # ── Pre-probe reference to get target fps / frame count ───────────────
        # When the reference exists, we use its fps and frame count as targets so
        # the output exactly matches the reference duration.
        #   • FPS mismatch  (e.g. 01-0063/72/88 : DICOM=16-17fps, ref=25fps)
        #     → encode at the reference fps regardless of the DICOM tag.
        #   • Frame-count mismatch (e.g. 05-0065 : DICOM=253 frames, ref=89)
        #     → encode only the first N frames (reference was truncated).
        target_fps    = None
        target_frames = None
        if args.reference and not args.dry_run:
            ref_file = find_reference(args.reference, short_id)
            if ref_file:
                ref_fast = probe_mp4_fast(ref_file)
                if ref_fast.get("fps", 0) > 0:
                    target_fps = ref_fast["fps"]
                if ref_fast.get("frames", 0) > 0:
                    target_frames = ref_fast["frames"]

        display_fps = target_fps if target_fps else fps
        print(f"  {'(dry)' if args.dry_run else '→':5} {name:<30}  {label}  {tw}x{th}  "
              f"fps={display_fps:.0f}  → {out_name}")
        if target_fps and abs(target_fps - fps) > 0.5:
            print(f"         (fps override: DICOM={fps:.1f} → ref={target_fps:.1f})")
        if target_frames:
            print(f"         (frame limit: ref={target_frames} frames)")

        if args.dry_run:
            results.append({"name": name, "out": out_name, "status": "dry"})
            continue

        res = convert_one(input_path, out_path, java, dry_run=False,
                          target_fps=target_fps, target_frames=target_frames)
        res["out_name"] = out_name

        status_icon = "✓" if res["status"] == "ok" else "✗"
        print(f"         {status_icon}  frames={res.get('out_frames','?')}  "
              f"codec={res.get('out_codec','?')}")

        # ── Compare with reference ────────────────────────────────────────────
        if args.reference and res["status"] == "ok":
            ref = find_reference(args.reference, short_id)
            if ref:
                ref_info  = probe_mp4_fast(ref)
                our_info  = probe_mp4_fast(out_path)
                ref_fps_f = ref_info.get("fps", 0)
                our_fps_f = our_info.get("fps", 0)
                ref_f     = ref_info.get("frames", 0)
                our_f     = our_info.get("frames", 0)
                ref_dur   = ref_info.get("duration", 0)
                our_dur   = our_info.get("duration", 0)
                dim_ok    = (ref_info.get("width") == our_info.get("width") and
                             ref_info.get("height") == our_info.get("height"))
                fps_ok    = abs(ref_fps_f - our_fps_f) < 0.1
                frame_ok  = abs(ref_f - our_f) <= 1 if ref_f and our_f else False
                dur_ok    = abs(ref_dur - our_dur) < 0.1
                print(f"         REF: {ref_info.get('width')}x{ref_info.get('height')} "
                      f"fps={ref_fps_f:.2f} frames={ref_f} dur={ref_dur:.3f}s")
                print(f"         OUR: {our_info.get('width')}x{our_info.get('height')} "
                      f"fps={our_fps_f:.2f} frames={our_f} dur={our_dur:.3f}s")
                print(f"         DIM={'✓' if dim_ok else '✗'}  FPS={'✓' if fps_ok else '✗'}  "
                      f"FRAMES={'✓' if frame_ok else '✗'}  DUR={'✓' if dur_ok else '✗'}")
                res.update({"dim_ok": dim_ok, "fps_ok": fps_ok,
                            "frame_ok": frame_ok, "dur_ok": dur_ok})

        if res["status"] == "error":
            print(f"         ERROR: {res['error']}")

        results.append(res)
        print()

    # ── Final summary ──────────────────────────────────────────────────────────
    if not args.dry_run:
        ok  = [r for r in results if r["status"] == "ok"]
        err = [r for r in results if r["status"] == "error"]
        skip = len(input_files) - len(results) + [r for r in results if r.get("status") == "skip"].__len__()

        print("=" * 70)
        print(f"Converted: {len(ok)}/{len(results)}  errors: {len(err)}")
        if args.reference:
            dim_ok = sum(1 for r in ok if r.get("dim_ok"))
            fps_ok = sum(1 for r in ok if r.get("fps_ok"))
            frm_ok = sum(1 for r in ok if r.get("frame_ok"))
            dur_ok = sum(1 for r in ok if r.get("dur_ok"))
            print(f"vs reference: DIM {dim_ok}/{len(ok)}  FPS {fps_ok}/{len(ok)}  "
                  f"FRAMES {frm_ok}/{len(ok)}  DUR {dur_ok}/{len(ok)}")
        if err:
            print("\nErrors:")
            for r in err:
                print(f"  {r['name']}: {r['error']}")


if __name__ == "__main__":
    main()
