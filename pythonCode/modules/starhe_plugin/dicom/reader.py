"""
dicom/reader.py — Lecture et extraction de fichiers DICOM
==========================================================
Fournit :
  - load_dicom()        : charge un fichier .dcm et retourne le dataset pydicom
  - extract_frames()    : extrait tous les frames pixel en array numpy (T x H x W x C)
  - is_cine_clip()      : détecte si le fichier contient plusieurs frames (ciné-clip)
  - frame_to_uint8()    : normalise un frame en image 8 bits affichable
"""

from io import BytesIO

import numpy as np
import pydicom
from pydicom.errors import InvalidDicomError
from starhe_plugin.utils.go_print import go_print


def load_dicom(path: str) -> pydicom.dataset.FileDataset:
    """
    Charge un fichier DICOM depuis le chemin donné.
    Retourne le dataset pydicom ou lève une exception explicite.
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
    Retourne True si le DICOM contient plusieurs frames (ciné-clip).
    Critères : NumberOfFrames > 1 ou pixel_array de rang 4.
    """
    n_frames = int(getattr(ds, "NumberOfFrames", 1))
    return n_frames > 1


def _pixel_array_to_tchw(pixel_array: np.ndarray) -> np.ndarray:
    """Normalise un pixel_array brut en (T, H, W) ou (T, H, W, 3)."""
    if pixel_array.ndim == 2:
        return pixel_array[np.newaxis, ...]          # (1, H, W)
    if pixel_array.ndim == 3:
        if pixel_array.shape[2] == 3:
            return pixel_array[np.newaxis, ...]      # (1, H, W, 3) — mono RGB
        return pixel_array                           # (T, H, W)
    return pixel_array                               # (T, H, W, 3) déjà correct


def _j2k_codestream_bounds(raw: bytes) -> list[tuple[int, int]]:
    """
    Retourne la liste des intervalles (start, end) de chaque codestream J2K valide.

    Validation Lsiz (38-65535) pour filtrer les faux positifs SOC+SIZ.

    Stratégie de borne de fin :
    - Frames intermédiaires : end = début du codestream suivant. OpenJPEG parse
      le flux jusqu'à son propre marqueur EOC et ignore les bytes trailing (item
      delimiter DICOM). On évite ainsi les faux EOC (FF D9) présents dans les
      paramètres de segments J2K (SIZ, TLM, COM…) qui tronquaient le flux et
      provoquaient un crash OpenJPEG.
    - Dernière frame : end = position du délimiteur de séquence DICOM (FFFE,E0DD)
      pour ne pas inclure les bytes DICOM non-J2K en queue de buffer.
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
    Fallback robuste pour les fichiers JPEG 2000 dont pydicom ne parse pas
    correctement la table des offsets (BOT vide, EOT, encapsulation non standard).

    Stratégie : scanner les bytes bruts de PixelData à la recherche du marqueur
    J2K SOC+SIZ (FF 4F FF 51) et décoder chaque codestream directement avec
    PIL/Pillow, en contournant entièrement la logique d'extraction de pydicom.

    display_max_frames : si renseigné, ne décode qu'un sous-ensemble uniformément
        réparti des codestreams trouvés (optimisation pour l'affichage).
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

    # Sous-échantillonnage pour l'affichage : décode seulement un sous-ensemble
    if display_max_frames is not None and len(bounds) > display_max_frames:
        n_total = len(bounds)
        step = n_total / display_max_frames
        keep = [int(i * step) for i in range(display_max_frames)]
        bounds = [bounds[i] for i in keep]
        go_print("info",
                 f"J2K raw scan display : sous-échantillonnage {n_total} → {len(bounds)} frames")

    # Pillow wrape OpenJPEG avec setjmp/longjmp : les erreurs C deviennent des
    # exceptions Python (pas de segfault). Le package standalone 'openjpeg' n'a
    # pas cette protection sur Windows — il est utilisé uniquement si PIL absent.
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

    # Normalise les shapes avant np.stack
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
    Extrait les données pixel du DICOM en array numpy.

    Retourne :
      - Array de shape (T, H, W)   si niveaux-de-gris
      - Array de shape (T, H, W, 3) si RGB

    display_max_frames : si renseigné, sous-échantillonne uniformément à ce nombre
        de frames maximum (optimisation pour l'affichage uniquement).

    Chaîne de fallbacks (du plus rapide au plus robuste) :
      1. ds.pixel_array          — pydicom + handlers installés
      2. ds.decompress()         — pydicom 3.x : convertit en non-compressé
      3. _extract_j2k_raw_scan() — scan brut des bytes pour marqueurs J2K SOC+SIZ
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

    # ── 1. Lecture directe (cas nominal) ─────────────────────────────────────
    errors: list[str] = []
    try:
        pixel_array = ds.pixel_array
        return _subsample(_pixel_array_to_tchw(pixel_array))
    except Exception as e1:
        errors.append(f"pixel_array: {e1}")
        go_print("warning", f"pixel_array direct échoué ({e1}), tentatives fallback…")

    # ── 2. ds.decompress() (pydicom 3.x) puis relecture ──────────────────────
    try:
        ds.decompress()
        pixel_array = ds.pixel_array
        go_print("info", "Décompression pydicom réussie.")
        return _subsample(_pixel_array_to_tchw(pixel_array))
    except AttributeError:
        pass  # pydicom < 3.x, méthode absente — passer au fallback suivant
    except Exception as e2:
        errors.append(f"decompress: {e2}")
        go_print("warning", f"decompress() échoué ({e2})")

    # ── 3. Scan brut des bytes J2K SOC+SIZ dans PixelData ────────────────────
    try:
        return _extract_j2k_raw_scan(ds, display_max_frames=display_max_frames)
    except Exception as e3:
        errors.append(f"j2k_scan: {e3}")
        go_print("warning", f"J2K raw scan échoué ({e3})")

    # ── Toutes les tentatives ont échoué ─────────────────────────────────────
    raise RuntimeError(
        f"Impossible de décoder les données pixel de ce fichier DICOM. "
        f"TransferSyntax={ts}, PhotometricInterp={pi}, "
        f"Frames={getattr(ds, 'NumberOfFrames', 1)}. "
        f"Erreurs: {' | '.join(errors)}"
    )


def frame_to_uint8(frame: np.ndarray) -> np.ndarray:
    """
    Normalise un frame (uint8, uint16…) vers l'intervalle [0, 255] uint8.
    Gère les images en niveaux de gris et RGB.
    """
    f = frame.astype(np.float32)
    f_min, f_max = f.min(), f.max()
    if f_max > f_min:
        f = (f - f_min) / (f_max - f_min) * 255.0
    return f.astype(np.uint8)
