#!/usr/bin/env python3
"""
test_dicom_pipeline.py
======================
Pipeline complet :
    DICOM → export PNG → ffmpeg MP4 → prepUS → STARHE (RISK + DETECT)

Moteur d'export PNG (par priorité) :
  1. weasis-dicom-tools (Java) — applique Modality LUT + VOI LUT comme Weasis.
     Supporte : RLE Lossless, JPEG Lossless, JPEG Baseline.
     (Échec JPEG 2000 connu → fallback automatique vers pydicom)
  2. pydicom (Python) — fallback. Supporte tous les formats via pylibjpeg.

Utilisation :
    python test_dicom_pipeline.py /chemin/vers/fichier.dcm
    python test_dicom_pipeline.py /chemin/vers/fichier.dcm --no-detect
    python test_dicom_pipeline.py /chemin/vers/fichier.dcm --keep-pngs /tmp/debug
    python test_dicom_pipeline.py /chemin/vers/fichier.dcm --no-weasis
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import cv2
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR  = os.path.join(ROOT, "pythonCode", "modules")
PREPUS_PATH = os.path.join(ROOT, "third_party", "prepUS")

# ── Weasis dcm2png CLI ────────────────────────────────────────────────────────
_WEASIS_DIR        = os.path.join(ROOT, "third_party", "weasis-dcm2png")
WEASIS_JAR         = os.path.join(_WEASIS_DIR, "dist", "weasis-dcm2png.jar")
WEASIS_NATIVE_DIR  = os.path.join(_WEASIS_DIR, "dist", "native")

sys.path.insert(0, PLUGIN_DIR)
if PREPUS_PATH not in sys.path:
    sys.path.insert(0, PREPUS_PATH)


# ══════════════════════════════════════════════════════════════════════════════
# 0. Weasis availability check + export
# ══════════════════════════════════════════════════════════════════════════════

def weasis_available() -> bool:
    """True si le JAR weasis-dcm2png est buildé et que java est dans le PATH."""
    return os.path.exists(WEASIS_JAR) and shutil.which("java") is not None


def export_dicom_to_pngs_weasis(dicom_path: str, out_dir: str) -> tuple:
    """
    Exporte les frames DICOM via weasis-dicom-tools (Java).
    Applique Modality LUT + VOI LUT exactement comme Weasis.
    Retourne (fps, n_frames).
    Lève RuntimeError si le JAR retourne un code non-nul.
    """
    cmd = [
        "java",
        f"-Djava.library.path={WEASIS_NATIVE_DIR}",
        "--enable-native-access=ALL-UNNAMED",
        "-jar", WEASIS_JAR,
        dicom_path,
        out_dir,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Extraire le message d'erreur pertinent (ignorer les warnings SLF4J)
        err_lines = [l for l in result.stderr.splitlines()
                     if "SLF4J" not in l and l.strip()]
        raise RuntimeError(
            f"weasis-dcm2png exit {result.returncode}\n" +
            "\n".join(err_lines[:5])
        )

    fps = 22.0
    n_frames = 0
    for line in result.stdout.splitlines():
        if line.startswith("fps="):
            fps = float(line[4:])
        elif line.startswith("frames="):
            n_frames = int(line[7:])

    ft_ms = round(1000.0 / fps, 3) if fps > 0 else 0
    print(f"    FrameTime≈{ft_ms} ms  →  FPS = {fps:.2f}  ({n_frames} frames)")
    return fps, n_frames


# ══════════════════════════════════════════════════════════════════════════════
# 1. FPS depuis les métadonnées DICOM
# ══════════════════════════════════════════════════════════════════════════════

def read_dicom_fps(ds) -> float:
    """
    Lit le FPS depuis les tags DICOM (de meilleur au pire) :
      1. FrameTime  (0018,1063) — ms par frame → fps = 1000/ft
      2. CineRate   (0018,0040) — fps direct
      3. Fallback   22 fps
    """
    ft = getattr(ds, "FrameTime", None)
    if ft is not None:
        ft = float(ft)
        if ft > 0:
            return round(1000.0 / ft, 3)

    cr = getattr(ds, "CineRate", None)
    if cr is not None:
        cr = float(cr)
        if cr > 0:
            return cr

    return 22.0


# ══════════════════════════════════════════════════════════════════════════════
# 2. Export DICOM → PNG
# ══════════════════════════════════════════════════════════════════════════════

def _decode_frames_encapsulated(ds) -> np.ndarray:
    """
    Fallback frame-par-frame pour les DICOM encapsulés dont certaines frames
    sont vides (length=0).  Utilise pylibjpeg-openjpeg pour JPEG 2000.
    Les frames vides sont remplacées par la frame précédente (ou noir).
    """
    from pydicom.encaps import generate_pixel_data_frame
    from pydicom.uid import JPEG2000Lossless, JPEG2000
    from openjpeg.utils import decode_pixel_data as opj_decode

    ts = ds.file_meta.TransferSyntaxUID
    n  = int(getattr(ds, "NumberOfFrames", 1))
    h, w = ds.Rows, ds.Columns
    spp  = getattr(ds, "SamplesPerPixel", 1)

    raw_frames = list(generate_pixel_data_frame(ds.PixelData, n))
    print(f"    [fallback] {sum(1 for f in raw_frames if len(f)==0)} frame(s) vide(s) sur {n}")

    decoded: list[np.ndarray] = []
    prev: np.ndarray | None = None

    for i, raw in enumerate(raw_frames):
        if len(raw) == 0:
            # Frame vide : réutiliser la précédente ou créer un noir
            if prev is not None:
                decoded.append(prev.copy())
            else:
                shape = (h, w, spp) if spp > 1 else (h, w)
                decoded.append(np.zeros(shape, dtype=np.uint8))
            continue

        if ts in (JPEG2000Lossless, JPEG2000):
            arr = np.frombuffer(
                opj_decode(raw, ds=None, version=2),
                dtype=np.uint8 if ds.BitsAllocated == 8 else np.uint16,
            )
        else:
            # Autres syntaxes encapsulées — laisser pydicom gérer frame unique
            import pydicom
            import io
            single = pydicom.dcmread(
                io.BytesIO(raw), force=True,
                specific_tags=None,
            )
            arr = single.pixel_array if hasattr(single, "pixel_array") else np.frombuffer(raw, dtype=np.uint8)

        # Reshape selon la géométrie du DICOM
        if spp > 1:
            arr = arr.reshape(h, w, spp)
        else:
            arr = arr.reshape(h, w)
        decoded.append(arr)
        prev = arr

    return np.stack(decoded)  # (T, H, W) ou (T, H, W, C)


def export_dicom_to_pngs(dicom_path: str, out_dir: str) -> tuple:
    """
    Lit le DICOM avec pydicom et enregistre chaque frame en PNG uint8.

    Gestion des cas courants pour les échographies :
    - 8 bits (BitsAllocated=8)  : export direct
    - 10/12/16 bits             : normalisation linéaire vers 0-255
                                  (optionnellement via WindowCenter/Width si présent)
    - Photométrie YBR_FULL_422  : pydicom convertit en RGB automatiquement
    - Monochrome                : sauvé en niveaux de gris
    - Couleur (RGB / YBR)       : sauvé en RGB

    Retourne (fps, n_frames)
    """
    import pydicom
    from PIL import Image

    print(f"    Lecture DICOM : {os.path.basename(dicom_path)}")
    ds = pydicom.dcmread(dicom_path, force=True)

    fps = read_dicom_fps(ds)
    ft  = getattr(ds, "FrameTime", None)
    print(f"    FrameTime={ft} ms  →  FPS = {fps:.2f}")

    # ── Pixel array ───────────────────────────────────────────────────────────
    try:
        pixels = ds.pixel_array  # (T, H, W) | (T, H, W, 3) | (H, W) | (H, W, 3)
    except RuntimeError:
        # Fallback pour les fichiers encapsulés avec frames vides (ex. JPEG 2000
        # dont certaines frames ont length=0 dans le Basic Offset Table).
        pixels = _decode_frames_encapsulated(ds)

    # ── Normalisation bit-depth ───────────────────────────────────────────────
    if pixels.dtype != np.uint8:
        wc = getattr(ds, "WindowCenter", None)
        ww = getattr(ds, "WindowWidth",  None)
        if wc is not None and ww is not None:
            wc = float(wc) if not hasattr(wc, "__iter__") else float(wc[0])
            ww = float(ww) if not hasattr(ww, "__iter__") else float(ww[0])
            lo, hi = wc - ww / 2.0, wc + ww / 2.0
            pixels = np.clip(pixels.astype(np.float32), lo, hi)
            pixels = ((pixels - lo) / ww * 255.0).astype(np.uint8)
        else:
            pmin, pmax = int(pixels.min()), int(pixels.max())
            if pmax > pmin:
                pixels = ((pixels.astype(np.float32) - pmin) /
                          (pmax - pmin) * 255.0).astype(np.uint8)
            else:
                pixels = np.zeros_like(pixels, dtype=np.uint8)

    # ── Mise en forme : toujours (T, H, W[, C]) ──────────────────────────────
    if pixels.ndim == 2:
        pixels = pixels[np.newaxis]           # mono-frame grayscale → (1, H, W)
    elif pixels.ndim == 3 and pixels.shape[2] in (3, 4):
        pixels = pixels[np.newaxis]           # mono-frame color    → (1, H, W, C)
    # else: déjà (T, H, W) ou (T, H, W, C)

    n = pixels.shape[0]

    # ── Sauvegarde PNG ────────────────────────────────────────────────────────
    for i, frame in enumerate(pixels):
        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[..., :3]          # drop alpha
        img = Image.fromarray(frame)
        img.save(os.path.join(out_dir, f"{i:05d}.png"))

    print(f"    {n} frames exportés → {out_dir}")
    return fps, n


# ══════════════════════════════════════════════════════════════════════════════
# 3. ffmpeg : PNG → MP4
# ══════════════════════════════════════════════════════════════════════════════

def pngs_to_mp4(png_dir: str, fps: float, out_mp4: str) -> None:
    """
    Reconstruit un MP4 (codec mpeg4, qualité max) depuis les PNG du dossier.
    Utilise -pattern_type glob pour gérer les trous de numérotation éventuels.
    """
    cmd = [
        "ffmpeg", "-y",
        "-r", str(fps),
        "-pattern_type", "glob",
        "-i", os.path.join(png_dir, "*.png"),
        "-c:v", "mpeg4",
        "-qscale:v", "1",
        out_mp4,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg a échoué :\n{r.stderr}")
    # Compte les frames encodées depuis stderr
    for line in r.stderr.splitlines():
        if "frame=" in line:
            print(f"    ffmpeg : {line.strip()}")
            break
    print(f"    MP4 → {out_mp4}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. prepUS
# ══════════════════════════════════════════════════════════════════════════════

def run_prepus(mp4_path: str, out_dir: str) -> tuple:
    """
    Appelle prepUS.removeLayoutFile et retourne (crop_frames, info).
    crop_frames : (T, H_crop, W_crop) uint8 grayscale — video.mp4
    """
    from prepUS.cli import removeLayoutFile  # type: ignore[import]

    removeLayoutFile(
        input_file=mp4_path,
        output_dir=out_dir,
        thresh=-1,
        back_scan_conversion=True,   # nécessaire pour produire video.mp4
        backscan_width=512,
        backscan_height=512,
        save_mask=False,
        save_cropped_mask=False,
        save_info=True,
    )

    info: dict | None = None
    info_path = os.path.join(out_dir, "info.json")
    if os.path.exists(info_path):
        with open(info_path, encoding="utf-8") as fh:
            info = json.load(fh)

    video_mp4 = os.path.join(out_dir, "video.mp4")
    if not os.path.exists(video_mp4):
        raise RuntimeError(f"prepUS n'a pas produit video.mp4 dans {out_dir}")

    cap = cv2.VideoCapture(video_mp4)
    buf = []
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        buf.append(cv2.cvtColor(frm, cv2.COLOR_BGR2GRAY))
    cap.release()

    if not buf:
        raise RuntimeError("video.mp4 est vide")

    return np.stack(buf), info          # (T, H_crop, W_crop), dict|None


# ══════════════════════════════════════════════════════════════════════════════
# 5. STARHE RISK
# ══════════════════════════════════════════════════════════════════════════════

def run_risk(crop_frames: np.ndarray) -> dict:
    from starhe_plugin.ai.starhe_risk import STARHERiskModel
    model  = STARHERiskModel()
    c      = crop_frames                               # (T, H_c, W_c)
    rgb    = np.stack([c, c, c], axis=-1)              # (T, H_c, W_c, 3) pseudo-RGB
    return model.predict(rgb)


# ══════════════════════════════════════════════════════════════════════════════
# 6. STARHE DETECT
# ══════════════════════════════════════════════════════════════════════════════

def run_detect(crop_frames: np.ndarray, info: dict | None) -> list:
    from starhe_plugin.ai.starhe_detect import STARHEDetectModel as STARHEDetect
    from starhe_plugin.dicom.prepus_bridge import map_detections_to_dicom_coords
    from starhe_plugin.config import DETECT_EVERY_N

    c   = crop_frames                                  # (T, H_c, W_c)
    rgb = np.stack([c, c, c], axis=-1)                 # (T, H_c, W_c, 3)

    # Sous-échantillonnage temporel identique à pipeline.py (DETECT_EVERY_N=4)
    indices = list(range(0, len(rgb), DETECT_EVERY_N))
    sampled = rgb[indices]
    print(f"    Détection sur {len(sampled)}/{len(rgb)} frames (stride={DETECT_EVERY_N})")

    detector = STARHEDetect()  # = STARHEDetectModel
    # predict_batch attend list[(H,W,3)] — pas un array 4D
    dets_sampled = detector.predict_batch(list(sampled))  # list[list[dict]]

    # Réexpansion : chaque frame non-analysée reçoit les détections de la frame
    # précédente (même comportement que pipeline.py)
    dets = [[] for _ in range(len(rgb))]
    for pos, idx in enumerate(indices):
        dets[idx] = dets_sampled[pos]

    # Remappage crop → coordonnées DICOM originales
    dets = map_detections_to_dicom_coords(dets, info)
    return dets


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline DICOM → PNG → MP4 → prepUS → STARHE"
    )
    parser.add_argument("dicom_path", help="Chemin vers le fichier DICOM (.dcm ou sans extension)")
    parser.add_argument("--no-detect", action="store_true", help="Sauter STARHE-DETECT (RTMDet)")
    parser.add_argument("--keep-pngs", metavar="DIR",
                        help="Conserver les PNG exportés dans ce répertoire (debug)")
    parser.add_argument("--no-weasis", action="store_true",
                        help="Forcer pydicom même si weasis-dcm2png est disponible")
    args = parser.parse_args()

    if not os.path.exists(args.dicom_path):
        print(f"[ERR] Fichier introuvable : {args.dicom_path}")
        sys.exit(1)

    work = tempfile.mkdtemp(prefix="starhe_dcm_")
    png_dir    = os.path.join(work, "pngs")
    prepus_out = os.path.join(work, "prepus")
    os.makedirs(png_dir)

    try:
        # ── 1. Export DICOM → PNG ─────────────────────────────────────────────
        print("\n[1] Export DICOM → PNG")
        used_weasis = False
        if not args.no_weasis and weasis_available():
            print("    Moteur : weasis-dicom-tools (LUT Modality + VOI appliquées)")
            try:
                fps, n_frames = export_dicom_to_pngs_weasis(args.dicom_path, png_dir)
                used_weasis = True
            except RuntimeError as e:
                print(f"    ⚠  weasis a échoué ({e.args[0].splitlines()[0]})")
                print("    Fallback → pydicom")
                shutil.rmtree(png_dir)
                os.makedirs(png_dir)
                fps, n_frames = export_dicom_to_pngs(args.dicom_path, png_dir)
        else:
            if not args.no_weasis:
                print("    Moteur : pydicom (JAR weasis-dcm2png absent — "
                      "buildez avec: cd third_party/weasis-dcm2png && mvn package)")
            fps, n_frames = export_dicom_to_pngs(args.dicom_path, png_dir)

        # Copie éventuelle pour debug
        if args.keep_pngs:
            os.makedirs(args.keep_pngs, exist_ok=True)
            for f in os.listdir(png_dir):
                shutil.copy(os.path.join(png_dir, f), args.keep_pngs)
            print(f"    PNG conservés dans : {args.keep_pngs}")

        # ── 2. ffmpeg PNG → MP4 ──────────────────────────────────────────────
        print("\n[2] Reconstruction MP4 (ffmpeg)")
        mp4_path = os.path.join(work, "input.mp4")
        pngs_to_mp4(png_dir, fps, mp4_path)

        # ── 3. prepUS ────────────────────────────────────────────────────────
        print("\n[3] prepUS (removeLayoutFile)")
        crop_frames, info = run_prepus(mp4_path, prepus_out)
        roi = info.get("crop") if info else "N/A"
        print(f"    crop shape : {crop_frames.shape}  |  ROI : {roi}")

        # ── 4. STARHE RISK ───────────────────────────────────────────────────
        print("\n[4] STARHE-RISK (C3D)")
        risk_result = run_risk(crop_frames)
        score = risk_result.get("risk_score", float("nan"))
        label = risk_result.get("risk_label", "?")
        scores = risk_result.get("scores", [])

        # ── 5. STARHE DETECT (optionnel) ─────────────────────────────────────
        detections = None
        if not args.no_detect:
            print("\n[5] STARHE-DETECT (RTMDet)")
            detections = run_detect(crop_frames, info)
            n_det_frames = sum(1 for fd in detections if fd)
            print(f"    Frames avec détections : {n_det_frames} / {len(detections)}")

        # ── Résultats ────────────────────────────────────────────────────────
        print()
        print("=" * 52)
        print(f"  FICHIER        : {os.path.basename(args.dicom_path)}")
        print(f"  MOTEUR PNG     : {'weasis-dicom-tools' if used_weasis else 'pydicom'}")
        print(f"  FRAMES         : {n_frames}  |  FPS : {fps:.2f}")
        print(f"  CROP           : {crop_frames.shape}")
        print(f"  RISK SCORE     : {score:.4f}")
        print(f"  LABEL          : {label}")
        print(f"  SCORES [lo,hi] : {[round(s, 4) for s in scores]}")
        if detections is not None:
            n_det = sum(len(fd) for fd in detections)
            print(f"  DÉTECTIONS     : {n_det} bbox(es) sur {n_det_frames} frame(s)")
        print("=" * 52)

    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
