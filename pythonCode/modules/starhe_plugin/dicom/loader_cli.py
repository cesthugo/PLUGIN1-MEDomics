"""
dicom/loader_cli.py — CLI pour charger un DICOM et retourner les frames en JPEG base64
========================================================================================
Appelé par le serveur Go pour alimenter le frontend React.

Usage :
    python -m starhe_plugin.dicom.loader_cli <dicom_path> [--quality 70] [--max-dim 640]

Sortie stdout : JSON unique avec toutes les frames encodées en JPEG base64.
Format de sortie :
{
  "file_name":          "example.dcm",
  "frame_count":        100,
  "rows":               480,
  "cols":               640,
  "modality":           "US",
  "pixel_spacing":      [0.25, 0.25],   // null si absent
  "base_fps":           22.0,
  "original_sensitive": [["PatientName", "Doe^John"], ...],
  "kept_metadata":      [["Modalité", "US"], ...],
  "patient_name":       "Doe John",
  "study_date":         "20240101",
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

# Ajoute le dossier modules au path pour les imports relatifs
_MODULES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)


_SENS_LABEL: dict[tuple, str] = {
    (0x0010, 0x0010): "PatientName",
    (0x0010, 0x0020): "PatientID",
    (0x0010, 0x0030): "PatientBirthDate",
    (0x0010, 0x0040): "PatientSex",
    (0x0010, 0x1010): "PatientAge",
    (0x0008, 0x0020): "StudyDate",
    (0x0008, 0x0030): "StudyTime",
    (0x0008, 0x0090): "ReferringPhysician",
    (0x0008, 0x1030): "StudyDescription",
    (0x0008, 0x103E): "SeriesDescription",
    (0x0020, 0x000D): "StudyInstanceUID",
    (0x0020, 0x000E): "SeriesInstanceUID",
    (0x0008, 0x0018): "SOPInstanceUID",
    (0x0032, 0x1032): "RequestingPhysician",
    (0x0040, 0xA124): "UID",
}

_KEPT_ATTRS: list[tuple[str, str]] = [
    ("Modality",                  "Modalité"),
    ("Manufacturer",              "Fabricant"),
    ("ManufacturerModelName",     "Modèle"),
    ("InstitutionName",           "Institution"),
    ("BodyPartExamined",          "Zone exam."),
    ("Rows",                      "Lignes"),
    ("Columns",                   "Colonnes"),
    ("NumberOfFrames",            "Nb frames"),
    ("FrameTime",                 "Tps/frame ms"),
    ("PhotometricInterpretation", "Photométrie"),
    ("BitsAllocated",             "Bits alloués"),
    ("SamplesPerPixel",           "Canaux"),
    ("TransducerType",            "Transducteur"),
]


def _extract_pixel_spacing(ds) -> list[float] | None:
    """Extrait l'espacement pixel depuis les tags DICOM (plusieurs fallbacks)."""
    # Priorité 1 : PixelSpacing
    try:
        ps = ds.PixelSpacing
        return [float(ps[0]), float(ps[1])]
    except AttributeError:
        pass
    # Priorité 2 : ImagerPixelSpacing
    try:
        ps = ds.ImagerPixelSpacing
        return [float(ps[0]), float(ps[1])]
    except AttributeError:
        pass
    # Priorité 3 : Régions US (PhysicalDeltaX/Y en cm/pixel)
    try:
        region = ds.SequenceOfUltrasoundRegions[0]
        row_mm = abs(float(region.PhysicalDeltaY)) * 10.0
        col_mm = abs(float(region.PhysicalDeltaX)) * 10.0
        if row_mm > 0 and col_mm > 0:
            return [row_mm, col_mm]
    except (AttributeError, IndexError, TypeError):
        pass
    return None


def load_and_encode(
    dicom_path: str,
    quality: int = 70,
    max_dim: int = 640,
) -> dict:
    """Charge un DICOM, anonymise, extrait les frames, encode en JPEG base64.

    Retourne un dict prêt à être sérialisé en JSON.
    """
    import numpy as np
    from PIL import Image

    from starhe_plugin.dicom.reader     import load_dicom, extract_frames, frame_to_uint8
    from starhe_plugin.dicom.anonymizer import anonymize, remove_pixel_burnin
    from starhe_plugin.config           import DICOM_SENSITIVE_TAGS

    ds = load_dicom(dicom_path)

    # ── Capture des valeurs sensibles AVANT anonymisation ─────────────────────
    original_sensitive: list[list[str]] = []
    for tag in DICOM_SENSITIVE_TAGS:
        name = _SENS_LABEL.get(tag, str(tag))
        val  = str(ds[tag].value).strip() if tag in ds else "— absent"
        original_sensitive.append([name, val])

    ds = anonymize(ds)

    # ── Extraction et normalisation des frames ────────────────────────────────
    # Max 120 frames pour l'affichage : évite de décoder des centaines de frames J2K
    # (le pipeline AI utilise extract_frames sans cette limite pour l'analyse complète)
    MAX_DISPLAY_FRAMES = 120
    frames_raw = extract_frames(ds, display_max_frames=MAX_DISPLAY_FRAMES)

    if frames_raw.ndim == 3:
        frames_uint8 = np.stack([frame_to_uint8(f) for f in frames_raw])
        frames_rgb   = np.stack([frames_uint8] * 3, axis=-1)
    else:
        frames_uint8 = np.stack([frame_to_uint8(f) for f in frames_raw])
        frames_rgb   = frames_uint8
    del frames_raw  # libère ~400 MB si frames RGB 1280×890

    frames_rgb = remove_pixel_burnin(frames_rgb)

    # ── Métadonnées conservées ────────────────────────────────────────────────
    kept_metadata: list[list[str]] = []
    for attr, label in _KEPT_ATTRS:
        val = getattr(ds, attr, None)
        if val is not None:
            kept_metadata.append([label, str(val).strip()])

    # ── Pixel spacing ─────────────────────────────────────────────────────────
    pixel_spacing = _extract_pixel_spacing(ds)

    # ── FPS natif ─────────────────────────────────────────────────────────────
    frame_time_ms = getattr(ds, "FrameTime", None)
    try:
        base_fps = 1000.0 / float(frame_time_ms) if frame_time_ms else 22.0
    except (ValueError, ZeroDivisionError):
        base_fps = 22.0

    # ── Nom patient (pour groupement d'onglets) ───────────────────────────────
    patient_name_raw = next(
        (v for n, v in original_sensitive if n == "PatientName" and v != "— absent"),
        "Patient inconnu",
    )
    patient_name = patient_name_raw.replace("^", " ").strip() or "Patient inconnu"

    study_date = next(
        (v for n, v in original_sensitive if n == "StudyDate" and v != "— absent"),
        "",
    )

    # ── Encodage JPEG base64 ──────────────────────────────────────────────────
    frames_b64: list[str] = []
    for i, f in enumerate(frames_rgb):
        try:
            if f.ndim == 2:
                img = Image.fromarray(f, mode="L").convert("RGB")
            elif f.ndim == 3 and f.shape[2] == 4:
                img = Image.fromarray(f.astype(np.uint8), mode="RGBA").convert("RGB")
            else:
                img = Image.fromarray(f.astype(np.uint8), mode="RGB")

            # Réduction si trop grand
            w, h = img.size
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                                 Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            frames_b64.append(base64.b64encode(buf.getvalue()).decode("ascii"))
        except Exception as frame_exc:
            sys.stderr.write(f"GO_PRINT|warning|frame {i} encode echoue ({frame_exc}), frame noire substituee\n")
            sys.stderr.flush()
            h_px = int(f.shape[0]) if f.ndim >= 1 else 64
            w_px = int(f.shape[1]) if f.ndim >= 2 else 64
            black = Image.new("RGB", (min(w_px, max_dim), min(h_px, max_dim)), (0, 0, 0))
            buf = BytesIO()
            black.save(buf, format="JPEG", quality=quality)
            frames_b64.append(base64.b64encode(buf.getvalue()).decode("ascii"))

    return {
        "file_name":          os.path.basename(dicom_path),
        "frame_count":        len(frames_rgb),
        "rows":               int(getattr(ds, "Rows",    frames_rgb[0].shape[0])),
        "cols":               int(getattr(ds, "Columns", frames_rgb[0].shape[1])),
        "modality":           str(getattr(ds, "Modality", "N/A")),
        "pixel_spacing":      pixel_spacing,
        "base_fps":           base_fps,
        "original_sensitive": original_sensitive,
        "kept_metadata":      kept_metadata,
        "patient_name":       patient_name,
        "study_date":         study_date,
        "frames_b64":         frames_b64,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load a DICOM file and output frames as JPEG base64 JSON."
    )
    parser.add_argument("dicom_path",      help="Chemin vers le fichier DICOM")
    parser.add_argument("--quality",  type=int, default=70,  help="Qualité JPEG (1-95)")
    parser.add_argument("--max-dim",  type=int, default=640, help="Dimension max d'une frame")
    args = parser.parse_args()

    # Redirige tous les go_print() vers stderr so que stdout ne contient que le JSON final.
    # Le serveur Go capture stderr séparément (cmd.Stderr) et retourne l'erreur si exit ≠ 0.
    from starhe_plugin.utils.go_print import set_log_sink
    set_log_sink(lambda level, msg: sys.stderr.write(f"GO_PRINT|{level}|{msg}\n") or sys.stderr.flush())

    if not os.path.isfile(args.dicom_path):
        print(json.dumps({"error": f"Fichier introuvable : {args.dicom_path}"}),
              flush=True)
        sys.exit(1)

    try:
        result = load_and_encode(args.dicom_path, args.quality, args.max_dim)
        print(json.dumps(result), flush=True)
    except Exception as exc:
        tb = traceback.format_exc()
        sys.stderr.write(f"GO_PRINT|error|loader_cli crash: {str(exc)}\n")
        sys.stderr.write(tb + "\n")
        sys.stderr.flush()
        print(json.dumps({
            "error":     str(exc),
            "traceback": tb,
        }), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
