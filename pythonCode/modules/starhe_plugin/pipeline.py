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

Note sur le preprocessing RISK
--------------------------------
Les MP4 d'entraînement du C3D sont de simples resizes proportionnels du DICOM
original (plein cadre, UI inclus). prepUS n'était PAS appliqué à l'entraînement.
STARHE-RISK reçoit donc les frames DICOM brutes (T, H, W, 3) ; preprocess_clips
gère lui-même le resize + center-crop 112×112 en interne.
prepUS est conservé pour STARHE-DETECT (coordonnées de crop nécessaires au
remappage des bboxes dans l'espace DICOM original).
"""

import threading
import cv2
import numpy as np

from starhe_plugin.dicom.reader        import load_dicom, extract_frames, frame_to_uint8
from starhe_plugin.dicom.prepus_bridge import preprocess_with_prepus, map_detections_to_dicom_coords
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

    # ── 2. Anonymisation ──────────────────────────────────────────────────────
    go_progress(step := step + 1, TOTAL_STEPS, "Anonymisation des métadonnées…")
    if anon_mode != "none":
        ds = anonymize(ds, mode=anon_mode)

    # ── 3. Extraction des frames ──────────────────────────────────────────────
    go_progress(step := step + 1, TOTAL_STEPS, "Extraction des frames…")
    frames_raw = extract_frames(ds)   # (T, H, W) ou (T, H, W, 3)

    # Normalise → (T, H, W, 3) uint8 RGB (format attendu par preprocess_with_prepus)
    frames_norm = np.stack([frame_to_uint8(f) for f in frames_raw])   # (T, H, W) uint8
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
    # Les données d'entraînement du C3D sont les video.mp4 de prepUS (éventail
    # rogné, UI retirée, niveaux de gris). À l'inférence, RISK et DETECT reçoivent
    # tous deux les frames crop_only (cône rogné) pour aligner la distribution.
    backscan_frames = crop_only_frames = info = None
    if run_detection or run_risk:
        go_progress(step := step + 1, TOTAL_STEPS,
                    "Prétraitement prepUS (removeLayout + crop cône US)…")
        backscan_frames, crop_only_frames, info = preprocess_with_prepus(
            frames_rgb,
            back_scan_conversion=back_scan_conversion,
            backscan_width=backscan_width,
            backscan_height=backscan_height,
        )
    else:
        go_progress(step := step + 1, TOTAL_STEPS, "prepUS ignoré.")

    # RISK : frames crop cône US (niveaux de gris → pseudo-RGB 3 canaux).
    # crop_only_frames = (T, H_crop, W_crop) uint8 gris, même format que les
    # video.mp4 d'entraînement décodés par Decord (R=G=B=gris).
    # Fallback : frames DICOM brutes si prepUS n'a pas été exécuté.
    if crop_only_frames is not None:
        _c = crop_only_frames  # (T, H_crop, W_crop) uint8 gris
        frames_processed_risk = np.stack([_c, _c, _c], axis=-1)  # (T, H_crop, W_crop, 3)
    else:
        frames_processed_risk = frames_rgb  # fallback brut (run_risk=True, run_detection=False, prepUS off)

    # DETECT : crop polaire prepUS → nécessaire pour remappe bboxes vers espace DICOM
    # Quand run_detection=False : frames_processed sert uniquement à n_frames_total.
    processed_detect = (
        crop_only_frames if crop_only_frames is not None else
        backscan_frames  if backscan_frames  is not None else
        frames_rgb[..., 0]  # fallback grayscale
    )
    frames_processed = (
        np.stack([processed_detect, processed_detect, processed_detect], axis=-1)
        if run_detection else frames_rgb
    )

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

    # ── 7. Remappage crop → espace DICOM original ─────────────────────────────
    # RTMDet reçoit les frames crop_only (espace polaire rogné) : ses bboxes sont
    # dans cet espace. Il faut ajouter l'offset de crop (xmin, ymin) pour obtenir
    # les coordonnées dans l'image DICOM originale affichée.
    # On passe un info réduit à "crop" pour forcer le décalage simple (pas l'inversion
    # polaire, qui s'appliquerait si la clé "backscan" était présente).
    crop_only_info = {"crop": info["crop"]} if info and "crop" in info else info
    detections_per_frame = map_detections_to_dicom_coords(
        detections_per_frame,
        crop_only_info,
        bsc_w=backscan_width,
        bsc_h=backscan_height,
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
