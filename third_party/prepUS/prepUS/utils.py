import fire
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
        frame = array[i, ...].astype(np.uint8)  # Convert the frame data type to 8-bit unsigned integers
        out.write(frame)
    out.release()


def keep_largest_component(binary_image):
    # Label connected components in the binary image
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_image, connectivity=8)

    # Find the largest component (excluding the background)
    largest_label = 1
    largest_area = stats[1, cv2.CC_STAT_AREA]
    for i in range(2, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > largest_area:
            largest_area = area
            largest_label = i

    # Create a new binary image containing only the largest component
    largest_component = np.zeros_like(binary_image)
    largest_component[labels == largest_label] = 255

    return largest_component


def sync_halves(binary_image: np.ndarray, foreground_value: int = 255) -> np.ndarray:
    """
    Synchronizes two halves of a binary image by mirroring and aligning them.

    Parameters
    ----------
    binary_image : np.ndarray
        A 2D binary NumPy array representing the input image.

    Returns
    -------
    synced_image : np.ndarray
        A 2D binary NumPy array representing the synchronized image.

    """
    # Get the shape of the binary_image (height, width)
    height, width = binary_image.shape

    # Split the image in half along the width
    left_half = binary_image[:, : width // 2]
    right_half = binary_image[:, width // 2 :]

    # Flip the right half horizontally to align it with the left half
    right_half_flipped = np.fliplr(right_half)

    # Set a pixel to 1 in the left half if the corresponding symmetric pixel is foreground_value in the right half
    left_half[np.where(right_half_flipped == foreground_value)] = foreground_value

    # Flip the left half horizontally to align it with the right half
    left_half_flipped = np.fliplr(left_half)

    # Set a pixel to 1 in the right half if the corresponding symmetric pixel is foreground_value in the left half
    right_half[np.where(left_half_flipped == foreground_value)] = foreground_value

    # Combine the synchronized halves back into a single image
    synced_image = np.concatenate((left_half, right_half), axis=1)

    return synced_image


def crop_single_object(bool_image: np.ndarray) -> Tuple[np.ndarray, int, int, int, int]:
    """
    Crops a single object from a boolean image.

    Parameters
    ----------
    bool_image : np.ndarray
        A 2D boolean NumPy array representing the input image.
        The object to be cropped should be marked with True values,
        while the background should be marked with False values.

    Returns
    -------
    cropped_image : np.ndarray
        A 2D boolean NumPy array representing the cropped object.
    ymin : int
        The minimum y coordinate of the object in the input image.
    ymax_plus_1 : int
        The maximum y coordinate of the object in the input image, plus 1.
    xmin : int
        The minimum x coordinate of the object in the input image.
    xmax_plus_1 : int
        The maximum x coordinate of the object in the input image, plus 1.

    """
    # Find the non-zero elements' indices (i.e., the object's coordinates)
    y_coords, x_coords = np.nonzero(bool_image)

    # Determine the minimum and maximum x and y coordinates of the object
    xmin, xmax = np.min(x_coords), np.max(x_coords)
    ymin, ymax = np.min(y_coords), np.max(y_coords)

    # Crop the image using the calculated coordinates
    cropped_image = bool_image[ymin : ymax + 1, xmin : xmax + 1]

    return (
        cropped_image,
        ymin,
        ymax + 1,
        xmin,
        xmax + 1,
    )
