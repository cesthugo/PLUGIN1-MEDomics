#!/usr/bin/env python3
"""
test_prepus_encodage_30.py — datasetAVANTPREPROCESS → prepUS → 30 encodages → C3D
=================================================================================
Pour chaque mp4 de datasetAVANTPREPROCESS :
  1. prepUS (chemin actif du plugin) → crop (retrait UI + cône)  [frames numpy]
  2. le crop est ré-encodé de 30 manières (mêmes encodages que test_encodage_impact_30)
  3. inférence C3D STARHE-RISK sur chaque variante ; comparaison au pred_score de Jérémy

"orig" = crop numpy brut (sans ré-encodage). Décodeur fixe = cv2.
CSV écrit incrémentalement (une ligne par patient dès qu'il est fini).

Usage :
    python scripts/test_prepus_encodage_30.py \\
        --input "/Users/hugo/Desktop/STAGE/VIDEO TESTING BATCH MP4 - À TESTER/datasetAVANTPREPROCESS" \\
        --output /Users/hugo/Desktop/STAGE/Testing/test_prepus_encodage_30.csv
"""

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pythonCode" / "modules"))
import starhe_plugin.utils.go_print as gp
gp.go_print = lambda *a, **k: None
from starhe_plugin.config import DETERMINISTIC_INFERENCE, PREPUS_BYPASS_MP4
from starhe_plugin.dicom.prepus_bridge import (
    preprocess_with_prepus, preprocess_with_prepus_inmem)
from starhe_plugin.ai.starhe_risk import STARHERiskModel

_YUV = ["-pix_fmt", "yuv420p"]
ENCODINGS = [
    ("orig",           None,                                                  ".mp4"),
    ("h264_crf0",  ["-c:v","libx264","-crf","0","-preset","slow"] + _YUV,   ".mp4"),
    ("h264_crf18", ["-c:v","libx264","-crf","18","-preset","slow"] + _YUV,   ".mp4"),
    ("h264_crf23", ["-c:v","libx264","-crf","23","-preset","medium"] + _YUV, ".mp4"),
    ("h264_crf28", ["-c:v","libx264","-crf","28","-preset","medium"] + _YUV, ".mp4"),
    ("h264_crf35", ["-c:v","libx264","-crf","35","-preset","medium"] + _YUV, ".mp4"),
    ("h264_crf45", ["-c:v","libx264","-crf","45","-preset","medium"] + _YUV, ".mp4"),
    ("h265_crf18", ["-c:v","libx265","-crf","18","-preset","medium"] + _YUV, ".mp4"),
    ("h265_crf23", ["-c:v","libx265","-crf","23","-preset","medium"] + _YUV, ".mp4"),
    ("h265_crf28", ["-c:v","libx265","-crf","28","-preset","medium"] + _YUV, ".mp4"),
    ("h265_crf35", ["-c:v","libx265","-crf","35","-preset","fast"] + _YUV,   ".mp4"),
    ("h265_crf45", ["-c:v","libx265","-crf","45","-preset","fast"] + _YUV,   ".mp4"),
    ("av1_crf20",  ["-c:v","libsvtav1","-crf","20","-preset","8"] + _YUV,     ".mp4"),
    ("av1_crf30",  ["-c:v","libsvtav1","-crf","30","-preset","8"] + _YUV,     ".mp4"),
    ("av1_crf40",  ["-c:v","libsvtav1","-crf","40","-preset","8"] + _YUV,     ".mp4"),
    ("av1_crf50",  ["-c:v","libsvtav1","-crf","50","-preset","8"] + _YUV,     ".mp4"),
    ("vp9_crf20",  ["-c:v","libvpx-vp9","-crf","20","-b:v","0","-deadline","good","-cpu-used","4"] + _YUV, ".webm"),
    ("vp9_crf31",  ["-c:v","libvpx-vp9","-crf","31","-b:v","0","-deadline","good","-cpu-used","4"] + _YUV, ".webm"),
    ("vp9_crf45",  ["-c:v","libvpx-vp9","-crf","45","-b:v","0","-deadline","good","-cpu-used","4"] + _YUV, ".webm"),
    ("vp8_crf10",  ["-c:v","libvpx","-crf","10","-b:v","0","-deadline","good","-cpu-used","4"] + _YUV, ".webm"),
    ("vp8_crf30",  ["-c:v","libvpx","-crf","30","-b:v","0","-deadline","good","-cpu-used","4"] + _YUV, ".webm"),
    ("mpeg4_q2",   ["-c:v","mpeg4","-qscale:v","2"],                       ".mp4"),
    ("mpeg4_q5",   ["-c:v","mpeg4","-qscale:v","5"],                       ".mp4"),
    ("mpeg4_q10",  ["-c:v","mpeg4","-qscale:v","10"],                      ".mp4"),
    ("mpeg4_q20",  ["-c:v","mpeg4","-qscale:v","20"],                      ".mp4"),
    ("mpeg2_q2",   ["-c:v","mpeg2video","-qscale:v","2"],                  ".mp4"),
    ("mpeg2_q10",  ["-c:v","mpeg2video","-qscale:v","10"],                 ".mp4"),
    ("mjpeg_q2",   ["-c:v","mjpeg","-q:v","2"],                            ".avi"),
    ("mjpeg_q8",   ["-c:v","mjpeg","-q:v","8"],                            ".avi"),
    ("ffv1_lossless", ["-c:v","ffv1"],                                     ".mkv"),
    ("rawvideo",   ["-c:v","rawvideo","-pix_fmt","bgr24"],                 ".avi"),
]


def parse_jeremy(path):
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        m = re.search(r"(\d{2}-\d{4})", r.get("ID", ""))
        if not m:
            continue
        sm = re.search(r"pred_score.*?tensor\(\[([0-9.eE+-]+),\s*([0-9.eE+-]+)\]", r.get("AI", ""))
        out[m.group(1)] = float(sm.group(2)) if sm else None
    return out


def read_rgb(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 22.0
    buf = []
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        buf.append(cv2.cvtColor(frm, cv2.COLOR_BGR2RGB))
    cap.release()
    return (np.stack(buf) if buf else np.zeros((0, 0, 0, 3), np.uint8)), float(fps)


def read_gray(path):
    cap = cv2.VideoCapture(path)
    buf = []
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        buf.append(cv2.cvtColor(frm, cv2.COLOR_BGR2GRAY) if frm.ndim == 3 else frm)
    cap.release()
    return np.stack(buf) if buf else np.zeros((0, 0, 0), np.uint8)


def gray_to_lossless(frames, out_mkv, fps=25):
    """Écrit un crop grayscale (T,H,W) → ffv1 lossless (source à ré-encoder)."""
    T, H, W = frames.shape
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "pipe:0", "-c:v", "ffv1", out_mkv]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for f in frames:
            p.stdin.write(np.ascontiguousarray(f).tobytes())
        p.stdin.close()
    except BrokenPipeError:
        pass
    return p.wait() == 0


def reencode(src, args, out):
    r = subprocess.run(["ffmpeg", "-y", "-i", src] + args + [out],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg: {r.stderr[-200:]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/Users/hugo/Desktop/STAGE/VIDEO TESTING BATCH MP4 - À TESTER/datasetAVANTPREPROCESS")
    ap.add_argument("--jeremy", default="/Users/hugo/Desktop/STAGE/Testing/analyse jérémy.csv")
    ap.add_argument("--output", default="/Users/hugo/Desktop/STAGE/Testing/test_prepus_encodage_30.csv")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    jeremy = parse_jeremy(args.jeremy)
    mp4s = sorted(Path(args.input).glob("*.mp4"))
    if args.limit:
        mp4s = mp4s[:args.limit]
    enc_names = [e[0] for e in ENCODINGS]
    prep_fn = preprocess_with_prepus_inmem if PREPUS_BYPASS_MP4 else preprocess_with_prepus

    risk = STARHERiskModel()
    print(f"DETERMINISTIC={DETERMINISTIC_INFERENCE} BYPASS={PREPUS_BYPASS_MP4} "
          f"backend={risk._active_backend}  fichiers={len(mp4s)}  encodages={len(ENCODINGS)}\n", flush=True)

    cols = (["patient", "jeremy_high", "prepus_crop", "prepus_fallback"] + enc_names +
            ["min", "max", "range", "std", "d_orig_vs_jeremy", "n_enc_err"])
    fout = open(args.output, "w", newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(fout, fieldnames=cols)
    writer.writeheader(); fout.flush()

    work = tempfile.mkdtemp(prefix="prepenc_")
    all_ranges = []
    try:
        for idx, mp4 in enumerate(mp4s, 1):
            sid = re.match(r"(\d{2}-\d{4})", mp4.stem)
            sid = sid.group(1) if sid else mp4.stem
            jh = jeremy.get(sid)
            row = {"patient": sid, "jeremy_high": round(jh, 4) if jh is not None else ""}

            # 1. prepUS → crop numpy
            try:
                frames_rgb, fps = read_rgb(str(mp4))
                crop, info = prep_fn(frames_rgb, fps=fps, thresh=-1.0,
                                     backscan_width=512, backscan_height=512)
                row["prepus_crop"] = f"{crop.shape[0]}x{crop.shape[1]}x{crop.shape[2]}"
                row["prepus_fallback"] = bool(info and info.get("fallback") == "crop.py")
            except Exception as e:
                row["prepus_crop"] = f"ERR:{str(e)[:50]}"
                writer.writerow({k: row.get(k, "") for k in cols}); fout.flush()
                print(f"[{idx:02d}/{len(mp4s)}] {sid}  prepUS ERR", flush=True)
                continue

            # source lossless du crop (pour ré-encoder)
            src = os.path.join(work, f"{sid}_src.mkv")
            gray_to_lossless(crop, src, fps=int(round(fps)))

            # 2+3. 30 encodages → C3D
            scores, n_err = [], 0
            for name, eargs, ext in ENCODINGS:
                try:
                    if name == "orig":
                        g = crop
                    else:
                        vid = os.path.join(work, f"{sid}_{name}{ext}")
                        reencode(src, eargs, vid)
                        g = read_gray(vid)
                        os.unlink(vid)
                    if g.size == 0:
                        raise RuntimeError("0 frame")
                    sc = round(risk.predict(np.stack([g, g, g], axis=-1))["risk_score"], 4)
                    row[name] = sc; scores.append(sc)
                except Exception as e:
                    row[name] = ""; n_err += 1
            os.unlink(src)

            if scores:
                row["min"] = min(scores); row["max"] = max(scores)
                row["range"] = round(max(scores) - min(scores), 4)
                row["std"] = round(float(np.std(scores)), 4)
                all_ranges.append(row["range"])
            if jh is not None and isinstance(row.get("orig"), float):
                row["d_orig_vs_jeremy"] = round(row["orig"] - jh, 4)
            row["n_enc_err"] = n_err

            writer.writerow({k: row.get(k, "") for k in cols}); fout.flush()
            print(f"[{idx:02d}/{len(mp4s)}] {sid}  jérémy={row['jeremy_high']} "
                  f"orig={row.get('orig')} range={row.get('range')} fb={row['prepus_fallback']} err={n_err}", flush=True)
    finally:
        risk.close(); fout.close()
        shutil.rmtree(work, ignore_errors=True)

    import statistics as st
    if all_ranges:
        print(f"\nrange du score par fichier (sur 30 encodages) : moy={st.mean(all_ranges):.4f} "
              f"méd={st.median(all_ranges):.4f} max={max(all_ranges):.4f}")
    print(f"CSV → {args.output}")


if __name__ == "__main__":
    main()
