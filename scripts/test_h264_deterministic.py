#!/usr/bin/env python3
"""
test_h264_deterministic.py — H.264 uniquement, DETERMINISTIC_INFERENCE=True
===========================================================================
Refait le test d'encodage mais RESTREINT à H.264 (libx264), avec
DETERMINISTIC_INFERENCE activé (config.py). Chaque vidéo croppée de référence
(data_test) est ré-encodée en H.264 à plusieurs CRF, décodée par cv2, puis
passée dans le C3D. On compare le score au pred_score de Jérémy.

Encodages testés : orig (baseline) + H.264 crf 0 / 18 / 23 / 28.

Le backend C3D est celui de la config (C3D_BACKEND). Pour le chemin
« déterministe pytorch » (float64), lancer avec C3D_BACKEND=pytorch.

Usage :
    C3D_BACKEND=pytorch python scripts/test_h264_deterministic.py \\
        --output /Users/hugo/Desktop/STAGE/Testing/test_h264_deterministic.csv
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

import torch
import numpy as np
import random
import os

def seed_everything(seed=42):
    # 1. Python built-in random module
    random.seed(seed)
    
    # 2. Hash seed (needed for certain Python dictionaries and sets)
    os.environ['PYTHONHASHSEED'] = str(seed)
    
    # 3. NumPy
    np.random.seed(seed)
    
    # 4. PyTorch CPU & GPU
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed) # if you are using multi-GPU
    
    # 5. Deterministic CuDNN configurations
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

# Call the function
seed_everything(42)


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pythonCode" / "modules"))
import starhe_plugin.utils.go_print as gp
gp.go_print = lambda *a, **k: None
from starhe_plugin.config import DETERMINISTIC_INFERENCE, C3D_BACKEND
from starhe_plugin.ai.starhe_risk import STARHERiskModel

_YUV = ["-pix_fmt", "yuv420p"]
ENCODINGS = [
    ("orig",       None,                                                       ".mp4"),
    ("h264_crf0",  ["-c:v", "libx264", "-crf", "0",  "-preset", "slow"] + _YUV,   ".mp4"),
    ("h264_crf18", ["-c:v", "libx264", "-crf", "18", "-preset", "slow"] + _YUV,   ".mp4"),
    ("h264_crf23", ["-c:v", "libx264", "-crf", "23", "-preset", "medium"] + _YUV, ".mp4"),
    ("h264_crf28", ["-c:v", "libx264", "-crf", "28", "-preset", "medium"] + _YUV, ".mp4"),
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
    r = subprocess.run(["ffmpeg", "-y", "-i", src] + args + [out],
                       capture_output=True, text=True, timeout=600)
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
    ap.add_argument("--output", default="/Users/hugo/Desktop/STAGE/Testing/test_h264_deterministic.csv")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    seed_everything()

    jeremy = parse_jeremy(args.jeremy)
    mp4s = sorted(Path(args.refdir).glob("*.mp4"))
    if args.limit:
        mp4s = mp4s[:args.limit]
    enc_names = [e[0] for e in ENCODINGS]

    risk = STARHERiskModel()
    print(f"DETERMINISTIC_INFERENCE={DETERMINISTIC_INFERENCE}  C3D_BACKEND(config)={C3D_BACKEND}  "
          f"backend actif={risk._active_backend}  fichiers={len(mp4s)}\n", flush=True)

    rows = []
    work = tempfile.mkdtemp(prefix="h264det_")
    try:
        for idx, mp4 in enumerate(mp4s, 1):
            sid = re.match(r"(\d{2}-\d{4})", mp4.stem)
            sid = sid.group(1) if sid else mp4.stem
            jh = jeremy.get(sid)
            row = {"patient": sid, "jeremy_high": round(jh, 4) if jh is not None else ""}
            scores = []
            for name, eargs, ext in ENCODINGS:
                try:
                    vid = str(mp4) if name == "orig" else os.path.join(work, f"{sid}_{name}{ext}")
                    if name != "orig":
                        reencode(str(mp4), eargs, vid)
                    gray = read_gray(vid)
                    c3d_in = np.stack([gray, gray, gray], axis=-1)
                    sc = round(risk.predict(c3d_in)["risk_score"], 4)
                    row[name] = sc
                    scores.append(sc)
                    if name != "orig" and os.path.exists(vid):
                        os.unlink(vid)
                except Exception as e:
                    row[name] = f"ERR:{str(e)[:60]}"
            if scores:
                row["range"] = round(max(scores) - min(scores), 4)
            if jh is not None and isinstance(row.get("h264_crf18"), float):
                row["d_h264_crf18"] = round(row["h264_crf18"] - jh, 4)
            if jh is not None and isinstance(row.get("orig"), float):
                row["d_orig"] = round(row["orig"] - jh, 4)
            rows.append(row)
            print(f"[{idx:02d}/{len(mp4s)}] {sid}  jérémy={row['jeremy_high']}  "
                  f"orig={row.get('orig')}  h264_crf18={row.get('h264_crf18')}  "
                  f"Δcrf18={row.get('d_h264_crf18','')}  range={row.get('range')}", flush=True)
    finally:
        risk.close()
        shutil.rmtree(work, ignore_errors=True)

    cols = ["patient", "jeremy_high"] + enc_names + ["range", "d_orig", "d_h264_crf18"]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})

    import statistics as st
    for k in ("orig", "h264_crf18"):
        ds = [abs(r[k] - r["jeremy_high"]) for r in rows
              if isinstance(r.get(k), float) and isinstance(r.get("jeremy_high"), float)]
        if ds:
            print(f"\n|Δ vs Jérémy| ({k}) : moy={st.mean(ds):.4f}  méd={st.median(ds):.4f}  max={max(ds):.4f}")
    ranges = [r["range"] for r in rows if isinstance(r.get("range"), float)]
    if ranges:
        print(f"range H.264 (crf 0-28) par fichier : moy={st.mean(ranges):.4f}  max={max(ranges):.4f}")
    print(f"\nCSV → {args.output}")


if __name__ == "__main__":
    main()
