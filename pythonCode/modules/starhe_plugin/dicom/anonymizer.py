"""
dicom/anonymizer.py — Anonymisation des métadonnées DICOM
==========================================================
Suppression automatique des tags sensibles (identificateurs patient,
centre, médecin) à l'importation du fichier DICOM dans le plugin.

Référence : DICOM PS3.15 Annexe E — Attribute Confidentiality Profiles
"""

import pydicom
from starhe_plugin.config import DICOM_SENSITIVE_TAGS
from starhe_plugin.utils.go_print import go_print


def anonymize(ds: pydicom.dataset.FileDataset) -> pydicom.dataset.FileDataset:
    """
    Supprime les tags sensibles du dataset DICOM (en place).

    Appelé automatiquement à chaque import de fichier DICOM.
    Aucune valeur n'est conservée ni hachée : suppression totale.

    Retourne le dataset modifié.
    """
    removed = 0
    for tag in DICOM_SENSITIVE_TAGS:
        if tag in ds:
            del ds[tag]
            removed += 1

    go_print("info", f"anonymizer : {removed} tag(s) supprimé(s).")
    return ds
