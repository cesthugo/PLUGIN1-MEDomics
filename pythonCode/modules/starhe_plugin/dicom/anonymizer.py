"""
dicom/anonymizer.py — DICOM metadata anonymization
==========================================================
Automatic removal of sensitive tags (patient, center, physician
identifiers) when importing the DICOM file into the plugin.

Reference: DICOM PS3.15 Annex E — Attribute Confidentiality Profiles
"""

import numpy as np
import pydicom
from starhe_plugin.config import DICOM_SENSITIVE_TAGS
from starhe_plugin.utils.go_print import go_print


def remove_pixel_burnin(frames: np.ndarray) -> np.ndarray:
    """
    Blacks out the header banner (burned-in PHI) present at the top of the frames.

    Algorithm:
      1. On the first frame, compute the mean brightness per row.
      2. Walk the rows from the top: as soon as a non-black row is
         found (colored banner), remember that we are "inside a banner".
      3. The first near-black row AFTER the banner marks the end of
         the header; all rows 0..header_end are set to 0 in
         every frame.

    Works for RGB (T, H, W, 3) or grayscale (T, H, W) images.
    Returns the array modified in place.
    """
    if frames is None or len(frames) == 0:
        return frames

    first = frames[0]
    # Mean brightness per pixel (channel average for RGB)
    gray = first.mean(axis=2).astype(float) if first.ndim == 3 else first.astype(float)
    h = gray.shape[0]

    _DARK_THRESH   = 15    # pixel < 15  → considered black/background
    _DARK_ROW_FRAC = 0.90  # 90% of the row's pixels must be dark

    header_end   = 0
    saw_content  = False
    max_scan_row = min(h // 3, 300)  # limit the search to the top third

    for row in range(max_scan_row):
        dark_frac = np.mean(gray[row] < _DARK_THRESH)
        if dark_frac < _DARK_ROW_FRAC:
            # Non-black row: we are inside (or before) the banner
            saw_content = True
        elif saw_content:
            # First black row after content → end of the banner
            header_end = row
            break

    if header_end > 0:
        frames[:, :header_end, ...] = 0
        go_print("info", f"remove_pixel_burnin : bandeau de {header_end} ligne(s) supprimé.")
    else:
        go_print("info", "remove_pixel_burnin : aucun bandeau détecté.")

    return frames


def anonymize(ds: pydicom.dataset.FileDataset,
              mode: str = "remove") -> pydicom.dataset.FileDataset:
    """
    Anonymizes the sensitive tags of the DICOM dataset (in place).

    mode : "remove" — full removal (default)
           "hash"   — replacement with SHA-256[:16] (internal traceability)

    Returns the modified dataset.
    """
    import hashlib
    removed = 0
    for tag in DICOM_SENSITIVE_TAGS:
        if tag in ds:
            if mode == "hash":
                original = str(ds[tag].value).encode("utf-8")
                ds[tag].value = hashlib.sha256(original).hexdigest()[:16]
            else:
                del ds[tag]
            removed += 1

    action = "hachés" if mode == "hash" else "supprimés"
    go_print("info", f"Anonymisation : {removed} tag(s) sensibles {action}.")
    return ds
