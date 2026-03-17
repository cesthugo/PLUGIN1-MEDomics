"""
dicom/crop.py — Détection et suppression du cadre de l'échographe
==================================================================
Deux approches disponibles :

Approche spatiale (mono-frame) — detect_ultrasound_roi()
  1. Conversion gris → seuillage → ouverture morphologique (efface textes).
  2. Composante connexe centrale (= cône US), fermeture pour boucher les trous.
  3. Bounding-box du cône.

Approche temporelle (multi-frames) — detect_ultrasound_roi_temporal()  [préférable]
  Portée de prepUS (Guigui et al.) :
  1. Pour chaque pixel, compte le nombre de valeurs distinctes sur T frames.
     Pixels statiques (UI, texte, règles) ≈ peu de valeurs.
     Pixels dynamiques (cône US) ≈ beaucoup de valeurs.
  2. Seuillage → masque binaire → plus grande CC → symétrie → remplissage trous.
  3. Bounding-box du masque résultant.
  crop_clip() utilise automatiquement l'approche temporelle quand T > 1.
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


# ─── Helpers pour l'approche temporelle (portés de prepUS – Guigui et al.) ───

def _keep_largest_component(binary_img: np.ndarray) -> np.ndarray:
    """Conserve uniquement la plus grande composante connexe (fond exclu)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary_img, connectivity=8)
    if n <= 1:
        return binary_img
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    out = np.zeros_like(binary_img)
    out[labels == best] = 255
    return out


def _sync_halves(binary_img: np.ndarray) -> np.ndarray:
    """Symétrise gauche/droite : un pixel actif d'un côté active son symétrique."""
    h, w = binary_img.shape
    left  = binary_img[:, : w // 2].copy()
    right = binary_img[:, w // 2 :].copy()
    left[np.fliplr(right) == 255]  = 255
    right[np.fliplr(left)  == 255] = 255
    return np.concatenate((left, right), axis=1)


def detect_ultrasound_roi_temporal(
    frames: np.ndarray,
    thresh: float = -1.0,
) -> tuple[int, int, int, int]:
    """
    Détecte la ROI échographique par comptage de valeurs uniques sur T frames.

    Algorithme (adapté de prepUS – Guigui et al.) :
      1. Pour chaque pixel, compte le nombre de niveaux de gris distincts
         sur l'ensemble du clip.  Les pixels UI/texte sont statiques (peu de
         valeurs uniques) ; les pixels du cône US sont dynamiques (beaucoup).
      2. Seuillage → plus grande composante connexe → symétrie gauche/droite
         → remplissage des trous → débruitage morphologique.
      3. Bounding-box du masque résultant.

    Paramètres :
      frames : np.ndarray  shape (T, H, W) ou (T, H, W, 3)
      thresh : ratio unique/T ; -1 = détection automatique (histogramme)

    Retourne :
      (x0, y0, x1, y1)
    """
    from scipy.ndimage import binary_fill_holes

    # ── 1. Conversion en niveaux de gris ─────────────────────────────────
    if frames.ndim == 4:
        gray = np.stack([
            cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            for f in frames
        ])
    else:
        gray = frames.astype(np.uint8)
    T, H, W = gray.shape

    # ── 2. Nombre de valeurs uniques par pixel (vectorisé) ───────────────
    sorted_g      = np.sort(gray, axis=0)                                # (T,H,W)
    unique_counts = (1 + np.count_nonzero(np.diff(sorted_g, axis=0), axis=0)).astype(np.float32)
    u_avg = unique_counts / T

    # ── 3. Seuil auto (bin 3 sur histogramme à 20 niveaux, comme prepUS) ─
    if thresh < 0:
        _, bin_edges = np.histogram(u_avg, bins=20)
        thresh = float(bin_edges[3])
    go_print("info", f"crop temporal: seuil unique_ratio={thresh:.4f}")

    # ── 4. Masque binaire → nettoyage → remplissage ──────────────────────
    mask = (u_avg > thresh).astype(np.uint8) * 255
    mask = _keep_largest_component(mask)
    mask = _sync_halves(mask)
    mask = (binary_fill_holes((mask / 255).astype(bool)) * 255).astype(np.uint8)
    k3   = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k3)

    # ── 5. Bounding-box ──────────────────────────────────────────────────
    y_coords, x_coords = np.nonzero(mask)
    if len(y_coords) == 0:
        go_print("warning", "crop temporal: aucun pixel dynamique — image entière retournée.")
        return 0, 0, W, H

    x0, x1 = int(x_coords.min()), int(x_coords.max()) + 1
    y0, y1 = int(y_coords.min()), int(y_coords.max()) + 1
    go_print("info", f"crop temporal: ROI → x0={x0} y0={y0} x1={x1} y1={y1} "
                     f"| couverture={(y1-y0)*(x1-x0)/(H*W):.1%}")
    return x0, y0, x1, y1


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

    Utilise l'analyse temporelle (pixels statiques vs. dynamiques) quand le
    clip contient plusieurs frames — nettement plus précise pour éliminer les
    annotations UI, textes et règles de l'échographe.
    Bascule sur l'analyse spatiale mono-frame pour un clip d'un seul frame.

    Paramètres :
      frames : np.ndarray  shape (T, H, W) ou (T, H, W, 3)

    Retourne :
      (frames_rognés, roi)
    """
    if len(frames) > 1:
        roi = detect_ultrasound_roi_temporal(frames)
    else:
        roi = detect_ultrasound_roi(frames[0])
    cropped = np.stack([crop_frame(f, roi)[0] for f in frames], axis=0)
    go_print("info", f"crop_clip : {len(frames)} frames rognés | ROI={roi}")
    return cropped, roi
