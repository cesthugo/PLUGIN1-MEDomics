"""
dicom/anonymizer.py — Anonymisation des métadonnées DICOM
==========================================================
Suppression automatique des tags sensibles (identificateurs patient,
centre, médecin) à l'importation du fichier DICOM dans le plugin.

Référence : DICOM PS3.15 Annexe E — Attribute Confidentiality Profiles
"""

import numpy as np
import pydicom
from starhe_plugin.config import DICOM_SENSITIVE_TAGS
from starhe_plugin.utils.go_print import go_print


def remove_pixel_burnin(frames: np.ndarray) -> np.ndarray:
    """
    Noircit le bandeau d'en-tête (burned-in PHI) présent en haut des frames.

    Algorithme :
      1. Sur le premier frame, calcule la luminosité moyenne par ligne.
      2. Parcourt les lignes depuis le haut : dès qu'une ligne non-noire
         est trouvée (bandeau coloré), on mémorise qu'on est « dans un bandeau ».
      3. La première ligne quasi-noire APRÈS le bandeau marque la fin de
         l'en-tête ; toutes les lignes 0..header_end sont mises à 0 dans
         chaque frame.

    Fonctionne pour les images RGB (T, H, W, 3) ou niveaux-de-gris (T, H, W).
    Retourne le tableau modifié en place.
    """
    if frames is None or len(frames) == 0:
        return frames

    first = frames[0]
    # Luminosité moyenne par pixel (moyenne des canaux pour RGB)
    gray = first.mean(axis=2).astype(float) if first.ndim == 3 else first.astype(float)
    h = gray.shape[0]

    _DARK_THRESH   = 15    # pixel < 15  → considéré noir/fond
    _DARK_ROW_FRAC = 0.90  # 90 % des pixels de la ligne doivent être sombres

    header_end   = 0
    saw_content  = False
    max_scan_row = min(h // 3, 300)  # limiter la recherche au tiers supérieur

    for row in range(max_scan_row):
        dark_frac = np.mean(gray[row] < _DARK_THRESH)
        if dark_frac < _DARK_ROW_FRAC:
            # Ligne non-noire : on est dans (ou avant) le bandeau
            saw_content = True
        elif saw_content:
            # Première ligne noire après contenu → fin du bandeau
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
    Anonymise les tags sensibles du dataset DICOM (en place).

    mode : "remove" — suppression totale (défaut)
           "hash"   — remplacement par SHA-256[:16] (traçabilité interne)

    Retourne le dataset modifié.
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
