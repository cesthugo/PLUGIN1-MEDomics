import cv2
import numpy as np
import rich
from rich.progress import Progress
from pathlib import Path
from sonocrop import vid
from scipy.ndimage import binary_fill_holes
from typing import Tuple


def savevideo_rgb(outFile, array, fps):
    f, height, width, c = array.shape
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(outFile), fourcc, fps, (width, height), True)
    for i in range(f):
        frame = array[i, ...].astype(np.uint8)
        out.write(frame)
    out.release()


def keep_largest_component(binary_image):
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_image, connectivity=8)
    largest_label = 1
    largest_area = stats[1, cv2.CC_STAT_AREA]
    for i in range(2, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > largest_area:
            largest_area = area
            largest_label = i
    largest_component = np.zeros_like(binary_image)
    largest_component[labels == largest_label] = 255
    return largest_component


def sync_halves(binary_image: np.ndarray, foreground_value: int = 255) -> np.ndarray:
    height, width = binary_image.shape
    left_half = binary_image[:, : width // 2]
    right_half = binary_image[:, width // 2 :]
    right_half_flipped = np.fliplr(right_half)
    left_half[np.where(right_half_flipped == foreground_value)] = foreground_value
    left_half_flipped = np.fliplr(left_half)
    right_half[np.where(left_half_flipped == foreground_value)] = foreground_value
    synced_image = np.concatenate((left_half, right_half), axis=1)
    return synced_image


def crop_single_object(bool_image: np.ndarray) -> Tuple[np.ndarray, int, int, int, int]:
    """
    Crops a single object from a boolean image.

    Returns
    -------
    (cropped_image, ymin, ymax+1, xmin, xmax+1)
    """
    y_coords, x_coords = np.nonzero(bool_image)
    xmin, xmax = np.min(x_coords), np.max(x_coords)
    ymin, ymax = np.min(y_coords), np.max(y_coords)
    cropped_image = bool_image[ymin: ymax + 1, xmin: xmax + 1]
    return (
        cropped_image,
        ymin,
        ymax + 1,
        xmin,
        xmax + 1,
    )
