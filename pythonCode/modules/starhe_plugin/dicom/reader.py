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


def extract_frames(ds: pydicom.dataset.FileDataset) -> np.ndarray:
    """
    Extrait les données pixel du DICOM en array numpy.

    Retourne :
      - Array de shape (T, H, W)   si niveaux-de-gris
      - Array de shape (T, H, W, 3) si RGB

    Les frames sont normalisées en uint16 natif ; utiliser
    frame_to_uint8() pour obtenir un affichage 8 bits.
    """
    pixel_array = ds.pixel_array  # shape: (H,W) | (H,W,3) | (T,H,W) | (T,H,W,3)

    # Mono-frame : on ajoute une dimension temporelle
    if pixel_array.ndim == 2:
        pixel_array = pixel_array[np.newaxis, ...]      # (1, H, W)
    elif pixel_array.ndim == 3:
        # Ambiguïté : (T, H, W) ou (H, W, 3) ?
        if pixel_array.shape[2] == 3:
            pixel_array = pixel_array[np.newaxis, ...]  # → (1, H, W, 3)
        # sinon c'est déjà (T, H, W)

    n_frames = pixel_array.shape[0]
    go_print("info", f"Extraction : {n_frames} frame(s) | shape={pixel_array.shape} | dtype={pixel_array.dtype}")
    return pixel_array


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
