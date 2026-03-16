"""
dicom/crop.py — Détection et suppression du cadre de l'échographe
==================================================================
Algorithme :
  1. Conversion du frame en niveaux de gris.
  2. Seuillage binaire (pixels > CROP_BLACK_THRESHOLD → contenu utile).
  3. Recherche des contours ou calcul de la bounding-box englobant
     au moins CROP_MIN_CONTENT_RATIO de pixels actifs.
  4. Retourne les coordonnées (x0, y0, x1, y1) de la zone utile
     et l'image rognée.

Approche choisie : contour du plus grand blob via findContours +
erosion/dilatation pour ignorer les annotations fines (texte, échelle…).
"""

import cv2
import numpy as np
from starhe_plugin.config import CROP_BLACK_THRESHOLD, CROP_MIN_CONTENT_RATIO
from starhe_plugin.utils.go_print import go_print


def _to_gray(frame: np.ndarray) -> np.ndarray:
    """Convertit un frame RGB ou niveaux-de-gris en image uint8 grise."""
    if frame.ndim == 3 and frame.shape[2] == 3:
        return cv2.cvtColor(frame.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    return frame.astype(np.uint8)


def detect_ultrasound_roi(frame: np.ndarray) -> tuple[int, int, int, int]:
    """
    Détecte la région d'intérêt (ROI) du cône échographique dans un frame.

    Paramètres :
      frame : np.ndarray  — frame uint8 (H, W) ou (H, W, 3)

    Retourne :
      (x0, y0, x1, y1)  — coordonnées de la bounding-box [x0:x1, y0:y1]

    Si aucune zone utile n'est trouvée, retourne l'image entière.
    """
    gray = _to_gray(frame)
    h, w = gray.shape

    # ── 1. Seuillage ─────────────────────────────────────────────────────────
    _, binary = cv2.threshold(gray, CROP_BLACK_THRESHOLD, 255, cv2.THRESH_BINARY)

    # ── 2. Ouverture : efface les annotations textuelles et marqueurs fins ────
    # (caractères ~20-30 px sur ce type d'échographe → noyau 30 px les supprime)
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (30, 30))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)

    # ── 3. Composante connexe au centre AVANT fermeture ───────────────────────
    # On isole d'abord le blob central (= cône) SANS fermeture pour ne pas
    # qu'elle crée des ponts entre le cône et les annotations périphériques.
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary)

    if n_labels <= 1:
        go_print("warning", "crop.py : aucune région trouvée, image retournée en entier.")
        return 0, 0, w, h

    center_label = int(labels[h // 2, w // 2])
    if center_label == 0:
        # Centre dans le fond — fallback : plus grande composante non-fond
        areas = stats[1:, cv2.CC_STAT_AREA]
        center_label = int(np.argmax(areas)) + 1
        go_print("warning", "crop.py : centre dans le fond, fallback sur la plus grande composante.")

    # ── 4. Fermeture sur le masque isolé du cône uniquement ───────────────────
    # Remplit les trous internes du cône SANS risque de reconnecter
    # les annotations qui ont été séparées à l'étape précédente.
    cone_mask = (labels == center_label).astype(np.uint8) * 255
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (40, 40))
    cone_filled  = cv2.morphologyEx(cone_mask, cv2.MORPH_CLOSE, kernel_close)

    # Bounding box finale sur le masque de cône rempli
    contours_cone, _ = cv2.findContours(cone_filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours_cone:
        go_print("warning", "crop.py : échec du contour final, image complète conservée.")
        return 0, 0, w, h

    bx, by, bw, bh = cv2.boundingRect(contours_cone[0])
    x0, y0, x1, y1 = bx, by, bx + bw, by + bh

    area = int(stats[center_label, cv2.CC_STAT_AREA])
    go_print("info", f"crop.py : ROI détectée → x0={x0} y0={y0} x1={x1} y1={y1} "
                     f"| couverture={area/(h*w):.1%}")
    return x0, y0, x1, y1


def crop_frame(frame: np.ndarray,
               roi: tuple[int, int, int, int] | None = None) -> tuple[np.ndarray,
                                                                        tuple[int, int, int, int]]:
    """
    Rogne un frame aux coordonnées ROI.
    Si roi est None, détecte automatiquement la ROI.

    Retourne :
      (frame_rogné, (x0, y0, x1, y1))
    """
    if roi is None:
        roi = detect_ultrasound_roi(frame)
    x0, y0, x1, y1 = roi
    if frame.ndim == 3:
        cropped = frame[y0:y1, x0:x1, :]
    else:
        cropped = frame[y0:y1, x0:x1]
    return cropped, roi


def crop_clip(frames: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """
    Applique un crop cohérent à TOUS les frames d'un ciné-clip.

    Stratégie : calcule la ROI sur le frame médian (plus représentatif),
    puis applique la même ROI à tous les frames.

    Paramètres :
      frames : np.ndarray  shape (T, H, W) ou (T, H, W, 3)

    Retourne :
      (frames_rognés, roi)
    """
    mid = len(frames) // 2
    roi = detect_ultrasound_roi(frames[mid])
    cropped = np.stack([crop_frame(f, roi)[0] for f in frames], axis=0)
    go_print("info", f"crop_clip : {len(frames)} frames rognés | ROI={roi}")
    return cropped, roi
