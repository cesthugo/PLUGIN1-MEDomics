"""
dicom/crop.py — Detection and removal of the ultrasound machine frame
==================================================================
Two available approaches:

Spatial approach (single-frame) — detect_ultrasound_roi()
  1. Grayscale conversion → thresholding → morphological opening (erases text).
  2. Central connected component (= US cone), closing to fill the holes.
  3. Bounding box of the cone.

Temporal approach (multi-frame) — detect_ultrasound_roi_temporal()  [preferred]
  Ported from prepUS (Guigui et al.):
  1. For each pixel, count the number of distinct values over T frames.
     Static pixels (UI, text, rulers) ≈ few values.
     Dynamic pixels (US cone) ≈ many values.
  2. Thresholding → binary mask → largest CC → symmetry → hole filling.
  3. Bounding box of the resulting mask.
  crop_clip() automatically uses the temporal approach when T > 1.
"""

import cv2
import numpy as np
from starhe_plugin.config import CROP_BLACK_THRESHOLD, CROP_MIN_CONTENT_RATIO
from starhe_plugin.utils.go_print import go_print


def _to_gray(frame: np.ndarray) -> np.ndarray:
    """Converts an RGB or grayscale frame into a gray uint8 image."""
    if frame.ndim == 3 and frame.shape[2] == 3:
        return cv2.cvtColor(frame.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    return frame.astype(np.uint8)


# ─── Helpers for the temporal approach (ported from prepUS – Guigui et al.) ──

def _keep_largest_component(binary_img: np.ndarray) -> np.ndarray:
    """Keeps only the largest connected component (background excluded)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary_img, connectivity=8)
    if n <= 1:
        return binary_img
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    out = np.zeros_like(binary_img)
    out[labels == best] = 255
    return out


def _sync_halves(binary_img: np.ndarray) -> np.ndarray:
    """Symmetrizes left/right: an active pixel on one side activates its mirror."""
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
    Detects the ultrasound ROI by counting unique values over T frames.

    Algorithm (adapted from prepUS – Guigui et al.):
      1. For each pixel, count the number of distinct gray levels
         over the whole clip.  UI/text pixels are static (few unique
         values); US cone pixels are dynamic (many).
      2. Thresholding → largest connected component → left/right symmetry
         → hole filling → morphological denoising.
      3. Bounding box of the resulting mask.

    Parameters:
      frames : np.ndarray  shape (T, H, W) or (T, H, W, 3)
      thresh : unique/T ratio; -1 = automatic detection (histogram)

    Returns:
      (x0, y0, x1, y1)
    """
    from scipy.ndimage import binary_fill_holes

    # ── 1. Grayscale conversion ──────────────────────────────────────────
    if frames.ndim == 4:
        gray = np.stack([
            cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            for f in frames
        ])
    else:
        gray = frames.astype(np.uint8)
    T, H, W = gray.shape

    # ── 2. Number of unique values per pixel (vectorized) ────────────────
    sorted_g      = np.sort(gray, axis=0)                                # (T,H,W)
    unique_counts = (1 + np.count_nonzero(np.diff(sorted_g, axis=0), axis=0)).astype(np.float32)
    u_avg = unique_counts / T

    # ── 3. Auto threshold (bin 3 on a 20-level histogram, like prepUS) ───
    if thresh < 0:
        _, bin_edges = np.histogram(u_avg, bins=20)
        thresh = float(bin_edges[3])
    go_print("info", f"crop temporal: seuil unique_ratio={thresh:.4f}")

    # ── 4. Binary mask → cleaning → filling ──────────────────────────────
    mask = (u_avg > thresh).astype(np.uint8) * 255
    mask = _keep_largest_component(mask)
    mask = _sync_halves(mask)
    mask = (binary_fill_holes((mask / 255).astype(bool)) * 255).astype(np.uint8)
    k3   = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k3)

    # ── 5. Bounding box ──────────────────────────────────────────────────
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
    Detects the region of interest (ROI) of the ultrasound cone in a frame.

    Parameters:
      frame : np.ndarray  — uint8 frame (H, W) or (H, W, 3)

    Returns:
      (x0, y0, x1, y1)  — bounding box coordinates [x0:x1, y0:y1]

    If no useful area is found, returns the whole image.
    """
    gray = _to_gray(frame)
    h, w = gray.shape

    # ── 1. Thresholding ──────────────────────────────────────────────────────
    _, binary = cv2.threshold(gray, CROP_BLACK_THRESHOLD, 255, cv2.THRESH_BINARY)

    # ── 2. Opening: erases text annotations and thin markers ──────────────────
    # (characters ~20-30 px on this type of ultrasound machine → 30 px kernel removes them)
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (30, 30))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)

    # ── 3. Central connected component BEFORE closing ─────────────────────────
    # First isolate the central blob (= cone) WITHOUT closing so that it
    # does not create bridges between the cone and peripheral annotations.
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary)

    if n_labels <= 1:
        go_print("warning", "crop.py : aucune région trouvée, image retournée en entier.")
        return 0, 0, w, h

    center_label = int(labels[h // 2, w // 2])
    if center_label == 0:
        # Center in the background — fallback: largest non-background component
        areas = stats[1:, cv2.CC_STAT_AREA]
        center_label = int(np.argmax(areas)) + 1
        go_print("warning", "crop.py : centre dans le fond, fallback sur la plus grande composante.")

    # ── 4. Closing on the isolated cone mask only ──────────────────────────────
    # Fills the cone's internal holes WITHOUT the risk of reconnecting
    # the annotations that were separated in the previous step.
    cone_mask = (labels == center_label).astype(np.uint8) * 255
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (40, 40))
    cone_filled  = cv2.morphologyEx(cone_mask, cv2.MORPH_CLOSE, kernel_close)

    # Final bounding box on the filled cone mask
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
    Crops a frame to the ROI coordinates.
    If roi is None, detects the ROI automatically.

    Returns:
      (cropped_frame, (x0, y0, x1, y1))
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
    Applies a consistent crop to ALL frames of a cine-clip.

    Uses the temporal analysis (static vs. dynamic pixels) when the
    clip contains multiple frames — markedly more accurate at removing
    UI annotations, text and rulers of the ultrasound machine.
    Falls back to the single-frame spatial analysis for a one-frame clip.

    Parameters:
      frames : np.ndarray  shape (T, H, W) or (T, H, W, 3)

    Returns:
      (cropped_frames, roi)
    """
    if len(frames) > 1:
        roi = detect_ultrasound_roi_temporal(frames)
    else:
        roi = detect_ultrasound_roi(frames[0])
    cropped = np.stack([crop_frame(f, roi)[0] for f in frames], axis=0)
    go_print("info", f"crop_clip : {len(frames)} frames rognés | ROI={roi}")
    return cropped, roi
