"""
dicom/reader.py — Lecture et extraction de fichiers DICOM
==========================================================
Fournit :
  - load_dicom()        : charge un fichier .dcm et retourne le dataset pydicom
  - extract_frames()    : extrait tous les frames pixel en array numpy (T x H x W x C)
  - is_cine_clip()      : détecte si le fichier contient plusieurs frames (ciné-clip)
  - frame_to_uint8()    : normalise un frame en image 8 bits affichable
"""

import numpy as np
import pydicom
from pydicom.errors import InvalidDicomError
from starhe_plugin.utils.go_print import go_print


def load_dicom(path: str) -> pydicom.dataset.FileDataset:
    """
    Charge un fichier DICOM depuis le chemin donné.
    Retourne le dataset pydicom ou lève une exception explicite.
    """
    try:
        ds = pydicom.dcmread(path, force=True)
        go_print("info", f"DICOM chargé : {path} | SOPClassUID={getattr(ds, 'SOPClassUID', 'N/A')}")
        return ds
    except InvalidDicomError as e:
        go_print("error", f"Fichier non DICOM valide : {path} — {e}")
        raise
    except FileNotFoundError:
        go_print("error", f"Fichier introuvable : {path}")
        raise


def is_cine_clip(ds: pydicom.dataset.FileDataset) -> bool:
    """
    Retourne True si le DICOM contient plusieurs frames (ciné-clip).
    Critères : NumberOfFrames > 1 ou pixel_array de rang 4.
    """
    n_frames = int(getattr(ds, "NumberOfFrames", 1))
    return n_frames > 1


def _pixel_array_to_tchw(pixel_array: np.ndarray) -> np.ndarray:
    """Normalise un pixel_array brut en (T, H, W) ou (T, H, W, 3)."""
    if pixel_array.ndim == 2:
        return pixel_array[np.newaxis, ...]          # (1, H, W)
    if pixel_array.ndim == 3:
        if pixel_array.shape[2] == 3:
            return pixel_array[np.newaxis, ...]      # (1, H, W, 3) — mono RGB
        return pixel_array                           # (T, H, W)
    return pixel_array                               # (T, H, W, 3) déjà correct


def _extract_j2k_raw_scan(ds: pydicom.dataset.FileDataset) -> np.ndarray:
    """
    Fallback robuste pour les fichiers JPEG 2000 dont pydicom ne parse pas
    correctement la table des offsets (BOT vide, EOT, encapsulation non standard).

    Stratégie : scanner les bytes bruts de PixelData à la recherche du marqueur
    J2K SOC+SIZ (FF 4F FF 51) et décoder chaque codestream avec openjpeg
    directement, en contournant entièrement la logique d'extraction de pydicom.
    """
    from openjpeg import decode as j2k_decode
    from io import BytesIO

    raw = bytes(ds.PixelData)
    n_expected = int(getattr(ds, "NumberOfFrames", 1))
    ts = str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", "?"))

    # Le SOC (Start of Codestream) est TOUJOURS suivi du marqueur SIZ (FF 51)
    # dans tout codestream J2K valide — signature à 4 octets unique et fiable.
    SOC_SIZ = b"\xff\x4f\xff\x51"

    starts: list[int] = []
    idx = 0
    while True:
        pos = raw.find(SOC_SIZ, idx)
        if pos == -1:
            break
        starts.append(pos)
        idx = pos + 4

    if not starts:
        raise ValueError(
            f"Aucun marqueur J2K SOC+SIZ trouvé dans {len(raw)} octets de PixelData "
            f"(TS={ts}). Le fichier n'est peut-être pas JPEG 2000."
        )

    go_print("info",
             f"J2K raw scan : {len(starts)} codestream(s) trouvé(s) "
             f"sur {n_expected} frame(s) attendue(s)")

    frames = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(raw)
        frame_bytes = raw[start:end]
        arr = j2k_decode(BytesIO(frame_bytes))
        frames.append(arr)

    return _pixel_array_to_tchw(np.stack(frames))


def extract_frames(ds: pydicom.dataset.FileDataset) -> np.ndarray:
    """
    Extrait les données pixel du DICOM en array numpy.

    Retourne :
      - Array de shape (T, H, W)   si niveaux-de-gris
      - Array de shape (T, H, W, 3) si RGB

    Les frames sont normalisées en uint16 natif ; utiliser
    frame_to_uint8() pour obtenir un affichage 8 bits.

    Chaîne de fallbacks (du plus rapide au plus robuste) :
      1. ds.pixel_array          — pydicom + handlers installés
      2. ds.decompress()         — pydicom 3.x : convertit en non-compressé
      3. _extract_j2k_raw_scan() — scan brut des bytes pour marqueurs J2K SOC+SIZ
    """
    ts = str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", "absent"))
    pi = str(getattr(ds, "PhotometricInterpretation", "?"))
    go_print("info", f"extract_frames : TS={ts} | PhotometricInterp={pi}")

    # ── 1. Lecture directe (cas nominal) ─────────────────────────────────────
    errors: list[str] = []
    try:
        pixel_array = ds.pixel_array
        return _pixel_array_to_tchw(pixel_array)
    except Exception as e1:
        errors.append(f"pixel_array: {e1}")
        go_print("warning", f"pixel_array direct échoué ({e1}), tentatives fallback…")

    # ── 2. ds.decompress() (pydicom 3.x) puis relecture ──────────────────────
    try:
        ds.decompress()
        pixel_array = ds.pixel_array
        go_print("info", "Décompression pydicom réussie.")
        return _pixel_array_to_tchw(pixel_array)
    except AttributeError:
        pass  # pydicom < 3.x, méthode absente — passer au fallback suivant
    except Exception as e2:
        errors.append(f"decompress: {e2}")
        go_print("warning", f"decompress() échoué ({e2})")

    # ── 3. Scan brut des bytes J2K SOC+SIZ dans PixelData ────────────────────
    try:
        return _extract_j2k_raw_scan(ds)
    except Exception as e3:
        errors.append(f"j2k_scan: {e3}")
        go_print("warning", f"J2K raw scan échoué ({e3})")

    # ── Toutes les tentatives ont échoué ─────────────────────────────────────
    raise RuntimeError(
        f"Impossible de décoder les données pixel de ce fichier DICOM. "
        f"TransferSyntax={ts}, PhotometricInterp={pi}, "
        f"Frames={getattr(ds, 'NumberOfFrames', 1)}. "
        f"Erreurs: {' | '.join(errors)}"
    )


def frame_to_uint8(frame: np.ndarray) -> np.ndarray:
    """
    Normalise un frame (uint8, uint16…) vers l'intervalle [0, 255] uint8.
    Gère les images en niveaux de gris et RGB.
    """
    f = frame.astype(np.float32)
    f_min, f_max = f.min(), f.max()
    if f_max > f_min:
        f = (f - f_min) / (f_max - f_min) * 255.0
    return f.astype(np.uint8)
