"""
dicom/prepus_bridge.py — Integration of the prepUS.removeLayoutFile API
======================================================================
Reproduces exactly the reference pipeline (prepus/prepUS/cli.py):

    1. Encodes numpy frames → MP4 via ffmpeg (mpeg4 codec, -qscale:v 1).
       Fallback to cv2.VideoWriter(mp4v) if ffmpeg is absent from the PATH.
    2. Calls prepUS.cli.removeLayoutFile (back_scan_conversion=True).
    3. Reads video.mp4 (cropped US cone, static UI removed) → grayscale numpy.
    4. Reads info.json → crop coordinate dict.

This is the same output as the video.mp4 files used for C3D training.
ffmpeg (mpeg4 codec) produces a bitstream identical to the one Jérémy used
during training, unlike cv2.VideoWriter(mp4v) which depends on the FFmpeg
linked to OpenCV and varies across OSes/versions.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import cv2
import numpy as np

from starhe_plugin.utils.go_print import go_print


# ── Path to the vendored prepUS ───────────────────────────────────────────────
_VENDOR_PREPUS = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),   # starhe_plugin/dicom/
        "..", "..", "..", "..",       # → repository root (PLUGIN1-MEDomics/)
        "third_party", "prepUS",
    )
)


def _ensure_importable() -> None:
    try:
        from prepUS.cli import removeLayoutFile  # noqa: F401
        return
    except ImportError:
        pass
    if os.path.isdir(_VENDOR_PREPUS) and _VENDOR_PREPUS not in sys.path:
        sys.path.insert(0, _VENDOR_PREPUS)
        try:
            from prepUS.cli import removeLayoutFile  # noqa: F401
            return
        except ImportError:
            pass
    raise ImportError(
        "Le package prepUS est introuvable.\n"
        f"  Source vendorisée attendue dans : {_VENDOR_PREPUS}\n"
        "  Installation : pip install third_party/prepUS --no-deps\n"
    )


def _fallback_crop_only(frames: np.ndarray) -> "tuple[np.ndarray, dict]":
    """
    Last-resort fallback if prepUS (Mode A and B) fails on find_linear_fov.
    Uses crop.py (temporal variability analysis) to detect the
    bounding box of the US cone. No UI mask — only a geometric crop.

    Returns the cropped grayscale frames with the same tuple format
    as preprocess_with_prepus / preprocess_with_prepus_inmem.
    """
    from starhe_plugin.dicom.crop import detect_ultrasound_roi_temporal

    if frames.ndim == 4:
        T, H, W, _ = frames.shape
        gray = np.stack([
            cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            for f in frames
        ])
    else:
        T, H, W = frames.shape
        gray = frames.astype(np.uint8)

    x0, y0, x1, y1 = detect_ultrasound_roi_temporal(gray)
    crop_frames = gray[:, y0:y1, x0:x1]
    info = {
        "crop": {"xmin": x0, "ymin": y0, "xmax": x1, "ymax": y1},
        "original_shape": {"width": W, "height": H},
        "threshold": -1.0,
        "fallback": "crop.py",
    }
    go_print("warning",
             f"prepus_bridge[crop.py]: crop {crop_frames.shape} "
             "(fallback — prepUS find_linear_fov a échoué sur ce DICOM ; "
             "pas de masque UI appliqué)")
    return crop_frames, info


def map_detections_to_dicom_coords(
    detections_per_frame: list,
    prepus_info: "dict | None",
) -> list:
    """Remaps the bboxes from crop space to the original DICOM image space."""
    if prepus_info is None or "crop" not in prepus_info:
        return detections_per_frame
    crop = prepus_info["crop"]
    cx = int(crop.get("xmin", 0))
    cy = int(crop.get("ymin", 0))
    mapped: list = []
    for frame_dets in detections_per_frame:
        mapped_dets: list = []
        for det in frame_dets:
            new_det = dict(det)
            x0, y0, x1, y1 = det["bbox"]
            new_det["bbox"] = [x0 + cx, y0 + cy, x1 + cx, y1 + cy]
            mapped_dets.append(new_det)
        mapped.append(mapped_dets)
    return mapped


def _frames_to_mp4_ffmpeg(frames: np.ndarray, fps: float, out_mp4: str) -> None:
    """
    Encodes (T, H, W, 3) uint8 RGB → MP4 via ffmpeg (rawvideo pipe).
    mpeg4 codec, -qscale:v 1 — identical to Jérémy's training pipeline
    (test_dicom_pipeline.py) and independent of the system OpenCV/FFmpeg version.
    Fallback to cv2.VideoWriter(mp4v) if ffmpeg is absent from the PATH.
    """
    T, H, W, _ = frames.shape
    ffmpeg_bin = shutil.which("ffmpeg")

    if ffmpeg_bin is None:
        go_print("warning", "prepus_bridge: ffmpeg absent — fallback cv2.VideoWriter(mp4v)")
        _frames_to_mp4_cv2(frames, fps, out_mp4)
        return

    cmd = [
        ffmpeg_bin, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "mpeg4", "-qscale:v", "1",
        out_mp4,
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for f in frames:
            proc.stdin.write(f.astype(np.uint8).tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    rc = proc.wait()
    if rc != 0:
        err = proc.stderr.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg exit={rc}:\n{err[-500:]}")
    go_print("info", f"prepus_bridge: ffmpeg {T} frames → {os.path.basename(out_mp4)}")


def _frames_to_mp4_cv2(frames: np.ndarray, fps: float, out_mp4: str) -> None:
    """cv2.VideoWriter(mp4v) fallback used only when ffmpeg is absent."""
    T, H, W, _ = frames.shape
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_mp4, fourcc, fps, (W, H))
    for f in frames:
        bgr = cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2BGR)
        writer.write(bgr)
    writer.release()
    go_print("info", f"prepus_bridge: cv2.VideoWriter(mp4v) {T} frames → {os.path.basename(out_mp4)}")


def _read_video_mp4_gray(video_mp4: str) -> "np.ndarray | None":
    """Reads a video.mp4 produced by prepUS → (T, H_crop, W_crop) uint8 grayscale."""
    if not os.path.exists(video_mp4):
        return None
    cap = cv2.VideoCapture(video_mp4)
    buf: list = []
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frm, cv2.COLOR_BGR2GRAY) if frm.ndim == 3 else frm
        buf.append(gray)
    cap.release()
    return np.stack(buf, axis=0) if buf else None


def preprocess_with_prepus_from_video(
    video_path: str,
    thresh: float = -1.0,
    backscan_width: int = 512,
    backscan_height: int = 512,
) -> "tuple[np.ndarray, dict | None]":
    """
    Aligned prepUS path: runs prepUS.removeLayoutFile DIRECTLY on an existing
    video file (mp4), WITHOUT the intermediate mpeg4 re-encode used by
    `preprocess_with_prepus`.

    Rationale
    ---------
    The training ground-truth (Jérémy) fed prepUS the video file produced at
    step 1 (DICOM → PNG → ffmpeg → mp4). Re-encoding the decoded frames to
    mpeg4 (`_frames_to_mp4_ffmpeg`) before prepUS alters the pixels, shifting
    prepUS's unique-pixel static map / auto-threshold → different UI mask and
    crop bbox → different C3D input. Reading the step-1 mp4 directly removes
    that divergence.

    Parameters
    ----------
    video_path : path to the source video (mp4/mov/avi) — read directly by
                 prepUS via sonocrop.loadvideo (no re-encode).
    thresh     : variability threshold; -1 = automatic (prepUS default).
    backscan_width / backscan_height : backscan dimensions.

    Returns
    -------
    crop_frames : (T, H_crop, W_crop) uint8 grayscale — video.mp4
    info        : dict from info.json or None

    Fallback : if find_linear_fov fails (no video.mp4) → crop.py geometric crop.
    """
    _ensure_importable()
    from prepUS.cli import removeLayoutFile  # type: ignore[import]

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Vidéo prepUS introuvable : {video_path}")

    work_dir = tempfile.mkdtemp(prefix="starhe_prepus_direct_")
    try:
        out_dir = os.path.join(work_dir, "out")
        removeLayoutFile(
            input_file=video_path,
            output_dir=out_dir,
            thresh=thresh,
            back_scan_conversion=True,
            backscan_width=backscan_width,
            backscan_height=backscan_height,
            save_mask=False,
            save_cropped_mask=False,
            save_info=True,
        )

        info: "dict | None" = None
        info_path = os.path.join(out_dir, "info.json")
        if os.path.exists(info_path):
            with open(info_path, encoding="utf-8") as fh:
                info = json.load(fh)

        crop_frames = _read_video_mp4_gray(os.path.join(out_dir, "video.mp4"))
        if crop_frames is not None:
            go_print("info",
                     f"prepus_bridge[direct]: crop {crop_frames.shape} depuis video.mp4 "
                     "(lecture mp4 directe, sans ré-encodage mpeg4)")
            return crop_frames, info

        go_print("warning",
                 "prepUS direct : video.mp4 absent (find_linear_fov a échoué) — "
                 "fallback crop.py")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    # Fallback: geometric crop on the decoded frames (no UI mask)
    import cv2 as _cv2
    cap = _cv2.VideoCapture(video_path)
    buf = []
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        buf.append(_cv2.cvtColor(frm, _cv2.COLOR_BGR2RGB))
    cap.release()
    frames_rgb = np.stack(buf, axis=0) if buf else np.zeros((0, 0, 0, 3), np.uint8)
    return _fallback_crop_only(frames_rgb)


def preprocess_with_prepus(
    frames: np.ndarray,
    fps: float = 22.0,
    thresh: float = -1.0,
    backscan_width: int = 512,
    backscan_height: int = 512,
) -> "tuple[np.ndarray, dict | None]":
    """
    Applies prepUS.removeLayoutFile and returns the frames from video.mp4.

    Parameters
    ----------
    frames         : (T, H, W, 3) uint8 RGB
    fps            : frame rate for the intermediate MP4 export
    thresh         : variability threshold; -1 = automatic (prepUS default)
    backscan_width / backscan_height : backscan dimensions (required by
                     removeLayoutFile to produce video.mp4)

    Returns
    -------
    crop_frames : (T, H_crop, W_crop) uint8 grayscale — video.mp4
    info        : dict from info.json ("crop", "backscan", … keys) or None

    Fallback chain
    --------------
    Mode A (this path) → if video.mp4 is absent/empty → Mode B (numpy bypass)
                       → if find_linear_fov also fails → crop.py

    Reason for the Mode A fallback: removeLayoutFile() silently returns None
    when find_linear_fov exhausts its retries (thresh ≤ 0.005), without raising
    an exception and without writing video.mp4.
    """
    _ensure_importable()
    from prepUS.cli import removeLayoutFile  # type: ignore[import]

    if frames.ndim != 4 or frames.shape[3] != 3:
        raise ValueError(f"frames doit être (T, H, W, 3), reçu {frames.shape}")

    work_dir = tempfile.mkdtemp(prefix="starhe_prepus_")
    _mode_a_result: "tuple[np.ndarray, dict | None] | None" = None

    try:
        # ── 1. Encode the frames → MP4 via ffmpeg (mpeg4 codec, qscale 1) ────
        tmp_mp4 = os.path.join(work_dir, "input.mp4")
        _frames_to_mp4_ffmpeg(frames, fps, tmp_mp4)

        # ── 2. prepUS call ────────────────────────────────────────────────────
        out_dir = os.path.join(work_dir, "out")
        removeLayoutFile(
            input_file=tmp_mp4,
            output_dir=out_dir,
            thresh=thresh,
            back_scan_conversion=True,
            backscan_width=backscan_width,
            backscan_height=backscan_height,
            save_mask=False,
            save_cropped_mask=False,
            save_info=True,
        )

        # ── 3. Read info.json ─────────────────────────────────────────────────
        info: "dict | None" = None
        info_path = os.path.join(out_dir, "info.json")
        if os.path.exists(info_path):
            with open(info_path, encoding="utf-8") as fh:
                info = json.load(fh)

        # ── 4. Read video.mp4 (cropped, masked cone) ─────────────────────────
        video_mp4 = os.path.join(out_dir, "video.mp4")
        if os.path.exists(video_mp4):
            cap = cv2.VideoCapture(video_mp4)
            buf: list = []
            while True:
                ok, frm = cap.read()
                if not ok:
                    break
                gray = cv2.cvtColor(frm, cv2.COLOR_BGR2GRAY) if frm.ndim == 3 else frm
                buf.append(gray)
            cap.release()

            if buf:
                crop_frames = np.stack(buf, axis=0)  # (T, H_crop, W_crop) uint8
                go_print("info", f"prepus_bridge: crop {crop_frames.shape} depuis video.mp4")
                _mode_a_result = (crop_frames, info)
            else:
                go_print("warning",
                         "prepUS Mode A : video.mp4 vide — "
                         "find_linear_fov a probablement échoué sur ce DICOM")
        else:
            go_print("warning",
                     "prepUS Mode A : video.mp4 absent — removeLayoutFile a retourné "
                     "silencieusement (find_linear_fov a épuisé ses retries)")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    if _mode_a_result is not None:
        return _mode_a_result

    # ── Mode B fallback: numpy bypass (same algorithm, no MP4 roundtrip) ──────
    go_print("warning",
             "prepUS Mode A échoué — fallback Mode B (bypass numpy)")
    try:
        return preprocess_with_prepus_inmem(
            frames,
            fps=fps,
            thresh=thresh,
            backscan_width=backscan_width,
            backscan_height=backscan_height,
        )
    except RuntimeError as exc_b:
        go_print("warning",
                 f"prepUS Mode B aussi échoué ({exc_b}) — "
                 "fallback crop.py (crop géométrique, pas de masque UI)")
        return _fallback_crop_only(frames)


# ─────────────────────────────────────────────────────────────────────────────
# In-memory variant: complete bypass of the MP4 roundtrip (cv2 VideoWriter/Capture).
#
# Motivation: `cv2.VideoWriter(mp4v)` produces a bitstream that depends on the
# FFmpeg binary linked to OpenCV. macOS ARM (Homebrew) and Linux (Jean Zay)
# produce different `video.mp4` files for the same numpy input, which slightly
# shifts the C3D input and prevents reproducing Jérémy's scores bit-near.
# This variant computes the crop exclusively in numpy: 100% deterministic
# cross-platform, but deviates slightly from the training distribution
# (loses the mp4v artifacts seen during training).
# ─────────────────────────────────────────────────────────────────────────────

def _remove_layout_inmem(
    v: np.ndarray,
    fps: float,
    thresh: float,
    FOV_tresh: int,
    backscan_width: int,
    backscan_height: int,
) -> "tuple[np.ndarray, dict]":
    """
    Pure numpy reimplementation of `prepUS.cli.removeLayoutFile` (back_scan_conversion=True),
    without any MP4 write/read. The logic is strictly identical to the
    reference; only the VideoWriter/VideoCapture/savevideo calls are removed.

    Parameters
    ----------
    v : (T, H, W) uint8  — grayscale frames (equivalent output of
        `sonocrop.vid.loadvideo`).
    fps : float          — unused internally (kept for the info trace).
    thresh : float       — -1 = auto threshold (unique-pixel histogram).
    FOV_tresh : int      — Hough threshold for find_linear_fov.
    backscan_width / backscan_height : linear FOV dims.

    Returns
    -------
    y_cropped : (T, H_crop, W_crop) uint8 — equivalent of the `video.mp4`
                produced by prepUS, without the mp4v roundtrip.
    info      : dict     — metadata (crop bbox + backscan parameters).
    """
    from scipy.ndimage import binary_fill_holes
    from sonocrop import vid
    from prepUS.utils import keep_largest_component, sync_halves, crop_single_object
    from prepUS.backscan import find_linear_fov, pre_dsc_image_vectorized

    f, height, width = v.shape

    # Step 1: per-position unique-pixel map (identical to the reference)
    u = np.zeros((height, width), np.uint8)
    for i in range(height):
        u[i] = np.apply_along_axis(vid.countUniquePixels, 0, v[:, i, :])
    u_avg = u / f

    if thresh == -1:
        _, bin_edges = np.histogram(u_avg, bins=20)
        thresh = bin_edges[3]

    # Step 2: denoised boolean mask + mirror + hole filling
    mask = u_avg > thresh
    mask_img = mask.astype(np.uint8)
    mask_largest_img = keep_largest_component(mask_img)
    mask_mirrored_largest_img = sync_halves(np.copy(mask_largest_img))

    boolean_mask = binary_fill_holes((mask_mirrored_largest_img / 255).astype(bool))
    boolean_mask = (boolean_mask * 255).astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    denoised_image = cv2.morphologyEx(boolean_mask, cv2.MORPH_OPEN, kernel)
    denoised_image = cv2.morphologyEx(denoised_image, cv2.MORPH_CLOSE, kernel)
    boolean_mask = (denoised_image / 255).astype(bool)

    cropped_boolean_mask, ymin, ymax, xmin, xmax = crop_single_object(np.copy(boolean_mask))

    # Step 3: find_linear_fov (with a retry identical to the reference on failure)
    params = find_linear_fov((cropped_boolean_mask * 255).astype(np.uint8), threshold=FOV_tresh)
    if params is None:
        if thresh > 0.005:
            # Recursive retry: thresh × 0.8, FOV_tresh × 0.9 (reference lines 187-194 cli.py)
            return _remove_layout_inmem(
                v, fps,
                thresh=thresh * 0.8,
                FOV_tresh=int(FOV_tresh * 0.9),
                backscan_width=backscan_width,
                backscan_height=backscan_height,
            )
        raise RuntimeError(
            "prepUS in-mem : find_linear_fov a échoué et thresh ≤ 0.005 "
            "(comportement identique à la référence : abandon)."
        )
    xoffset, yoffset, rc, theta_c, dc = params

    # Step 4: cropping + valid FOV mask (same ops as the reference)
    y_cropped = v[:, ymin:ymax, xmin:xmax]
    mask_valid = pre_dsc_image_vectorized(
        y_cropped[0], dc, rc, theta_c, yoffset, xoffset,
        backscan_width, backscan_height, get_IUSI_FOV=True,
    )
    y_cropped = vid.applyMask(y_cropped, (mask_valid / 255).astype(bool))

    info = {
        "crop": {
            "ymin": int(ymin),
            "ymax": int(ymax),
            "xmin": int(xmin),
            "xmax": int(xmax),
        },
        "original_shape": {
            "width": int(width),
            "height": int(height),
        },
        "threshold": float(thresh),
        "backscan": {
            "width": int(backscan_width),
            "height": int(backscan_height),
            "xoffset": float(xoffset),
            "yoffset": float(yoffset),
            "rc": float(rc),
            "dc": float(dc),
            "theta_c": float(theta_c),
        },
    }
    return y_cropped, info


def preprocess_with_prepus_inmem(
    frames: np.ndarray,
    fps: float = 22.0,
    thresh: float = -1.0,
    FOV_tresh: int = 100,
    backscan_width: int = 512,
    backscan_height: int = 512,
) -> "tuple[np.ndarray, dict | None]":
    """
    100% numpy variant of `preprocess_with_prepus`: no MP4 roundtrip.

    Difference from the standard version:
      - NO `input.mp4` export (cv2.VideoWriter)
      - NO `video.mp4` read (cv2.VideoCapture)
      - prepUS is executed in-process on the numpy converted RGB→GRAY directly.

    Advantage : bit-identical output across macOS/Linux/Windows for the
                same numpy input (eliminates the non-portability of mp4v).
    Cost      : deviates slightly from the training distribution (the
                C3D saw crops decoded from mp4v, not pure numpy).

    Signature and return semantics identical to `preprocess_with_prepus`.
    """
    _ensure_importable()

    if frames.ndim != 4 or frames.shape[3] != 3:
        raise ValueError(f"frames doit être (T, H, W, 3), reçu {frames.shape}")

    T = frames.shape[0]

    # RGB → grayscale uint8 conversion (equivalent to the
    # mp4v(color)→VideoCapture(BGR)→cvtColor(BGR2GRAY) path without the mp4v loss).
    # cv2.cvtColor(RGB2GRAY) applies exactly the same ITU-R BT.601 weights
    # (0.299·R + 0.587·G + 0.114·B) as BGR2GRAY.
    gray_frames = np.empty((T, frames.shape[1], frames.shape[2]), dtype=np.uint8)
    for i, f in enumerate(frames):
        gray_frames[i] = cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2GRAY)

    go_print("info", f"prepus_bridge[inmem]: {T} frames RGB → gray (bypass MP4)")

    try:
        crop_frames, info = _remove_layout_inmem(
            gray_frames,
            fps=fps,
            thresh=thresh,
            FOV_tresh=FOV_tresh,
            backscan_width=backscan_width,
            backscan_height=backscan_height,
        )
    except RuntimeError as exc:
        go_print("warning",
                 f"prepUS in-mem échoué ({exc}) — "
                 "fallback crop.py (crop géométrique, pas de masque UI)")
        return _fallback_crop_only(frames)
    go_print("info", f"prepus_bridge[inmem]: crop {crop_frames.shape} (numpy direct)")
    return crop_frames, info
