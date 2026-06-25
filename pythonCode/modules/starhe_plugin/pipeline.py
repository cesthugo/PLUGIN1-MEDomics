"""
pipeline.py — Orchestrateur du flux de traitement STARHE
=========================================================
Enchaîne toutes les étapes :
  1. Chargement DICOM
  2. Extraction des frames
  3. Anonymisation
  4. Prétraitement prepUS (uniquement si DETECT actif)
  5. Inférence STARHE-RISK  (sur frames DICOM brutes — distribution d'entraînement)
  6. Inférence STARHE-DETECT (sur frames croppées prepUS)
  7. Sauvegarde MongoDB

Point d'entrée appelé par le blueprint Go.

Notes sur le preprocessing
--------------------------
STARHE-RISK (C3D) : entraîné sur les video.mp4 de prepUS = éventail rogné,
niveaux de gris, codec mp4v. → reçoit crop_only_frames (T, H_crop, W_crop, 3)
avec R=G=B=gris.

STARHE-DETECT (RTMDet) : entraîné sur les cropped_videos de prepUS (éventail
rogné, UI retirée). → reçoit crop_only_frames (T, H_crop, W_crop, 3).
Remappage : simple offset (xmin/ymin) pour revenir dans l'espace DICOM.
"""

import threading
import cv2
import numpy as np

from starhe_plugin.dicom.reader         import load_dicom, extract_frames, frame_to_uint8
from starhe_plugin.dicom.weasis_bridge  import weasis_available, frames_via_weasis
from starhe_plugin.dicom.prepus_bridge  import preprocess_with_prepus, preprocess_with_prepus_inmem, map_detections_to_dicom_coords
from starhe_plugin.config import PREPUS_BYPASS_MP4, USE_WEASIS_EXPORT
from starhe_plugin.dicom.anonymizer    import anonymize
from starhe_plugin.ai.starhe_risk      import STARHERiskModel
from starhe_plugin.ai.starhe_detect    import STARHEDetectModel
from starhe_plugin.db.mongo_client     import save_result
from starhe_plugin.utils.go_print      import go_print, go_progress, go_result
from starhe_plugin.config              import DETECT_EVERY_N



def run_pipeline(dicom_path: str,
                 anon_mode: str = "hash",
                 run_risk: bool = True,
                 run_detection: bool = True,
                 back_scan_conversion: bool = True,
                 backscan_width: int = 512,
                 backscan_height: int = 512,
                 analysis_mode: str | None = None) -> dict:
    """
    Exécute le pipeline complet STARHE sur un fichier DICOM.

    Paramètres :
      dicom_path           : chemin absolu du fichier .dcm
      anon_mode            : "hash" | "remove" | "none"
      run_risk             : si False, saute STARHE-RISK (plus rapide, detection seule)
      run_detection        : si False, saute STARHE-DETECT (plus rapide ; désactive aussi prepUS)
      back_scan_conversion : active la conversion scan inverse prepUS (uniquement pour DETECT)
      backscan_width/height: dimensions de sortie du backscan (défaut 512×512)

    Retourne un dict de résultats qui est aussi émis via go_result().
    """
    TOTAL_STEPS = 6
    step = 0

    # ── 1. Chargement ─────────────────────────────────────────────────────────
    go_progress(step := step + 1, TOTAL_STEPS, "Chargement DICOM…")
    ds = load_dicom(dicom_path)

    # Extraire le FPS réel depuis les tags DICOM (priorité descendante) :
    #   1. RecommendedDisplayFrameRate (0008,2144) — entier, source la plus fiable
    #      (correspond aux fps des MP4 de référence pour 46/49 patients du dataset).
    #   2. CineRate (0018,0040) — fps direct.
    #   3. FrameTime (0018,1063) — ms/frame → fps = 1000/FrameTime.
    _rdp = float(getattr(ds, "RecommendedDisplayFrameRate", 0.0))
    _cr  = float(getattr(ds, "CineRate", 0.0))
    _ft  = float(getattr(ds, "FrameTime", 0.0))
    if _rdp > 0:
        dicom_fps, _fps_src = _rdp, f"RecommendedDisplayFrameRate={_rdp}"
    elif _cr > 0:
        dicom_fps, _fps_src = _cr, f"CineRate={_cr}"
    elif _ft > 0:
        dicom_fps, _fps_src = 1000.0 / _ft, f"FrameTime={_ft} ms"
    else:
        raise RuntimeError(
            "Impossible de déterminer le FPS du fichier DICOM : "
            "aucun tag RecommendedDisplayFrameRate / CineRate / FrameTime trouvé."
        )
    go_print("info", f"FPS DICOM : {dicom_fps:.2f} fps ({_fps_src})")

    # ── 2. Anonymisation ──────────────────────────────────────────────────────
    go_progress(step := step + 1, TOTAL_STEPS, "Anonymisation des métadonnées…")
    if anon_mode != "none":
        ds = anonymize(ds, mode=anon_mode)

    # ── 3. Extraction des frames ──────────────────────────────────────────────
    go_progress(step := step + 1, TOTAL_STEPS, "Extraction des frames…")

    frames_rgb: np.ndarray | None = None

    # Chemin préféré : weasis-dcm2png (Modality LUT + VOI LUT comme à
    # l'entraînement). Fallback automatique vers pydicom si JAR/JVM absent
    # ou si la transfer syntax n'est pas supportée par weasis (ex. JPEG 2000).
    if USE_WEASIS_EXPORT and weasis_available():
        try:
            frames_rgb, weasis_fps = frames_via_weasis(dicom_path)
            if weasis_fps > 0:
                dicom_fps = weasis_fps   # privilégier la valeur lue par weasis
        except Exception as exc:
            go_print("warning",
                     f"weasis-dcm2png a échoué ({exc}) — fallback pydicom")
            frames_rgb = None

    if frames_rgb is None:
        frames_raw  = extract_frames(ds)   # (T, H, W) ou (T, H, W, 3)
        frames_norm = np.stack([frame_to_uint8(f) for f in frames_raw])
        if frames_norm.ndim == 3:
            frames_rgb = np.stack([frames_norm] * 3, axis=-1)   # (T, H, W, 3)
        else:
            frames_rgb = frames_norm   # (T, H, W, 3)

    # ── Préchauffage DETECT en arrière-plan ───────────────────────────────────
    # Le subprocess RTMDet charge le modèle (~3-5 s). On le démarre dès maintenant
    # pour qu'il soit prêt quand on en a besoin, pendant que prepUS + RISK tournent.
    _detect_model_box: list = []
    _detect_exc_box:   list = []

    def _warm_detect():
        try:
            _detect_model_box.append(STARHEDetectModel())
        except Exception as exc:
            _detect_exc_box.append(exc)

    detect_thread: threading.Thread | None = None
    if run_detection:
        detect_thread = threading.Thread(target=_warm_detect, daemon=True)
        detect_thread.start()

    # ── 4. Prétraitement prepUS (crop cône US — pour RISK et DETECT) ─────────
    crop_only_frames = info = None
    if run_detection or run_risk:
        _prepus_fn = preprocess_with_prepus_inmem if PREPUS_BYPASS_MP4 else preprocess_with_prepus
        _mode_tag  = "in-mem numpy" if PREPUS_BYPASS_MP4 else "MP4 roundtrip"
        go_progress(step := step + 1, TOTAL_STEPS,
                    f"Prétraitement prepUS (removeLayout + crop cône US — {_mode_tag})…")
        crop_only_frames, info = _prepus_fn(
            frames_rgb,
            fps=dicom_fps,
            backscan_width=backscan_width,
            backscan_height=backscan_height,
        )
    else:
        go_progress(step := step + 1, TOTAL_STEPS, "prepUS ignoré.")

    # RISK et DETECT : frames crop cône US (niveaux de gris → pseudo-RGB 3 canaux).
    # Identique aux video.mp4 d'entraînement décodés par Decord (R=G=B=gris).
    if crop_only_frames is not None:
        _c = crop_only_frames  # (T, H_crop, W_crop) uint8 gris
        frames_processed_risk = np.stack([_c, _c, _c], axis=-1)  # (T, H_crop, W_crop, 3)
    else:
        frames_processed_risk = frames_rgb

    frames_processed = frames_processed_risk

    roi = None
    if info and "crop" in info:
        c = info["crop"]
        roi = (c["xmin"], c["ymin"], c["xmax"], c["ymax"])

    # ── 5. STARHE-RISK ────────────────────────────────────────────────────────
    risk_result: dict | None = None
    if run_risk:
        go_progress(step := step + 1, TOTAL_STEPS, "Inférence STARHE-RISK (C3D)…")
        risk_model  = STARHERiskModel()
        risk_result = risk_model.predict(frames_processed_risk)
    else:
        step += 1
        go_progress(step, TOTAL_STEPS, "STARHE-RISK ignoré (run_risk=False).")

    # ── 6. STARHE-DETECT (échantillonnage temporel + propagation) ────────────
    # Identique à l'implémentation de référence (prototype_tkinter.py) :
    #   - inférence sur les frames samplées (stride=DETECT_EVERY_N)
    #   - propagation directe des détections aux frames intermédiaires
    #     [i, i+1, ..., i+stride-1] (pas de deuxième passe d'inférence)
    # predict_batch utilise déjà DETECT_SCORE_THRESHOLD en interne.
    n_frames_total = len(frames_processed)
    detections_per_frame: list[list[dict]] = [[] for _ in range(n_frames_total)]

    if run_detection:
        stride     = max(1, DETECT_EVERY_N)
        sampled    = list(range(0, n_frames_total, stride))
        n_analysed = len(sampled)
        go_progress(step := step + 1, TOTAL_STEPS,
                    f"Inférence STARHE-DETECT ({n_analysed}/{n_frames_total} frames, stride={stride})…")

        # Attendre que le subprocess soit prêt (il a démarré pendant prepUS + RISK)
        detect_thread.join()
        if _detect_exc_box:
            raise _detect_exc_box[0]
        detect_model = _detect_model_box[0]

        with detect_model:
            bs = detect_model.batch_size
            go_print("info",
                     f"DETECT : batch_size={bs}, {n_analysed} sampled frames à analyser.")

            for b_start in range(0, n_analysed, bs):
                batch_idx    = sampled[b_start:b_start + bs]
                batch_frames = [frames_processed[i] for i in batch_idx]
                batch_dets   = detect_model.predict_batch(batch_frames)

                for idx, frame_dets in zip(batch_idx, batch_dets):
                    # Propagation temporelle identique à Tkinter :
                    # copier les détections sur toutes les frames [idx, idx+stride).
                    for j in range(idx, min(idx + stride, n_frames_total)):
                        detections_per_frame[j] = frame_dets

                done  = b_start + len(batch_idx)
                n_det = sum(1 for d in detections_per_frame if d)
                if done % 5 == 0 or done >= n_analysed:
                    go_print("info",
                             f"DETECT : {done}/{n_analysed} sampled frames —"
                             f" {n_det} frames avec détection(s).")

            n_det_final = sum(1 for d in detections_per_frame if d)
            go_print("success",
                     f"DETECT terminé : {n_det_final}/{n_frames_total} frames avec lésion(s).")
    else:
        step += 1
        go_progress(step, TOTAL_STEPS, "STARHE-DETECT ignoré (run_detection=False).")

    # ── 7. Remappage crop → espace DICOM original ──────────────────────────────
    # RTMDet prédit des bboxes dans l'espace crop_only → simple offset (xmin, ymin).
    detections_per_frame = map_detections_to_dicom_coords(
        detections_per_frame,
        info,
    )
    if any(d for d in detections_per_frame):
        go_print("info", "Détections remappées vers l'espace original.")

    # ── 8. Sauvegarde MongoDB ─────────────────────────────────────────────────
    # Calcule analysis_mode depuis les options si non fourni explicitement
    if analysis_mode is None:
        r = "1" if run_risk else "0"
        d = "1" if run_detection else "0"
        b = "1" if back_scan_conversion else "0"
        analysis_mode = f"risk={r},detect={d},backscan={b},anon={anon_mode}"

    doc_id = save_result(
        file_path            = dicom_path,
        num_frames           = n_frames_total,
        roi                  = list(roi) if roi else [],
        risk                 = risk_result,
        detections_per_frame = detections_per_frame,
        anon_mode            = anon_mode,
        analysis_mode        = analysis_mode,
    )

    output = {
        "doc_id"              : doc_id,
        "num_frames"          : n_frames_total,
        "roi"                 : list(roi) if roi else [],
        "detections_per_frame": detections_per_frame,
    }
    if risk_result is not None:
        output["risk"] = risk_result
    go_result(output)
    return output


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m starhe_plugin.pipeline",
        description="Lance le pipeline STARHE complet sur un fichier DICOM.",
    )
    parser.add_argument("dicom_path",
                        help="Chemin absolu du fichier .dcm")
    parser.add_argument("--anon_mode", default="hash",
                        choices=["hash", "remove", "none"],
                        help="Mode d'anonymisation DICOM (défaut : hash)")
    parser.add_argument("--no_risk", action="store_true",
                        help="Désactiver STARHE-RISK (classification C3D)")
    parser.add_argument("--no_detection", action="store_true",
                        help="Désactiver STARHE-DETECT (plus rapide)")
    parser.add_argument("--no_backscan", action="store_true",
                        help="Désactiver la conversion scan inverse prepUS")
    parser.add_argument("--backscan_width",  type=int, default=512,
                        help="Largeur de sortie backscan (défaut : 512)")
    parser.add_argument("--backscan_height", type=int, default=512,
                        help="Hauteur de sortie backscan (défaut : 512)")
    parser.add_argument("--analysis_mode", default=None,
                        help="Clé de cache MongoDB (calculée automatiquement si absente)")

    args = parser.parse_args()
    try:
        run_pipeline(
            dicom_path          = args.dicom_path,
            anon_mode           = args.anon_mode,
            run_risk            = not args.no_risk,
            run_detection       = not args.no_detection,
            back_scan_conversion= not args.no_backscan,
            backscan_width      = args.backscan_width,
            backscan_height     = args.backscan_height,
            analysis_mode       = args.analysis_mode,
        )
    except Exception as exc:
        go_print("error", f"Pipeline échoué : {exc}")
        sys.exit(1)
