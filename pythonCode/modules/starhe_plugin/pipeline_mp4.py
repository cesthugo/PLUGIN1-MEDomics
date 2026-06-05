"""
pipeline_mp4.py — Pipeline STARHE pour fichiers MP4 directs
============================================================
Identique à pipeline.py mais sans chargement DICOM ni anonymisation.
Les frames sont lues directement depuis un fichier .mp4 via OpenCV.

Point d'entrée appelé par le serveur Go (handlers_mp4.go).
"""

import threading
import cv2
import numpy as np

from starhe_plugin.dicom.prepus_bridge import preprocess_with_prepus, map_detections_to_dicom_coords
from starhe_plugin.ai.starhe_risk      import STARHERiskModel
from starhe_plugin.ai.starhe_detect    import STARHEDetectModel
from starhe_plugin.db.mongo_client     import save_result
from starhe_plugin.utils.go_print      import go_print, go_progress, go_result
from starhe_plugin.config              import DETECT_EVERY_N


def run_pipeline_mp4(
    mp4_path: str,
    run_risk: bool = True,
    run_detection: bool = True,
    back_scan_conversion: bool = True,
    backscan_width: int = 512,
    backscan_height: int = 512,
    analysis_mode: str | None = None,
) -> dict:
    """
    Exécute le pipeline STARHE sur un fichier MP4.

    Étapes :
      1. Lecture MP4 (cv2.VideoCapture)
      2. Prétraitement prepUS
      3. Inférence STARHE-RISK
      4. Inférence STARHE-DETECT
      5. Sauvegarde MongoDB

    Retourne un dict de résultats (émis aussi via go_result).
    """
    TOTAL_STEPS = 5
    step = 0

    # ── 1. Lecture MP4 ────────────────────────────────────────────────────────
    go_progress(step := step + 1, TOTAL_STEPS, "Lecture du fichier MP4…")

    cap = cv2.VideoCapture(mp4_path)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir le fichier MP4 : {mp4_path}")

    raw_fps = cap.get(cv2.CAP_PROP_FPS)
    fps = raw_fps if raw_fps > 0 else 22.0
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    h_orig  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w_orig  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    go_print("info", f"MP4 : {fps:.2f} fps, {n_total} frames, {w_orig}×{h_orig}")

    raw_frames: list[np.ndarray] = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        raw_frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()

    if not raw_frames:
        raise RuntimeError("Le fichier MP4 ne contient aucune frame lisible.")

    # (T, H, W, 3) uint8 RGB — même format que pipeline.py après extraction
    frames_rgb = np.stack(raw_frames)
    go_print("info", f"Frames lues : {len(frames_rgb)}")

    # ── Préchauffage DETECT en arrière-plan (pendant prepUS + RISK) ───────────
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

    # ── 2. Prétraitement prepUS ───────────────────────────────────────────────
    crop_only_frames = info = None
    if run_detection or run_risk:
        go_progress(step := step + 1, TOTAL_STEPS,
                    "Prétraitement prepUS (removeLayout + crop cône US)…")
        crop_only_frames, info = preprocess_with_prepus(
            frames_rgb,
            fps=fps,
            backscan_width=backscan_width,
            backscan_height=backscan_height,
        )
    else:
        step += 1
        go_progress(step, TOTAL_STEPS, "prepUS ignoré.")

    if crop_only_frames is not None:
        _c = crop_only_frames          # (T, H_crop, W_crop) uint8 gris
        frames_processed = np.stack([_c, _c, _c], axis=-1)  # (T, H_crop, W_crop, 3)
    else:
        frames_processed = frames_rgb

    roi = None
    if info and "crop" in info:
        c = info["crop"]
        roi = (c["xmin"], c["ymin"], c["xmax"], c["ymax"])

    # ── 3. STARHE-RISK ────────────────────────────────────────────────────────
    risk_result: dict | None = None
    if run_risk:
        go_progress(step := step + 1, TOTAL_STEPS, "Inférence STARHE-RISK (C3D)…")
        risk_model  = STARHERiskModel()
        risk_result = risk_model.predict(frames_processed)
    else:
        step += 1
        go_progress(step, TOTAL_STEPS, "STARHE-RISK ignoré (run_risk=False).")

    # ── 4. STARHE-DETECT ──────────────────────────────────────────────────────
    n_frames_total = len(frames_processed)
    detections_per_frame: list[list[dict]] = [[] for _ in range(n_frames_total)]

    if run_detection:
        stride     = max(1, DETECT_EVERY_N)
        sampled    = list(range(0, n_frames_total, stride))
        n_analysed = len(sampled)
        go_progress(step := step + 1, TOTAL_STEPS,
                    f"Inférence STARHE-DETECT ({n_analysed}/{n_frames_total} frames, stride={stride})…")

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

    # ── Remappage crop → espace vidéo original ────────────────────────────────
    detections_per_frame = map_detections_to_dicom_coords(detections_per_frame, info)
    if any(d for d in detections_per_frame):
        go_print("info", "Détections remappées vers l'espace original.")

    # ── 5. Sauvegarde MongoDB ─────────────────────────────────────────────────
    if analysis_mode is None:
        r = "1" if run_risk else "0"
        d = "1" if run_detection else "0"
        b = "1" if back_scan_conversion else "0"
        analysis_mode = f"risk={r},detect={d},backscan={b},anon=none,source=mp4"

    doc_id = save_result(
        file_path            = mp4_path,
        num_frames           = n_frames_total,
        roi                  = list(roi) if roi else [],
        risk                 = risk_result,
        detections_per_frame = detections_per_frame,
        anon_mode            = "none",
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
        prog="python -m starhe_plugin.pipeline_mp4",
        description="Lance le pipeline STARHE sur un fichier MP4.",
    )
    parser.add_argument("mp4_path",
                        help="Chemin absolu du fichier .mp4")
    parser.add_argument("--no_risk",       action="store_true",
                        help="Désactiver STARHE-RISK")
    parser.add_argument("--no_detection",  action="store_true",
                        help="Désactiver STARHE-DETECT")
    parser.add_argument("--no_backscan",   action="store_true",
                        help="Désactiver la conversion scan inverse prepUS")
    parser.add_argument("--backscan_width",  type=int, default=512)
    parser.add_argument("--backscan_height", type=int, default=512)
    parser.add_argument("--analysis_mode",   default=None,
                        help="Clé de cache MongoDB (calculée automatiquement si absente)")

    args = parser.parse_args()
    try:
        run_pipeline_mp4(
            mp4_path            = args.mp4_path,
            run_risk            = not args.no_risk,
            run_detection       = not args.no_detection,
            back_scan_conversion= not args.no_backscan,
            backscan_width      = args.backscan_width,
            backscan_height     = args.backscan_height,
            analysis_mode       = args.analysis_mode,
        )
    except Exception as exc:
        go_print("error", f"Pipeline MP4 échoué : {exc}")
        sys.exit(1)
