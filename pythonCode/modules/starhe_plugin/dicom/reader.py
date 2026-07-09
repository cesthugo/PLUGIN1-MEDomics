"""
dicom/reader.py — DICOM file reading and extraction
==========================================================
Provides:
  - load_dicom()        : loads a .dcm file and returns the pydicom dataset
  - extract_frames()    : extracts all pixel frames into a numpy array (T x H x W x C)
  - is_cine_clip()      : detects whether the file contains multiple frames (cine-clip)
  - frame_to_uint8()    : normalizes a frame into a displayable 8-bit image
"""

from io import BytesIO

import numpy as np
import pydicom
from pydicom.errors import InvalidDicomError
from starhe_plugin.utils.go_print import go_print


def load_dicom(path: str) -> pydicom.dataset.FileDataset:
    """
    Loads a DICOM file from the given path.
    Returns the pydicom dataset or raises an explicit exception.
    """
    try:
        ds = pydicom.dcmread(path, force=True)
        go_print("info", f"DICOM chargé : {path} | SOPClassUID={getattr(ds, 'SOPClassUID', 'N/A')}")
        return ds
    except InvalidDicomError as e:
        go_print("error", f"Fichier non DICOM valide : {path} — {e}")
        raise
    except FileNotFoundError:
        go_print("error", f"Fichier introuvable : {path}")
        raise


def is_cine_clip(ds: pydicom.dataset.FileDataset) -> bool:
    """
    Returns True if the DICOM contains multiple frames (cine-clip).
    Criteria: NumberOfFrames > 1 or rank-4 pixel_array.
    """
    n_frames = int(getattr(ds, "NumberOfFrames", 1))
    return n_frames > 1


def _pixel_array_to_tchw(pixel_array: np.ndarray) -> np.ndarray:
    """Normalizes a raw pixel_array into (T, H, W) or (T, H, W, 3)."""
    if pixel_array.ndim == 2:
        return pixel_array[np.newaxis, ...]          # (1, H, W)
    if pixel_array.ndim == 3:
        if pixel_array.shape[2] == 3:
            return pixel_array[np.newaxis, ...]      # (1, H, W, 3) — single RGB
        return pixel_array                           # (T, H, W)
    return pixel_array                               # (T, H, W, 3) already correct


def _j2k_codestream_bounds(raw: bytes) -> list[tuple[int, int]]:
    """
    Returns the list of (start, end) intervals for each valid J2K codestream.

    Lsiz validation (38-65535) to filter out SOC+SIZ false positives.

    End-bound strategy:
    - Intermediate frames: end = start of the next codestream. OpenJPEG parses
      the stream up to its own EOC marker and ignores trailing bytes (DICOM
      item delimiter). This avoids the false EOCs (FF D9) present in J2K
      segment parameters (SIZ, TLM, COM…) which truncated the stream and
      crashed OpenJPEG.
    - Last frame: end = position of the DICOM sequence delimiter (FFFE,E0DD)
      so as not to include non-J2K DICOM bytes at the end of the buffer.
    """
    SOC_SIZ   = b"\xff\x4f\xff\x51"
    SEQ_DELIM = b"\xfe\xff\xdd\xe0"  # tag FFFE,E0DD little-endian

    starts: list[int] = []
    idx = 0
    while True:
        pos = raw.find(SOC_SIZ, idx)
        if pos == -1:
            break
        if pos + 6 <= len(raw):
            lsiz = int.from_bytes(raw[pos + 4: pos + 6], "big")
            if 38 <= lsiz <= 65535:
                starts.append(pos)
        idx = pos + 4

    if not starts:
        return []

    seq_delim_pos = raw.find(SEQ_DELIM)
    data_end = seq_delim_pos if seq_delim_pos != -1 else len(raw)

    bounds: list[tuple[int, int]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else data_end
        bounds.append((start, end))

    return bounds


def _extract_j2k_raw_scan(
    ds: pydicom.dataset.FileDataset,
    display_max_frames: int | None = None,
) -> np.ndarray:
    """
    Robust fallback for JPEG 2000 files whose offset table pydicom fails
    to parse correctly (empty BOT, EOT, non-standard encapsulation).

    Strategy: scan the raw PixelData bytes for the J2K SOC+SIZ marker
    (FF 4F FF 51) and decode each codestream directly with
    PIL/Pillow, bypassing pydicom's extraction logic entirely.

    display_max_frames: if set, only decodes a uniformly distributed
        subset of the found codestreams (display optimization).
    """
    raw = bytes(ds.PixelData)
    n_expected = int(getattr(ds, "NumberOfFrames", 1))
    ts = str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", "?"))

    bounds = _j2k_codestream_bounds(raw)

    if not bounds:
        raise ValueError(
            f"Aucun codestream J2K valide trouvé dans {len(raw)} octets de PixelData "
            f"(TS={ts}). Le fichier n'est peut-être pas JPEG 2000."
        )

    go_print("info",
             f"J2K raw scan : {len(bounds)} codestream(s) trouvé(s) "
             f"sur {n_expected} frame(s) attendue(s)")

    # Display subsampling: only decode a subset
    if display_max_frames is not None and len(bounds) > display_max_frames:
        n_total = len(bounds)
        step = n_total / display_max_frames
        keep = [int(i * step) for i in range(display_max_frames)]
        bounds = [bounds[i] for i in keep]
        go_print("info",
                 f"J2K raw scan display : sous-échantillonnage {n_total} → {len(bounds)} frames")

    # Pillow wraps OpenJPEG with setjmp/longjmp: C errors become Python
    # exceptions (no segfault). The standalone 'openjpeg' package lacks
    # this protection on Windows — it is used only if PIL is absent.
    try:
        from PIL import Image as _PILImage
        def _decode_frame(data: bytes) -> np.ndarray:
            with _PILImage.open(BytesIO(data)) as img:
                mode = img.mode
                if mode not in ("L", "RGB"):
                    img = img.convert("RGB")
                return np.array(img)
    except ImportError:
        from openjpeg import decode as _opj_decode
        def _decode_frame(data: bytes) -> np.ndarray:  # type: ignore[misc]
            return _opj_decode(BytesIO(data))

    frames = []
    failed = 0
    for i, (start, end) in enumerate(bounds):
        frame_bytes = raw[start:end]
        try:
            arr = _decode_frame(frame_bytes)
            frames.append(arr)
        except Exception as e:
            failed += 1
            go_print("warning", f"J2K raw scan : frame {i} decode echoue ({e}), ignoree")

    if not frames:
        raise ValueError("J2K raw scan : aucune frame n'a pu etre decodee")

    if failed:
        go_print("warning", f"J2K raw scan : {failed} frame(s) ignoree(s) sur {len(bounds)}")

    # Normalize the shapes before np.stack
    shapes = {f.shape for f in frames}
    if len(shapes) > 1:
        ref_shape = max(shapes, key=lambda s: s[0] * s[1])
        frames = [f for f in frames if f.shape == ref_shape]
        go_print("warning", f"J2K raw scan : shapes heterogenes, conserve shape={ref_shape} ({len(frames)} frames)")

    return _pixel_array_to_tchw(np.stack(frames))


def extract_frames(
    ds: pydicom.dataset.FileDataset,
    display_max_frames: int | None = None,
) -> np.ndarray:
    """
    Extracts the DICOM pixel data into a numpy array.

    Returns:
      - Array of shape (T, H, W)   if grayscale
      - Array of shape (T, H, W, 3) if RGB

    display_max_frames: if set, uniformly subsamples down to this maximum
        number of frames (display-only optimization).

    Fallback chain (from fastest to most robust):
      1. ds.pixel_array          — pydicom + installed handlers
      2. ds.decompress()         — pydicom 3.x: converts to uncompressed
      3. _extract_j2k_raw_scan() — raw byte scan for J2K SOC+SIZ markers
    """
    ts = str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", "absent"))
    pi = str(getattr(ds, "PhotometricInterpretation", "?"))
    go_print("info", f"extract_frames : TS={ts} | PhotometricInterp={pi}")

    def _subsample(arr: np.ndarray) -> np.ndarray:
        if display_max_frames is None or arr.shape[0] <= display_max_frames:
            return arr
        T = arr.shape[0]
        step = T / display_max_frames
        indices = [int(i * step) for i in range(display_max_frames)]
        go_print("info", f"extract_frames display : sous-échantillonnage {T} → {len(indices)} frames")
        return arr[indices]

    # ── 1. Direct read (nominal case) ────────────────────────────────────────
    errors: list[str] = []
    try:
        pixel_array = ds.pixel_array
        return _subsample(_pixel_array_to_tchw(pixel_array))
    except Exception as e1:
        errors.append(f"pixel_array: {e1}")
        go_print("warning", f"pixel_array direct échoué ({e1}), tentatives fallback…")

    # ── 2. ds.decompress() (pydicom 3.x) then re-read ─────────────────────────
    try:
        ds.decompress()
        pixel_array = ds.pixel_array
        go_print("info", "Décompression pydicom réussie.")
        return _subsample(_pixel_array_to_tchw(pixel_array))
    except AttributeError:
        pass  # pydicom < 3.x, method absent — move to the next fallback
    except Exception as e2:
        errors.append(f"decompress: {e2}")
        go_print("warning", f"decompress() échoué ({e2})")

    # ── 3. Raw scan for J2K SOC+SIZ bytes in PixelData ────────────────────────
    try:
        return _extract_j2k_raw_scan(ds, display_max_frames=display_max_frames)
    except Exception as e3:
        errors.append(f"j2k_scan: {e3}")
        go_print("warning", f"J2K raw scan échoué ({e3})")

    # ── All attempts failed ───────────────────────────────────────────────────
    raise RuntimeError(
        f"Impossible de décoder les données pixel de ce fichier DICOM. "
        f"TransferSyntax={ts}, PhotometricInterp={pi}, "
        f"Frames={getattr(ds, 'NumberOfFrames', 1)}. "
        f"Erreurs: {' | '.join(errors)}"
    )


def frame_to_uint8(frame: np.ndarray) -> np.ndarray:
    """
    Normalizes a frame (uint8, uint16…) into the [0, 255] uint8 range.
    Handles grayscale and RGB images.
    """
    f = frame.astype(np.float32)
    f_min, f_max = f.min(), f.max()
    if f_max > f_min:
        f = (f - f_min) / (f_max - f_min) * 255.0
    return f.astype(np.uint8)
