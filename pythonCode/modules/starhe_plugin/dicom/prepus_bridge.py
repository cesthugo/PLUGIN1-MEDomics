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


# ── Localisation du package prepUS (chemin relatif au projet) ──────────────────
_PREPUS_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),              # starhe_plugin/dicom/
        "..", "..", "..", "..",                  # → F:\STAGE\PROJET
        "..", "Pre-processing ultrasound", "prepus",
    )
)


def _ensure_importable() -> None:
    """Vérifie que prepUS est importable ; sinon lève ImportError avec message clair."""
    try:
        from prepUS.cli import removeLayoutFile  # noqa: F401
        return
    except ImportError:
        pass

    # Tentative d'ajout du chemin local au sys.path
    if os.path.isdir(_PREPUS_ROOT) and _PREPUS_ROOT not in sys.path:
        sys.path.insert(0, _PREPUS_ROOT)
        try:
            from prepUS.cli import removeLayoutFile  # noqa: F401
            return
        except ImportError:
            pass

    raise ImportError(
        "Le package prepUS est introuvable.\n"
        f"  Chemin cherché : {_PREPUS_ROOT}\n"
        "  Installation : pip install <chemin_vers_prepus>\n"
        "  Dépendances requises : sonocrop, fire, rich, scipy"
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

        # ── 4. Lire la/les vidéo(s) de sortie ──────────────────────────────────
        # Quand backscan=True, prepUS produit DEUX vidéos :
        #   - backscan_video.mp4  (conversion scan inverse 512×512)
        #   - video.mp4           (crop seulement, taille variable)
        # Quand backscan=False, aucune vidéo n'est produite → crop depuis info.json.
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

        crop_only_array: "np.ndarray | None" = None

        if os.path.exists(backscan_mp4):
            out_array = _read_video(backscan_mp4)
            if out_array is None:
                raise RuntimeError("backscan_video.mp4 est vide ou illisible.")
            if os.path.exists(video_mp4):
                crop_only_array = _read_video(video_mp4)
            source = "backscan"

        elif os.path.exists(video_mp4):
            out_array = _read_video(video_mp4)
            if out_array is None:
                raise RuntimeError("video.mp4 est vide ou illisible.")
            source = "masqué/rogné"

        elif info is not None and "crop" in info:
            # backscan=False : pas de vidéo prepUS → crop depuis les coordonnées info.json
            c = info["crop"]
            ymin, ymax = int(c["ymin"]), int(c["ymax"])
            xmin, xmax = int(c["xmin"]), int(c["xmax"])
            go_print("info",
                     f"prepus_bridge: backscan off — crop y=[{ymin}:{ymax}] x=[{xmin}:{xmax}]")
            cropped_rgb = frames[:, ymin:ymax, xmin:xmax, :]
            out_array = np.stack([
                cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2GRAY) for f in cropped_rgb
            ], axis=0)
            source = "crop-manuel (backscan off)"

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
