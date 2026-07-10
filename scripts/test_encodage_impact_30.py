#!/usr/bin/env python3
"""
test_encodage_impact_30.py — Impact de 30 ENCODAGES sur le score C3D
====================================================================
Plan factoriel étendu : chaque vidéo croppée de référence (data_test) est
RÉ-ENCODÉE avec 30 encodages courants (H.264, H.265, AV1, VP9, VP8, MPEG-4,
MPEG-2, MJPEG, lossless), du lossless au très lossy. Le DÉCODEUR est fixé
(cv2, comme le plugin) → on mesure l'effet PUR de l'encodage sur le C3D.

Sortie CSV :
  • lignes   : les 24 fichiers de data_test
  • colonnes : score_high pour chaque encodage (+ orig baseline)
  • + jeremy_high, min/max/range/std, max_dev_vs_orig, nframes_all_equal

Usage :
    python scripts/test_encodage_impact_30.py \\
        --output /Users/hugo/Desktop/STAGE/Testing/test_encodage_impact_30.csv
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
from starhe_plugin.ai.starhe_risk import STARHERiskModel


# ── 30 encodages : (nom, args ffmpeg de sortie, extension) ───────────────────
# "orig" = baseline (pas de ré-encodage). Presets rapides pour les codecs lents.
_YUV = ["-pix_fmt", "yuv420p"]
ENCODINGS = [
    ("orig",           None,                                                  ".mp4"),
    # ── H.264 (libx264) — le plus utilisé ──
    ("h264_crf0",      ["-c:v", "libx264", "-crf", "0",  "-preset", "slow"] + _YUV,   ".mp4"),
    ("h264_crf18",     ["-c:v", "libx264", "-crf", "18", "-preset", "slow"] + _YUV,   ".mp4"),
    ("h264_crf23",     ["-c:v", "libx264", "-crf", "23", "-preset", "medium"] + _YUV, ".mp4"),
    ("h264_crf28",     ["-c:v", "libx264", "-crf", "28", "-preset", "medium"] + _YUV, ".mp4"),
    ("h264_crf35",     ["-c:v", "libx264", "-crf", "35", "-preset", "medium"] + _YUV, ".mp4"),
    ("h264_crf45",     ["-c:v", "libx264", "-crf", "45", "-preset", "medium"] + _YUV, ".mp4"),
    # ── H.265 (libx265) ──
    ("h265_crf18",     ["-c:v", "libx265", "-crf", "18", "-preset", "medium"] + _YUV, ".mp4"),
    ("h265_crf23",     ["-c:v", "libx265", "-crf", "23", "-preset", "medium"] + _YUV, ".mp4"),
    ("h265_crf28",     ["-c:v", "libx265", "-crf", "28", "-preset", "medium"] + _YUV, ".mp4"),
    ("h265_crf35",     ["-c:v", "libx265", "-crf", "35", "-preset", "fast"] + _YUV,   ".mp4"),
    ("h265_crf45",     ["-c:v", "libx265", "-crf", "45", "-preset", "fast"] + _YUV,   ".mp4"),
    # ── AV1 (SVT-AV1) ──
    ("av1_crf20",      ["-c:v", "libsvtav1", "-crf", "20", "-preset", "8"] + _YUV,     ".mp4"),
    ("av1_crf30",      ["-c:v", "libsvtav1", "-crf", "30", "-preset", "8"] + _YUV,     ".mp4"),
    ("av1_crf40",      ["-c:v", "libsvtav1", "-crf", "40", "-preset", "8"] + _YUV,     ".mp4"),
    ("av1_crf50",      ["-c:v", "libsvtav1", "-crf", "50", "-preset", "8"] + _YUV,     ".mp4"),
    # ── VP9 (libvpx-vp9) ──
    ("vp9_crf20",      ["-c:v", "libvpx-vp9", "-crf", "20", "-b:v", "0", "-deadline", "good", "-cpu-used", "4"] + _YUV, ".webm"),
    ("vp9_crf31",      ["-c:v", "libvpx-vp9", "-crf", "31", "-b:v", "0", "-deadline", "good", "-cpu-used", "4"] + _YUV, ".webm"),
    ("vp9_crf45",      ["-c:v", "libvpx-vp9", "-crf", "45", "-b:v", "0", "-deadline", "good", "-cpu-used", "4"] + _YUV, ".webm"),
    # ── VP8 (libvpx) ──
    ("vp8_crf10",      ["-c:v", "libvpx", "-crf", "10", "-b:v", "0", "-deadline", "good", "-cpu-used", "4"] + _YUV, ".webm"),
    ("vp8_crf30",      ["-c:v", "libvpx", "-crf", "30", "-b:v", "0", "-deadline", "good", "-cpu-used", "4"] + _YUV, ".webm"),
    # ── MPEG-4 Part 2 (mpeg4) ──
    ("mpeg4_q2",       ["-c:v", "mpeg4", "-qscale:v", "2"],                    ".mp4"),
    ("mpeg4_q5",       ["-c:v", "mpeg4", "-qscale:v", "5"],                    ".mp4"),
    ("mpeg4_q10",      ["-c:v", "mpeg4", "-qscale:v", "10"],                   ".mp4"),
    ("mpeg4_q20",      ["-c:v", "mpeg4", "-qscale:v", "20"],                   ".mp4"),
    # ── MPEG-2 (mpeg2video) ──
    ("mpeg2_q2",       ["-c:v", "mpeg2video", "-qscale:v", "2"],              ".mp4"),
    ("mpeg2_q10",      ["-c:v", "mpeg2video", "-qscale:v", "10"],             ".mp4"),
    # ── MJPEG (intra) ──
    ("mjpeg_q2",       ["-c:v", "mjpeg", "-q:v", "2"],                         ".avi"),
    ("mjpeg_q8",       ["-c:v", "mjpeg", "-q:v", "8"],                         ".avi"),
    # ── Lossless ──
    ("ffv1_lossless",  ["-c:v", "ffv1"],                                       ".mkv"),
    ("rawvideo",       ["-c:v", "rawvideo", "-pix_fmt", "bgr24"],              ".avi"),
]


def parse_jeremy(path: str) -> dict:
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        m = re.search(r"(\d{2}-\d{4})", r.get("ID", ""))
        if not m:
            continue
        sm = re.search(r"pred_score.*?tensor\(\[([0-9.eE+-]+),\s*([0-9.eE+-]+)\]", r.get("AI", ""))
        out[m.group(1)] = float(sm.group(2)) if sm else None
    return out


def reencode(src: str, args: list, out: str) -> None:
    cmd = ["ffmpeg", "-y", "-i", src] + args + [out]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg: {r.stderr[-200:]}")


def read_gray(mp4: str) -> np.ndarray:
    cap = cv2.VideoCapture(mp4)
    buf = []
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        buf.append(cv2.cvtColor(frm, cv2.COLOR_BGR2GRAY) if frm.ndim == 3 else frm)
    cap.release()
    return np.stack(buf) if buf else np.zeros((0, 0, 0), np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refdir", default="/Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test")
    ap.add_argument("--jeremy", default="/Users/hugo/Desktop/STAGE/Testing/analyse jérémy.csv")
    ap.add_argument("--output", default="/Users/hugo/Desktop/STAGE/Testing/test_encodage_impact_30.csv")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    jeremy = parse_jeremy(args.jeremy)
    mp4s = sorted(Path(args.refdir).glob("*.mp4"))
    if args.limit:
        mp4s = mp4s[:args.limit]
    enc_names = [e[0] for e in ENCODINGS]

    risk = STARHERiskModel()
    print(f"Backend={risk._active_backend}  fichiers={len(mp4s)}  encodages={len(ENCODINGS)}\n", flush=True)

    rows = []
    work = tempfile.mkdtemp(prefix="enc30_")
    try:
        for idx, mp4 in enumerate(mp4s, 1):
            sid = re.match(r"(\d{2}-\d{4})", mp4.stem)
            sid = sid.group(1) if sid else mp4.stem
            jh = jeremy.get(sid)
            row = {"patient": sid, "jeremy_high": round(jh, 4) if jh is not None else ""}
            nframes = {}
            scores = []
            n_err = 0
            for name, eargs, ext in ENCODINGS:
                try:
                    if name == "orig":
                        vid = str(mp4)
                    else:
                        vid = os.path.join(work, f"{sid}_{name}{ext}")
                        reencode(str(mp4), eargs, vid)
                    gray = read_gray(vid)
                    if gray.size == 0:
                        raise RuntimeError("0 frame décodée")
                    nframes[name] = int(gray.shape[0])
                    c3d_in = np.stack([gray, gray, gray], axis=-1)
                    sc = round(risk.predict(c3d_in)["risk_score"], 4)
                    row[name] = sc
                    scores.append(sc)
                    if name != "orig" and os.path.exists(vid):
                        os.unlink(vid)
                except Exception as e:
                    row[name] = ""
                    n_err += 1
                    if f"{name}_err" not in row:
                        row[f"{name}_err"] = str(e)[:100]
            if scores:
                row["min"] = min(scores)
                row["max"] = max(scores)
                row["range"] = round(max(scores) - min(scores), 4)
                row["std"] = round(float(np.std(scores)), 4)
                if isinstance(row.get("orig"), float):
                    row["max_dev_vs_orig"] = round(max(abs(s - row["orig"]) for s in scores), 4)
            row["nframes_orig"] = nframes.get("orig", "")
            row["nframes_all_equal"] = len(set(nframes.values())) == 1 if nframes else ""
            row["n_enc_err"] = n_err
            rows.append(row)
            print(f"[{idx:02d}/{len(mp4s)}] {sid}  jérémy={row['jeremy_high']}  "
                  f"range={row.get('range')}  std={row.get('std')}  "
                  f"nf_eq={row['nframes_all_equal']}  err={n_err}", flush=True)
    finally:
        risk.close()
        shutil.rmtree(work, ignore_errors=True)

    cols = (["patient", "jeremy_high"] + enc_names +
            ["min", "max", "range", "std", "max_dev_vs_orig",
             "nframes_orig", "nframes_all_equal", "n_enc_err"])
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})

    # ── Résumé ──
    import statistics as st
    ranges = [r["range"] for r in rows if isinstance(r.get("range"), float)]
    stds = [r["std"] for r in rows if isinstance(r.get("std"), float)]
    print("\n" + "=" * 70)
    print("IMPACT DE 30 ENCODAGES (même vidéo, décodeur cv2 fixe)")
    if ranges:
        print(f"  range (max-min) par fichier : moy={st.mean(ranges):.4f}  "
              f"méd={st.median(ranges):.4f}  max={max(ranges):.4f}")
        print(f"  std par fichier             : moy={st.mean(stds):.4f}  max={max(stds):.4f}")
    nf_eq = sum(1 for r in rows if r.get("nframes_all_equal") is True)
    print(f"  nb frames identique/encodages : {nf_eq}/{len(rows)}")
    tot_err = sum(r.get("n_enc_err", 0) for r in rows)
    print(f"  encodages en erreur (total)   : {tot_err}/{len(rows)*(len(ENCODINGS)-1)}")
    print("\n  |Δ vs Jérémy| moyen par encodage :")
    for name in enc_names:
        ds = [abs(r[name] - r["jeremy_high"]) for r in rows
              if isinstance(r.get(name), float) and isinstance(r.get("jeremy_high"), float)]
        if ds:
            print(f"    {name:<16} {st.mean(ds):.4f}")
    print(f"\nCSV → {args.output}")


if __name__ == "__main__":
    main()
