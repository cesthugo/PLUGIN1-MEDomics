"""
dicom/prepus_bridge.py — Intégration de l'API prepUS.removeLayout
==================================================================
Utilise directement l'API publique de prepUS pour le prétraitement :

    from prepUS import removeLayout (ou removeLayoutFile)

Pipeline interne :
    1. Exporte les frames DICOM numpy → MP4 temporaire (OpenCV).
    2. Appelle ``prepUS.cli.removeLayoutFile`` :
         - détection des pixels statiques (UI, texte, règles)
         - masquage + rognage du cône US
         - conversion scan inverse (backscan) optionnelle
    3. Lit la vidéo de sortie → retourne un ndarray numpy.
    4. Supprime les fichiers temporaires.

Retourne :
    (frames_uint8, info_dict)
      frames_uint8 : (T, H, W) uint8 gris  — backscan si disponible,
                     sinon image masquée/rognée
      info_dict    : dict issu de info.json (crop + paramètres backscan),
                     ou None si le fichier n'existe pas
"""

import json
import os
import shutil
import sys
import tempfile

import cv2
import numpy as np

from starhe_plugin.utils.go_print import go_print


# ── Calcul déterministe des paramètres géométriques backscan ─────────────────
def _compute_lossless_backscan_params(
    frames_rgb: np.ndarray,
) -> "dict | None":
    """
    Recalcule les paramètres géométriques du backscan directement depuis les
    frames RGB originales (sans codec vidéo lossy), garantissant des résultats
    identiques sur macOS (ARM/Accelerate) et Windows (x86/MKL).

    Reproduit l'algorithme de prepUS.removeLayoutFile :
      1. Conversion RGB→gris
      2. Comptage de valeurs uniques par pixel (vectorisé numpy, sans sonocrop)
      3. Seuillage automatique + opérations morphologiques identiques
      4. find_linear_fov (HoughLines) → (xoffset, yoffset, rc, theta_c, dc)

    Retourne un dict {"backscan": {...}, "crop": {...}} ou None si échec.
    """
    from scipy.ndimage import binary_fill_holes
    from prepUS.utils import keep_largest_component, sync_halves, crop_single_object
    from prepUS.backscan import find_linear_fov

    T, H, W, _ = frames_rgb.shape

    # ── 1. Conversion RGB→gris (identique à sonocrop.vid.loadvideo) ──────────
    v_gray = np.stack(
        [cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2GRAY) for f in frames_rgb],
        axis=0,
    )  # (T, H, W) uint8

    # ── 2. Nombre de valeurs grises uniques par position spatiale ─────────────
    # Équivalent de : u[i] = np.apply_along_axis(vid.countUniquePixels, 0, v[:, i, :])
    # Après tri temporel, on compte les changements consécutifs → nb valeurs uniques.
    # Entièrement vectorisé, déterministe sur ARM et x86.
    sorted_v = np.sort(v_gray, axis=0)  # (T, H, W) uint8 — trié le long du temps
    u = np.ones((H, W), dtype=np.uint8)
    for t in range(1, T):
        u += (sorted_v[t] != sorted_v[t - 1]).astype(np.uint8)
    u_avg = u / T

    # ── 3. Seuil automatique (même formule que prepUS) ────────────────────────
    _, bin_edges = np.histogram(u_avg, bins=20)
    thresh = float(bin_edges[3])

    # ── 4. Masque binaire + opérations morphologiques ─────────────────────────
    mask_img     = (u_avg > thresh).astype(np.uint8)
    mask_largest = keep_largest_component(mask_img)
    mask_mirror  = sync_halves(np.copy(mask_largest))
    bool_mask    = binary_fill_holes((mask_mirror / 255).astype(bool))
    bool_mask    = (bool_mask * 255).astype(np.uint8)
    kernel       = np.ones((3, 3), np.uint8)
    denoised     = cv2.morphologyEx(bool_mask, cv2.MORPH_OPEN, kernel)
    denoised     = cv2.morphologyEx(denoised, cv2.MORPH_CLOSE, kernel)
    bool_mask    = (denoised / 255).astype(bool)

    cropped_mask, ymin, ymax, xmin, xmax = crop_single_object(np.copy(bool_mask))

    # ── 5. Détection des bords du cône US (HoughLines) ───────────────────────
    params = find_linear_fov((cropped_mask * 255).astype(np.uint8), threshold=100)
    if params is None:
        return None

    xoffset, yoffset, rc, theta_c, dc = params
    return {
        "backscan": {
            "xoffset": float(xoffset),
            "yoffset": float(yoffset),
            "rc":      float(rc),
            "theta_c": float(theta_c),
            "dc":      float(dc),
        },
        "crop": {
            "ymin": int(ymin),
            "ymax": int(ymax),
            "xmin": int(xmin),
            "xmax": int(xmax),
        },
    }


# ── Chemin vers le package prepUS vendorisé (inclus dans le projet) ────────────
# Priorité 1 : prepUS déjà installé dans le venv (pip install third_party/prepUS)
# Priorité 2 : source vendorisée dans third_party/prepUS/ (fallback sys.path)
_VENDOR_PREPUS = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),   # starhe_plugin/dicom/
        "..", "..", "..", "..",       # → racine du dépôt (PLUGIN1-MEDomics/)
        "third_party", "prepUS",
    )
)


def _ensure_importable() -> None:
    """
    Vérifie que prepUS est importable.
    Tente d'abord l'import normal (venv), puis ajoute third_party/prepUS
    au sys.path si nécessaire.
    """
    try:
        from prepUS.cli import removeLayoutFile  # noqa: F401
        return
    except ImportError:
        pass

    # Fallback : code source vendorisé dans third_party/prepUS/
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
        "  Dépendances requises : sonocrop, fire, rich, scipy\n"
        "  (run_tkinter.ps1 s'en charge automatiquement)"
    )


def preprocess_with_prepus(
    frames: np.ndarray,
    fps: float = 22.0,
    thresh: float = -1.0,
    back_scan_conversion: bool = True,
    backscan_width: int = 512,
    backscan_height: int = 512,
) -> tuple[np.ndarray, np.ndarray | None, dict | None]:
    """
    Applique le prétraitement prepUS (removeLayout + backscan optionnel)
    sur un clip DICOM fourni sous forme de tableau numpy.

    Paramètres
    ----------
    frames             : np.ndarray  (T, H, W, 3) uint8 RGB
    fps                : fréquence d'images du clip (pour l'export MP4 intermédiaire)
    thresh             : seuil de variabilité temporelle ; -1 = détection automatique
    back_scan_conversion : active la conversion scan inverse (backscan)
    backscan_width / backscan_height : dimensions de l'image backscan en sortie

    Retourne
    --------
    preprocessed_frames : np.ndarray  (T, H', W') uint8 niveaux de gris
        backscan si ``back_scan_conversion=True``, sinon image masquée/rognée
    info_dict : dict | None
        Contenu du fichier ``info.json`` produit par prepUS :
        ``"crop"`` (ymin, ymax, xmin, xmax), ``"original_shape"``,
        ``"threshold"``, ``"backscan"`` (paramètres géométriques).

    Lève
    ----
    ImportError  si prepUS / sonocrop ne sont pas installés.
    RuntimeError si removeLayoutFile échoue ou retourne une vidéo vide.
    """
    _ensure_importable()
    from prepUS.cli import removeLayoutFile  # type: ignore[import]

    if frames.ndim != 4 or frames.shape[3] != 3:
        raise ValueError(f"frames doit être (T, H, W, 3), reçu {frames.shape}")

    T, H, W, _ = frames.shape
    work_dir = tempfile.mkdtemp(prefix="starhe_prepus_")
    go_print("info", f"prepus_bridge: répertoire temporaire → {work_dir}")

    try:
        # ── 1. Exporter les frames numpy vers un MP4 temporaire ───────────────
        tmp_mp4 = os.path.join(work_dir, "input.mp4")
        fourcc  = cv2.VideoWriter_fourcc(*"mp4v")
        writer  = cv2.VideoWriter(tmp_mp4, fourcc, fps, (W, H))
        for f in frames:
            bgr = cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2BGR)
            writer.write(bgr)
        writer.release()
        go_print("info", f"prepus_bridge: {T} frames exportés → {os.path.basename(tmp_mp4)}")

        # ── 2. Appel de l'API prepUS : removeLayoutFile ───────────────────────
        out_dir = os.path.join(work_dir, "out")
        go_print("info", "prepus_bridge: removeLayoutFile en cours…")
        result = removeLayoutFile(
            input_file=tmp_mp4,
            output_dir=out_dir,
            thresh=thresh,
            back_scan_conversion=back_scan_conversion,
            backscan_width=backscan_width,
            backscan_height=backscan_height,
            save_mask=False,
            save_cropped_mask=True,
            save_info=True,
        )
        if result is None:
            raise RuntimeError(
                "prepUS.removeLayoutFile a échoué (retourné None). "
                "Essayez avec un seuil différent (thresh) ou "
                "désactivez la conversion backscan."
            )
        go_print("success", f"prepus_bridge: removeLayoutFile → {result}")

        # ── 3. Lire info.json ─────────────────────────────────────────────────
        info: dict | None = None
        info_path = os.path.join(out_dir, "info.json")
        if os.path.exists(info_path):
            with open(info_path, encoding="utf-8") as fh:
                info = json.load(fh)

        # ── 3b. Surcharge déterministe de la géométrie backscan ───────────────
        # prepUS calcule la géométrie du cône US (xoffset, yoffset, rc, theta_c,
        # dc) depuis la vidéo MP4 compressée (codec mp4v, lossy). Le décodage
        # mp4v diffère selon la plateforme (CoreVideo/macOS vs
        # MediaFoundation/Windows) : ±1–2 niveaux de gris → masque statique
        # légèrement différent → HoughLines différent → paramètres différents →
        # backscan in-memory différent → scores IA différents.
        #
        # Fix : on recalcule le masque et la géométrie directement depuis les
        # frames numpy brutes (sans codec), puis on écrase info["backscan"] et
        # info["crop"] avec des valeurs déterministes et on régénère mask.png en
        # cohérence.
        if back_scan_conversion and info is not None and "backscan" in info:
            try:
                from prepUS.backscan import pre_dsc_image_vectorized as _pdv_geo
                det = _compute_lossless_backscan_params(frames)
                if det is not None:
                    info["backscan"].update(det["backscan"])
                    info["crop"].update(det["crop"])
                    # Régénère mask.png cohérent avec la nouvelle géométrie
                    bsc = det["backscan"]
                    c   = det["crop"]
                    first_gray = cv2.cvtColor(
                        frames[0].astype(np.uint8), cv2.COLOR_RGB2GRAY
                    )
                    first_crop = first_gray[c["ymin"]:c["ymax"], c["xmin"]:c["xmax"]]
                    mask_det   = _pdv_geo(
                        first_crop,
                        bsc["dc"], bsc["rc"], bsc["theta_c"],
                        bsc["yoffset"], bsc["xoffset"],
                        backscan_width, backscan_height,
                        get_IUSI_FOV=True,
                    )
                    cv2.imwrite(os.path.join(out_dir, "mask.png"), mask_det)
                    go_print("info",
                             "prepus_bridge: géométrie backscan recalculée (déterministe)")
            except Exception as exc:
                go_print("warning",
                         f"prepus_bridge: recalcul géométrie échoué ({exc}) "
                         "— paramètres prepUS conservés")

        # ── 4. Reconstruire les frames de sortie en mémoire (sans décodage lossy) ──
        # prepUS écrit ses résultats en MP4 (codec mp4v, lossy).
        # Relire ce fichier via VideoCapture introduit des artefacts de décodage
        # différents selon la plateforme (CoreVideo/macOS vs MF/Windows) → ±1-2
        # niveaux par pixel → différences de score cross-plateforme.
        #
        # Solution : quand les paramètres géométriques sont dans info.json, on
        # recalcule les frames backscan directement depuis les pixels numpy bruts
        # (pre_dsc_image_vectorized, identique sur toutes les plateformes).
        # Quand info.json est absent, on retombe sur la lecture vidéo en fallback.
        backscan_mp4 = os.path.join(out_dir, "backscan_video.mp4")
        video_mp4    = os.path.join(out_dir, "video.mp4")

        def _read_video(path: str) -> "np.ndarray | None":
            cap = cv2.VideoCapture(path)
            buf: list[np.ndarray] = []
            while True:
                ok, frm = cap.read()
                if not ok:
                    break
                buf.append(cv2.cvtColor(frm, cv2.COLOR_BGR2GRAY) if frm.ndim == 3 else frm)
            cap.release()
            return np.stack(buf, axis=0) if buf else None

        def _backscan_inmemory(frames_rgb: np.ndarray,
                               bsc_info: dict, crop_info: dict,
                               bsc_w: int, bsc_h: int) -> "np.ndarray":
            """
            Recalcule le backscan en mémoire depuis les pixels numpy bruts.
            Équivalent exact de ce que prepUS écrit dans backscan_video.mp4,
            mais sans passer par un codec vidéo lossy.
            """
            from prepUS.backscan import pre_dsc_image_vectorized
            from prepUS.cli import vid  # noqa: F401 – sonocrop.vid.applyMask

            xoffset = bsc_info["xoffset"]
            yoffset = bsc_info["yoffset"]
            rc      = bsc_info["rc"]
            theta_c = bsc_info["theta_c"]
            dc      = bsc_info["dc"]

            ymin = int(crop_info["ymin"])
            ymax = int(crop_info["ymax"])
            xmin = int(crop_info["xmin"])
            xmax = int(crop_info["xmax"])

            # Charge le masque pre_dsc (mask.png produit par prepUS)
            mask_path = os.path.join(out_dir, "mask.png")
            mask_valid = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE) if os.path.exists(mask_path) else None

            result: list[np.ndarray] = []
            for frame_rgb in frames_rgb:
                gray  = cv2.cvtColor(frame_rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
                crop  = gray[ymin:ymax, xmin:xmax]
                if mask_valid is not None:
                    m = (mask_valid / 255.0).astype(bool)
                    from sonocrop import vid as _vid
                    crop = _vid.applyMask(crop[np.newaxis], m)[0]
                bsc = pre_dsc_image_vectorized(
                    crop, dc, rc, theta_c, yoffset, xoffset, bsc_w, bsc_h
                )
                result.append(bsc.astype(np.uint8))
            return np.stack(result, axis=0)

        crop_only_array: "np.ndarray | None" = None

        if os.path.exists(backscan_mp4) and info is not None and "backscan" in info:
            # Recalcul en mémoire — déterministe sur toutes les plateformes
            go_print("info", "prepus_bridge: recalcul backscan in-memory (déterministe)…")
            try:
                out_array = _backscan_inmemory(
                    frames,
                    info["backscan"],
                    info["crop"],
                    backscan_width,
                    backscan_height,
                )
                # crop_only : frames rognées sans backscan (lecture vidéo acceptée ici
                # car utilisées uniquement pour l'affichage, pas pour l'inférence IA)
                if os.path.exists(video_mp4):
                    crop_only_array = _read_video(video_mp4)
                source = "backscan-inmemory"
            except Exception as exc:
                go_print("warning",
                         f"prepus_bridge: recalcul in-memory échoué ({exc}) "
                         "— fallback lecture vidéo.")
                out_array = _read_video(backscan_mp4)
                if out_array is None:
                    raise RuntimeError("backscan_video.mp4 est vide ou illisible.")
                if os.path.exists(video_mp4):
                    crop_only_array = _read_video(video_mp4)
                source = "backscan-video (fallback)"
        elif os.path.exists(backscan_mp4):
            out_array = _read_video(backscan_mp4)
            if out_array is None:
                raise RuntimeError("backscan_video.mp4 est vide ou illisible.")
            if os.path.exists(video_mp4):
                crop_only_array = _read_video(video_mp4)
            source = "backscan-video (info.json absent)"

        elif os.path.exists(video_mp4):
            out_array = _read_video(video_mp4)
            if out_array is None:
                raise RuntimeError("video.mp4 est vide ou illisible.")
            source = "masqué/rogné"

        elif info is not None and "crop" in info:
            # backscan=False : prepUS ne sauvegarde pas de vidéo →
            # crop rectangulaire depuis info.json + masque binaire pour
            # supprimer les annotations UI statiques dans la zone rognée.
            c = info["crop"]
            ymin, ymax = int(c["ymin"]), int(c["ymax"])
            xmin, xmax = int(c["xmin"]), int(c["xmax"])
            go_print("info",
                     f"prepus_bridge: backscan off — crop y=[{ymin}:{ymax}] x=[{xmin}:{xmax}]")

            cropped_rgb = frames[:, ymin:ymax, xmin:xmax, :].copy()

            # ── Charge et applique le masque prepUS (pixels dynamiques = zone US) ──
            # prepUS sauve « cropped_mask.png » quand save_cropped_mask=True.
            # Le masque est blanc (255) sur la zone échographique, noir (0) sur les
            # pixels statiques (annotations, texte, règles de la machine).
            go_print("info",
                     f"prepus_bridge: fichiers dans out_dir: {sorted(os.listdir(out_dir))}")
            mask_applied = False
            for mask_name in ("cropped_mask.png", "mask.png", "cropped_mask.jpg"):
                mask_path = os.path.join(out_dir, mask_name)
                if not os.path.exists(mask_path):
                    continue
                m = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
                if m is None:
                    continue
                fh, fw = cropped_rgb.shape[1], cropped_rgb.shape[2]
                if m.shape != (fh, fw):
                    m = cv2.resize(m, (fw, fh), interpolation=cv2.INTER_NEAREST)
                # 1 = garder (zone US dynamique), 0 = zéro (UI statique)
                mask_bin = (m > 0).astype(np.uint8)           # (H, W)
                cropped_rgb = (
                    cropped_rgb * mask_bin[np.newaxis, :, :, np.newaxis]
                ).astype(np.uint8)
                go_print("info",
                         f"prepus_bridge: masque '{mask_name}' appliqué ({m.shape})")
                mask_applied = True
                break

            if not mask_applied:
                go_print("warning",
                         "prepus_bridge: aucun masque trouvé — crop seul (annota"
                         "tions UI possiblement visibles).")

            out_array = np.stack([
                cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2GRAY) for f in cropped_rgb
            ], axis=0)
            source = "crop" + (" + masque" if mask_applied else "") + " (backscan off)"

        else:
            raise FileNotFoundError(
                f"Aucune vidéo de sortie trouvée dans {out_dir} "
                "et info.json absent ou sans coordonnées de crop. "
                "Fichiers présents : " + ", ".join(os.listdir(out_dir))
            )

        extra = f" + crop_only {crop_only_array.shape}" if crop_only_array is not None else ""
        go_print("info", f"prepus_bridge: sortie {out_array.shape} ({source}){extra}")
        return out_array, crop_only_array, info

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        go_print("info", "prepus_bridge: fichiers temporaires supprimés.")
