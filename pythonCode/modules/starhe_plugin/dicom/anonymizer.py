"""
dicom/anonymizer.py — Anonymisation des métadonnées DICOM
==========================================================
Deux modes :
  - "hash"   : remplace la valeur par son SHA-256 tronqué (traçabilité interne)
  - "remove" : supprime complètement le tag

Référence : DICOM PS3.15 Annexe E — Attribute Confidentiality Profiles
"""

import hashlib
import pydicom
from starhe_plugin.config import DICOM_SENSITIVE_TAGS
from starhe_plugin.utils.go_print import go_print


def _hash_value(value: str) -> str:
    """Retourne les 16 premiers caractères du SHA-256 de la valeur."""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


def anonymize(ds: pydicom.dataset.FileDataset,
              mode: str = "hash") -> pydicom.dataset.FileDataset:
    """
    Anonymise les tags sensibles d'un dataset DICOM.

    Paramètres :
      ds   : dataset pydicom à modifier (en place)
      mode : "hash"   → remplace par SHA-256 tronqué
             "remove" → supprime le tag

    Retourne :
      Le dataset modifié.
    """
    if mode not in ("hash", "remove"):
        raise ValueError(f"Mode invalide : '{mode}'. Utiliser 'hash' ou 'remove'.")

    processed = 0
    for tag in DICOM_SENSITIVE_TAGS:
        group, element = tag
        if tag in ds:
            original = str(ds[tag].value)
            if mode == "hash":
                ds[tag].value = _hash_value(original)
            else:
                del ds[tag]
            processed += 1

    go_print("info", f"anonymizer : {processed} tag(s) traité(s) en mode '{mode}'.")
    return ds


def anonymize_file(input_path: str,
                   output_path: str,
                   mode: str = "hash") -> str:
    """
    Charge, anonymise et sauvegarde un fichier DICOM.

    Paramètres :
      input_path  : chemin du .dcm source
      output_path : chemin du .dcm de sortie
      mode        : "hash" ou "remove"

    Retourne :
      output_path
    """
    ds = pydicom.dcmread(input_path, force=False)
    ds = anonymize(ds, mode=mode)
    ds.save_as(output_path)
    go_print("info", f"anonymizer : fichier anonymisé sauvegardé → {output_path}")
    return output_path
