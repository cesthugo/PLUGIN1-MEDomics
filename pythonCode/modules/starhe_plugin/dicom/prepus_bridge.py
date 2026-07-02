"""
dicom/prepus_bridge.py — Intégration de l'API prepUS.removeLayoutFile
======================================================================
Reproduit exactement le pipeline de référence (prepus/prepUS/cli.py) :

    1. Encode les frames numpy → MP4 via ffmpeg (codec mpeg4, -qscale:v 1).
       Fallback cv2.VideoWriter(mp4v) si ffmpeg est absent du PATH.
    2. Appelle prepUS.cli.removeLayoutFile (back_scan_conversion=True).
    3. Lit video.mp4 (cône US rogné, UI statique retirée) → numpy gris.
    4. Lit info.json → dict de coordonnées de crop.

C'est la même sortie que les video.mp4 utilisés pour l'entraînement du C3D.
ffmpeg (codec mpeg4) produit un bitstream identique à celui utilisé par Jérémy
à l'entraînement, contrairement à cv2.VideoWriter(mp4v) qui dépend du FFmpeg
lié à OpenCV et varie entre OS/versions.
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


# ── Chemin vers prepUS vendorisé ──────────────────────────────────────────────
_VENDOR_PREPUS = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),   # starhe_plugin/dicom/
        "..", "..", "..", "..",       # → racine du dépôt (PLUGIN1-MEDomics/)
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
    Fallback ultime si prepUS (Mode A et B) échoue sur find_linear_fov.
    Utilise crop.py (analyse temporelle de variabilité) pour détecter la
    bounding-box du cône US. Pas de masque UI — uniquement un crop géométrique.

    Retourne les frames en niveaux de gris rognées avec le même format
    de tuple que preprocess_with_prepus / preprocess_with_prepus_inmem.
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
    """Remappe les bboxes de l'espace crop vers l'espace image DICOM original."""
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
    Encode (T, H, W, 3) uint8 RGB → MP4 via ffmpeg (rawvideo pipe).
    Codec mpeg4, -qscale:v 1 — identique au pipeline d'entraînement de Jérémy
    (test_dicom_pipeline.py) et indépendant de la version OpenCV/FFmpeg système.
    Fallback vers cv2.VideoWriter(mp4v) si ffmpeg est absent du PATH.
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
    """Fallback cv2.VideoWriter(mp4v) utilisé uniquement si ffmpeg est absent."""
    T, H, W, _ = frames.shape
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_mp4, fourcc, fps, (W, H))
    for f in frames:
        bgr = cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2BGR)
        writer.write(bgr)
    writer.release()
    go_print("info", f"prepus_bridge: cv2.VideoWriter(mp4v) {T} frames → {os.path.basename(out_mp4)}")


def preprocess_with_prepus(
    frames: np.ndarray,
    fps: float = 22.0,
    thresh: float = -1.0,
    backscan_width: int = 512,
    backscan_height: int = 512,
) -> "tuple[np.ndarray, dict | None]":
    """
    Applique prepUS.removeLayoutFile et retourne les frames de video.mp4.

    Paramètres
    ----------
    frames         : (T, H, W, 3) uint8 RGB
    fps            : fréquence d'images pour l'export MP4 intermédiaire
    thresh         : seuil variabilité ; -1 = automatique (défaut prepUS)
    backscan_width / backscan_height : dimensions backscan (requises par
                     removeLayoutFile pour produire video.mp4)

    Retourne
    --------
    crop_frames : (T, H_crop, W_crop) uint8 niveaux de gris — video.mp4
    info        : dict depuis info.json (clés "crop", "backscan", …) ou None

    Chaîne de fallback
    ------------------
    Mode A (ce chemin) → si video.mp4 absent/vide → Mode B (bypass numpy)
                       → si find_linear_fov échoue aussi → crop.py

    Motif du fallback Mode A : removeLayoutFile() retourne None silencieusement
    quand find_linear_fov épuise ses retries (thresh ≤ 0.005), sans lever
    d'exception et sans écrire video.mp4.
    """
    _ensure_importable()
    from prepUS.cli import removeLayoutFile  # type: ignore[import]

    if frames.ndim != 4 or frames.shape[3] != 3:
        raise ValueError(f"frames doit être (T, H, W, 3), reçu {frames.shape}")

    work_dir = tempfile.mkdtemp(prefix="starhe_prepus_")
    _mode_a_result: "tuple[np.ndarray, dict | None] | None" = None

    try:
        # ── 1. Encoder les frames → MP4 via ffmpeg (codec mpeg4, qscale 1) ───
        tmp_mp4 = os.path.join(work_dir, "input.mp4")
        _frames_to_mp4_ffmpeg(frames, fps, tmp_mp4)

        # ── 2. Appel prepUS ───────────────────────────────────────────────────
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

        # ── 3. Lire info.json ─────────────────────────────────────────────────
        info: "dict | None" = None
        info_path = os.path.join(out_dir, "info.json")
        if os.path.exists(info_path):
            with open(info_path, encoding="utf-8") as fh:
                info = json.load(fh)

        # ── 4. Lire video.mp4 (cône rogné, masqué) ───────────────────────────
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

    # ── Fallback Mode B : bypass numpy (même algorithme, sans roundtrip MP4) ──
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
# Variante in-memory : bypass total du roundtrip MP4 (cv2 VideoWriter/Capture).
#
# Motivation : `cv2.VideoWriter(mp4v)` produit un bitstream dépendant du binaire
# FFmpeg lié à OpenCV. macOS ARM (Homebrew) et Linux (Jean Zay) produisent des
# `video.mp4` différents pour la même entrée numpy, ce qui décale légèrement
# l'entrée du C3D et empêche de reproduire bit-near les scores de Jérémy.
# Cette variante calcule le crop exclusivement en numpy : 100 % déterministe
# cross-plateforme, mais s'écarte légèrement de la distribution d'entraînement
# (perte des artefacts mp4v vus pendant l'entraînement).
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
    Réimplémentation numpy pure de `prepUS.cli.removeLayoutFile` (back_scan_conversion=True),
    sans aucune écriture/lecture MP4. La logique est strictement identique à la
    référence ; seuls les appels VideoWriter/VideoCapture/savevideo sont supprimés.

    Parameters
    ----------
    v : (T, H, W) uint8  — frames en niveaux de gris (sortie équivalente de
        `sonocrop.vid.loadvideo`).
    fps : float          — non utilisé en interne (gardé pour la trace info).
    thresh : float       — -1 = seuil auto (histogramme des pixels uniques).
    FOV_tresh : int      — seuil Hough pour find_linear_fov.
    backscan_width / backscan_height : dims FOV linéaire.

    Returns
    -------
    y_cropped : (T, H_crop, W_crop) uint8 — équivalent du `video.mp4` produit
                par prepUS, sans roundtrip mp4v.
    info      : dict     — métadonnées (crop bbox + paramètres backscan).
    """
    from scipy.ndimage import binary_fill_holes
    from sonocrop import vid
    from prepUS.utils import keep_largest_component, sync_halves, crop_single_object
    from prepUS.backscan import find_linear_fov, pre_dsc_image_vectorized

    f, height, width = v.shape

    # Étape 1 : carte des pixels uniques par position (identique référence)
    u = np.zeros((height, width), np.uint8)
    for i in range(height):
        u[i] = np.apply_along_axis(vid.countUniquePixels, 0, v[:, i, :])
    u_avg = u / f

    if thresh == -1:
        _, bin_edges = np.histogram(u_avg, bins=20)
        thresh = bin_edges[3]

    # Étape 2 : masque booléen denoisé + miroir + remplissage de trous
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

    # Étape 3 : find_linear_fov (avec retry identique à la référence en cas d'échec)
    params = find_linear_fov((cropped_boolean_mask * 255).astype(np.uint8), threshold=FOV_tresh)
    if params is None:
        if thresh > 0.005:
            # Retry récursif : thresh × 0.8, FOV_tresh × 0.9 (référence ligne 187-194 cli.py)
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

    # Étape 4 : recadrage + masque valid FOV (mêmes ops que la référence)
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
    Variante 100 % numpy de `preprocess_with_prepus` : aucun roundtrip MP4.

    Différence avec la version standard :
      - PAS d'export `input.mp4` (cv2.VideoWriter)
      - PAS de lecture `video.mp4` (cv2.VideoCapture)
      - prepUS est exécuté in-process sur le numpy converti RGB→GRAY direct.

    Avantage  : sortie identique bit-à-bit entre macOS/Linux/Windows pour la
                même entrée numpy (élimine la non-portabilité de mp4v).
    Coût      : s'écarte légèrement de la distribution d'entraînement (le
                C3D a vu des crops décodés depuis mp4v, pas du numpy pur).

    Signature et sémantique de retour identiques à `preprocess_with_prepus`.
    """
    _ensure_importable()

    if frames.ndim != 4 or frames.shape[3] != 3:
        raise ValueError(f"frames doit être (T, H, W, 3), reçu {frames.shape}")

    T = frames.shape[0]

    # Conversion RGB → grayscale uint8 (équivalent du chemin
    # mp4v(color)→VideoCapture(BGR)→cvtColor(BGR2GRAY) sans la perte mp4v).
    # cv2.cvtColor(RGB2GRAY) applique exactement les mêmes poids ITU-R BT.601
    # (0.299·R + 0.587·G + 0.114·B) que BGR2GRAY.
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
