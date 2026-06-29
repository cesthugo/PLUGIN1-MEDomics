#!/usr/bin/env python3
"""
compare_mp4_simple.py — Comparaison lisible des fichiers MP4 entre deux dossiers.
Colonnes : fichier, présent dans chaque dossier, identiques ou non, différence visuelle.
"""

import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import cv2

DIR_A = Path('/Users/hugo/Desktop/STAGE/VIDEO TESTING BATCH MP4 - À TESTER/datasetAVANTPREPROCESS')
DIR_B = Path('/Users/hugo/Desktop/STAGE/datasetMP4')
OUTPUT = Path('/Users/hugo/Desktop/STAGE/PLUGIN1-MEDomics/comparaison_mp4.csv')

N_FRAMES = 20  # frames échantillonnées pour la comparaison pixel


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fps_and_duration(path: Path) -> tuple[float, float]:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
           "-show_streams", "-show_format", str(path)]
    try:
        data = json.loads(subprocess.check_output(cmd, stderr=subprocess.DEVNULL))
        dur = float(data.get("format", {}).get("duration") or 0)
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                n, d = map(int, s.get("r_frame_rate", "0/1").split("/"))
                return (round(n / d, 2) if d else 0.0), round(dur, 2)
    except Exception:
        pass
    return 0.0, 0.0


def sample_frames(path: Path, n: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        frames = []
        while True:
            ret, f = cap.read()
            if not ret:
                break
            frames.append(f)
        cap.release()
        if not frames:
            return []
        idxs = np.linspace(0, len(frames) - 1, min(n, len(frames)), dtype=int)
        return [frames[i] for i in idxs]
    idxs = np.linspace(0, total - 1, min(n, total), dtype=int)
    out = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ret, f = cap.read()
        if ret:
            out.append(f)
    cap.release()
    return out


def mae_psnr(frames_a: list, frames_b: list) -> tuple[float, float]:
    n = min(len(frames_a), len(frames_b))
    if n == 0:
        return 0.0, 0.0
    maes, psnrs = [], []
    for fa, fb in zip(frames_a[:n], frames_b[:n]):
        if fa.shape != fb.shape:
            fb = cv2.resize(fb, (fa.shape[1], fa.shape[0]))
        diff = np.abs(fa.astype(np.float32) - fb.astype(np.float32))
        maes.append(float(diff.mean()))
        mse = float((diff ** 2).mean())
        if mse > 0:
            psnrs.append(20.0 * math.log10(255.0 / math.sqrt(mse)))
    return round(float(np.mean(maes)), 2), round(float(np.mean(psnrs)), 1) if psnrs else 0.0


def qualite(mae: float) -> str:
    if mae < 1.5:
        return "Très bonne — différence invisible à l'œil"
    if mae < 3.0:
        return "Bonne"
    if mae < 10.0:
        return "Modérée — différences légères"
    return "Mauvaise — différences importantes"


def patient_id(name: str) -> str:
    parts = name.replace(".mp4", "").split("-")
    return f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else name


# ── Matching ──────────────────────────────────────────────────────────────────

files_a = {f.name: f for f in sorted(DIR_A.glob("*.mp4"))}
files_b = {f.name: f for f in sorted(DIR_B.glob("*.mp4"))}

# Exact match first, then patient-ID match for files only in one folder
pairs: list[tuple[str, Path | None, Path | None]] = []
matched_a, matched_b = set(), set()

for name in sorted(set(files_a) & set(files_b)):
    pairs.append((name, files_a[name], files_b[name]))
    matched_a.add(name)
    matched_b.add(name)

# Files present only in A — try to find a partner in B by patient ID
by_pid_b = {patient_id(n): (n, p) for n, p in files_b.items() if n not in matched_b}
for name_a, path_a in files_a.items():
    if name_a in matched_a:
        continue
    pid = patient_id(name_a)
    if pid in by_pid_b:
        name_b, path_b = by_pid_b.pop(pid)
        pairs.append((f"{name_a}  ↔  {name_b}", path_a, path_b))
        matched_b.add(name_b)
    else:
        pairs.append((name_a, path_a, None))

for name_b, path_b in files_b.items():
    if name_b not in matched_b:
        pairs.append((name_b, None, path_b))

pairs.sort(key=lambda x: x[0])

# ── Compare ───────────────────────────────────────────────────────────────────

rows = []
print(f"{len(pairs)} fichiers à comparer\n")

for i, (label, fa, fb) in enumerate(pairs, 1):
    print(f"[{i:02d}/{len(pairs)}] {label} ...", end="  ", flush=True)

    row = {
        "Fichier": label,
        "Dans la référence": "Oui" if fa else "Non",
        "Dans la version générée": "Oui" if fb else "Non",
    }

    if not fa or not fb:
        row["Identiques"] = "N/A — fichier manquant"
        row["Similarité"] = ""
        row["FPS identique"] = ""
        row["Durée identique"] = ""
        row["Remarque"] = "Fichier absent dans un des deux dossiers"
        print("(fichier manquant)")
        rows.append(row)
        continue

    # MD5
    identical = md5(fa) == md5(fb)
    row["Identiques"] = "Oui" if identical else "Non"

    # FPS + durée
    fps_a, dur_a = fps_and_duration(fa)
    fps_b, dur_b = fps_and_duration(fb)
    row["FPS identique"] = "Oui" if abs(fps_a - fps_b) < 0.01 else f"Non ({fps_a} vs {fps_b})"
    row["Durée identique"] = "Oui" if abs(dur_a - dur_b) < 0.1 else f"Non ({dur_a}s vs {dur_b}s)"

    # Pixels
    frames_a = sample_frames(fa, N_FRAMES)
    frames_b = sample_frames(fb, N_FRAMES)
    mae, psnr = mae_psnr(frames_a, frames_b)
    row["Similarité"] = qualite(mae) if not identical else "Parfaite — bit à bit identiques"
    row["Remarque"] = f"MAE={mae}  PSNR={psnr} dB"

    print(f"MAE={mae}  PSNR={psnr} dB  → {qualite(mae)}")
    rows.append(row)

# ── CSV ───────────────────────────────────────────────────────────────────────

fieldnames = ["Fichier", "Dans la référence", "Dans la version générée",
              "Identiques", "FPS identique", "Durée identique", "Similarité", "Remarque"]

with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

# ── Résumé ────────────────────────────────────────────────────────────────────
both = [r for r in rows if r["Dans la référence"] == "Oui" and r["Dans la version générée"] == "Oui"]
n_id = sum(1 for r in both if r["Identiques"] == "Oui")
n_tres_bon = sum(1 for r in both if "Très bonne" in r.get("Similarité", ""))
n_mauvais  = sum(1 for r in both if "Mauvaise"  in r.get("Similarité", ""))

print(f"\n{'='*60}")
print(f"Fichiers comparés : {len(both)}")
print(f"  Bit à bit identiques   : {n_id}")
print(f"  Similarité très bonne  : {n_tres_bon}")
print(f"  Similarité mauvaise    : {n_mauvais}")
print(f"\nCSV → {OUTPUT.resolve()}")
