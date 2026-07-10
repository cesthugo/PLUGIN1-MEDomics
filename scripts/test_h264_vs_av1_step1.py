#!/usr/bin/env python3
"""
test_h264_vs_av1_step1.py — Impact du codec STEP-1 (H.264 vs AV1) sur le C3D
============================================================================
Hypothèse : les mp4 non-processés (sortie étape 1 DICOM→MP4) doivent être en
H.264, pas en AV1. On teste si régénérer le step-1 en H.264 rapproche le score
STARHE-RISK de la référence Jérémy.

Pour chaque patient (présent dans data_test / analyse jérémy) :
  • AV1  : mp4 step-1 existant (output_mp4_batch, libsvtav1)
  • H264 : régénéré depuis le DICOM (weasis→PNG→libx264, mêmes dims/fps)
  puis, pour chacun : prepUS direct (lit le mp4) → C3D → score_high
  comparé au pred_score de Jérémy.

Sortie CSV : patient, jeremy_high, av1_high, h264_high, deltas.

Usage :
    python scripts/test_h264_vs_av1_step1.py \\
        --output /Users/hugo/Desktop/STAGE/Testing/test_h264_vs_av1_step1.csv
"""

import argparse
import csv
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import cv2

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS.parent / "pythonCode" / "modules"))
sys.path.insert(0, str(_SCRIPTS))

import starhe_plugin.utils.go_print as gp
gp.go_print = lambda *a, **k: None
from starhe_plugin.dicom.prepus_bridge import preprocess_with_prepus_from_video
from starhe_plugin.ai.starhe_risk import STARHERiskModel

from dicom_batch_to_mp4 import (
    convert_one, find_java, find_reference, probe_mp4_fast,
)

DICOM_DIR = "/Users/hugo/Desktop/STAGE/Testing/datasetDICOM"
AV1_DIR = "/Users/hugo/Desktop/STAGE/Testing/output_mp4_batch"
REF_STEP1 = "/Users/hugo/Desktop/STAGE/VIDEO TESTING BATCH MP4 - À TESTER/datasetAVANTPREPROCESS"
DATA_TEST = "/Users/hugo/Desktop/STAGE/STARHE_ADRIEN_DATA-PREPROCESSED/data_test"


def parse_jeremy(path: str) -> dict:
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        m = re.search(r"(\d{2}-\d{4})", r.get("ID", ""))
        if not m:
            continue
        sm = re.search(r"pred_score.*?tensor\(\[([0-9.eE+-]+),\s*([0-9.eE+-]+)\]", r.get("AI", ""))
        out[m.group(1)] = float(sm.group(2)) if sm else None
    return out


def find_by_id(folder: str, sid: str, ext: str) -> str | None:
    for f in sorted(Path(folder).glob(f"*{ext}")):
        if f.name.startswith(sid):
            return str(f)
    return None


def score_via_direct(risk, mp4: str) -> float | str:
    cf, _ = preprocess_with_prepus_from_video(mp4)
    c3d_in = np.stack([cf, cf, cf], axis=-1)
    return round(risk.predict(c3d_in)["risk_score"], 4)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="/Users/hugo/Desktop/STAGE/Testing/test_h264_vs_av1_step1.csv")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    jeremy = parse_jeremy("/Users/hugo/Desktop/STAGE/Testing/analyse jérémy.csv")
    # patients = ceux présents dans data_test (sous-ensemble avec crops de réf)
    patients = sorted({re.match(r"(\d{2}-\d{4})", p.stem).group(1)
                       for p in Path(DATA_TEST).glob("*.mp4")
                       if re.match(r"(\d{2}-\d{4})", p.stem)})
    if args.limit:
        patients = patients[:args.limit]

    java = find_java(None)
    risk = STARHERiskModel()
    print(f"Java={'ok' if java else 'ABSENT'}  backend={risk._active_backend}  patients={len(patients)}\n", flush=True)

    rows = []
    work = tempfile.mkdtemp(prefix="h264test_")
    try:
        for idx, sid in enumerate(patients, 1):
            jh = jeremy.get(sid)
            row = {"patient": sid, "jeremy_high": round(jh, 4) if jh is not None else ""}

            dcm = find_by_id(DICOM_DIR, sid, ".dcm")
            av1 = find_by_id(AV1_DIR, sid, ".mp4")

            # cible fps/frames depuis la référence step-1 (comme dicom_batch)
            tgt_fps = tgt_frames = None
            ref = find_reference(REF_STEP1, sid)
            if ref:
                rf = probe_mp4_fast(ref)
                tgt_fps = rf.get("fps") or None
                tgt_frames = rf.get("frames") or None

            # ── H264 régénéré depuis DICOM ──
            h264_score = ""
            if dcm:
                h264_mp4 = os.path.join(work, f"{sid}_h264.mp4")
                res = convert_one(dcm, h264_mp4, java, dry_run=False,
                                  target_fps=tgt_fps, target_frames=tgt_frames,
                                  codec_override="libx264")
                if res.get("status") == "ok" and os.path.exists(h264_mp4):
                    try:
                        h264_score = score_via_direct(risk, h264_mp4)
                    except Exception as e:
                        h264_score = f"ERR:{str(e)[:60]}"
                    os.unlink(h264_mp4)
                else:
                    h264_score = f"conv_err:{res.get('error','?')[:60]}"

            # ── AV1 existant ──
            av1_score = ""
            if av1:
                try:
                    av1_score = score_via_direct(risk, av1)
                except Exception as e:
                    av1_score = f"ERR:{str(e)[:60]}"

            row["av1_high"] = av1_score
            row["h264_high"] = h264_score
            if jh is not None:
                if isinstance(av1_score, float):
                    row["d_av1"] = round(av1_score - jh, 4)
                if isinstance(h264_score, float):
                    row["d_h264"] = round(h264_score - jh, 4)
            if isinstance(av1_score, float) and isinstance(h264_score, float):
                row["h264_minus_av1"] = round(h264_score - av1_score, 4)
            rows.append(row)
            print(f"[{idx:02d}/{len(patients)}] {sid}  jérémy={row['jeremy_high']}  "
                  f"av1={av1_score} (Δ{row.get('d_av1','')})  "
                  f"h264={h264_score} (Δ{row.get('d_h264','')})", flush=True)
    finally:
        risk.close()
        import shutil
        shutil.rmtree(work, ignore_errors=True)

    cols = ["patient", "jeremy_high", "av1_high", "h264_high",
            "d_av1", "d_h264", "h264_minus_av1"]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})

    import statistics as st
    da = [abs(r["d_av1"]) for r in rows if isinstance(r.get("d_av1"), float)]
    dh = [abs(r["d_h264"]) for r in rows if isinstance(r.get("d_h264"), float)]
    dd = [abs(r["h264_minus_av1"]) for r in rows if isinstance(r.get("h264_minus_av1"), float)]
    print("\n" + "=" * 64)
    if da:
        print(f"|Δ vs Jérémy|  AV1  : moy={st.mean(da):.4f}  méd={st.median(da):.4f}")
    if dh:
        print(f"|Δ vs Jérémy|  H264 : moy={st.mean(dh):.4f}  méd={st.median(dh):.4f}")
    if dd:
        print(f"|H264 - AV1|        : moy={st.mean(dd):.4f}  max={max(dd):.4f}")
    print(f"\nCSV → {args.output}")


if __name__ == "__main__":
    main()
