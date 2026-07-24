#!/usr/bin/env python3
"""
build_recap_csv.py — CSV récapitulatif de comparaison des scores STARHE-RISK.

Compare, par patient, trois sources de score « risque élevé » :
  1. jeremy      : référence Jérémy (analyse jérémy.csv, pred_score tensor([low,high]))
  2. batch_dicom : pipeline COMPLÈTE depuis DICOM (starhe_batch_*.json, risk.score)
  3. prepus_mp4  : nouveau test — datasetAVANTPREPROCESS (mp4) → prepUS → C3D

Sortie : par patient, les 3 scores + écarts vs Jérémy + accords de label (seuil 0.5).
"""

import csv
import json
import re
import statistics as st
from pathlib import Path

JEREMY = "/Users/hugo/Desktop/STAGE/Testing/analyse jérémy.csv"
BATCH = "/Users/hugo/Downloads/starhe_batch_2026-07-14.json"
NEWTEST = "/Users/hugo/Desktop/STAGE/Testing/test_prepus_inference_current.csv"
OUT = "/Users/hugo/Desktop/STAGE/Testing/recap_comparaison_jeremy.csv"


def pid(s):
    m = re.search(r"(\d{2}-\d{4})", s or "")
    return m.group(1) if m else None


def parse_jeremy(path):
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        p = pid(r.get("ID", ""))
        if not p:
            continue
        m = re.search(r"pred_score.*?tensor\(\[([0-9.eE+-]+),\s*([0-9.eE+-]+)\]", r.get("AI", ""))
        out[p] = float(m.group(2)) if m else None
    return out


def parse_batch(path):
    d = json.load(open(path, encoding="utf-8"))
    out = {}
    for r in d.get("results", []):
        p = pid(r.get("file_name", ""))
        if p and r.get("risk"):
            out[p] = float(r["risk"]["score"])
    return out


def parse_newtest(path):
    out = {}
    if not Path(path).exists():
        return out
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = pid(r.get("patient", ""))
        try:
            out[p] = float(r.get("our_high"))
        except (TypeError, ValueError):
            pass
    return out


def cls(x):
    return "" if x is None else ("High" if x >= 0.5 else "Low")


def verdict(x):
    return "—" if x is None else ("Risque élevé" if x >= 0.5 else "Risque faible")


def pct(x):
    return "—" if x is None else f"{x * 100:.1f} %"


def pts(a, b):
    """Écart (a − b) en points de pourcentage, signé."""
    if a is None or b is None:
        return "—"
    d = (a - b) * 100
    return f"{d:+.1f} pts"


def oui_non(a, b):
    if a is None or b is None:
        return "—"
    return "Oui" if cls(a) == cls(b) else "Non"


# En-têtes lisibles (colonne interne → libellé affiché)
COLS = [
    ("Patient", "patient"),
    ("Score de référence (Jérémy)", "ref"),
    ("Score — pipeline complète (depuis DICOM)", "batch"),
    ("Score — test prepUS → RISK", "prepus"),
    ("Écart pipeline vs référence", "d_batch"),
    ("Écart prepUS vs référence", "d_prepus"),
    ("Verdict de référence", "v_ref"),
    ("Verdict pipeline", "v_batch"),
    ("Verdict prepUS", "v_prepus"),
    ("Même verdict — pipeline ?", "m_batch"),
    ("Même verdict — prepUS ?", "m_prepus"),
]


def main():
    jer, bat, new = parse_jeremy(JEREMY), parse_batch(BATCH), parse_newtest(NEWTEST)
    patients = sorted(set(jer) | set(bat) | set(new))

    rows = []
    for p in patients:
        j, b, n = jer.get(p), bat.get(p), new.get(p)
        rows.append({
            "patient": p,
            "ref": pct(j), "batch": pct(b), "prepus": pct(n),
            "d_batch": pts(b, j), "d_prepus": pts(n, j),
            "v_ref": verdict(j), "v_batch": verdict(b), "v_prepus": verdict(n),
            "m_batch": oui_non(b, j), "m_prepus": oui_non(n, j),
        })

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([label for label, _ in COLS])
        for r in rows:
            w.writerow([r[key] for _, key in COLS])

    # ── Résumé (calculé sur les scores bruts) ──
    def stats(src):
        ds = [abs(src[p] - jer[p]) for p in src if p in jer]
        ms = [cls(src[p]) == cls(jer[p]) for p in src if p in jer]
        return ds, ms

    print(f"patients: {len(rows)}  (jeremy={len(jer)} batch={len(bat)} newtest={len(new)})")
    for label, src in [("Pipeline complète (depuis DICOM)", bat),
                       ("Test prepUS → RISK", new)]:
        ds, ms = stats(src)
        if ds:
            print(f"\n{label}:")
            print(f"  |écart| moyen vs référence = {st.mean(ds) * 100:.1f} pts "
                  f"(méd {st.median(ds) * 100:.1f}, max {max(ds) * 100:.1f})")
            print(f"  même verdict (seuil 50 %): {sum(ms)}/{len(ms)}")
    print(f"\nCSV → {OUT}")


if __name__ == "__main__":
    main()
