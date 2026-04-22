"""
pipeline.py — Orchestrateur du flux de traitement STARHE
=========================================================
Enchaîne toutes les étapes :
  1. Chargement DICOM
  2. Extraction des frames
  3. Anonymisation
  4. Prétraitement prepUS (removeLayout + backscan)
  5. Inférence STARHE-RISK
  6. Inférence STARHE-DETECT (toutes les frames)
  7. Sauvegarde MongoDB

Point d'entrée appelé par le blueprint Go.
"""

import threading
import numpy as np

from starhe_plugin.dicom.reader        import load_dicom, extract_frames, frame_to_uint8
from starhe_plugin.dicom.prepus_bridge import preprocess_with_prepus
from starhe_plugin.dicom.anonymizer    import anonymize
from starhe_plugin.ai.starhe_risk      import STARHERiskModel
from starhe_plugin.ai.starhe_detect    import STARHEDetectModel
from starhe_plugin.db.mongo_client     import save_result
from starhe_plugin.utils.go_print      import go_print, go_progress, go_result
from starhe_plugin.config              import DETECT_EVERY_N


def run_pipeline(dicom_path: str,
                 anon_mode: str = "hash",
                 run_detection: bool = True,
                 back_scan_conversion: bool = True,
                 backscan_width: int = 512,
                 backscan_height: int = 512) -> dict:
    """
    Exécute le pipeline complet STARHE sur un fichier DICOM.

    Paramètres :
      dicom_path           : chemin absolu du fichier .dcm
      anon_mode            : "hash" | "remove" | "none"
      run_detection        : si False, saute STARHE-DETECT (plus rapide)
      back_scan_conversion : active la conversion scan inverse prepUS (recommandé)
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

    # ── 4. Prétraitement prepUS ───────────────────────────────────────────────
    go_progress(step := step + 1, TOTAL_STEPS,
                "Prétraitement prepUS (removeLayout + backscan)…")
    backscan_frames, crop_only_frames, info = preprocess_with_prepus(
        frames_rgb,
        back_scan_conversion=back_scan_conversion,
        backscan_width=backscan_width,
        backscan_height=backscan_height,
    )
    # Utilise le backscan si dispo (meilleur pour l'IA), sinon le crop seul
    processed = backscan_frames if backscan_frames is not None else crop_only_frames
    # (T, H', W') gris → (T, H', W', 3) RGB pour les modèles IA
    frames_processed = np.stack([processed, processed, processed], axis=-1)

    roi = None
    if info and "crop" in info:
        c = info["crop"]
        roi = (c["xmin"], c["ymin"], c["xmax"], c["ymax"])

    # ── 5. STARHE-RISK ────────────────────────────────────────────────────────
    go_progress(step := step + 1, TOTAL_STEPS, "Inférence STARHE-RISK (C3D)…")
    risk_model  = STARHERiskModel()
    risk_result = risk_model.predict(frames_processed)

    # ── 6. STARHE-DETECT (échantillonnage temporel) ──────────────────────────
    detections: list[dict] = []
    if run_detection:
        n_frames   = len(frames_processed)
        stride     = max(1, DETECT_EVERY_N)
        n_analysed = len(range(0, n_frames, stride))
        go_progress(step := step + 1, TOTAL_STEPS,
                    f"Inférence STARHE-DETECT ({n_analysed}/{n_frames} frames, stride={stride})…")

        # Attendre que le subprocess soit prêt (il a démarré pendant prepUS + RISK)
        detect_thread.join()
        if _detect_exc_box:
            raise _detect_exc_box[0]
        detect_model = _detect_model_box[0]

        with detect_model:
            sampled = list(range(0, n_frames, stride))
            bs = detect_model.batch_size
            go_print("info",
                     f"DETECT : batch_size={bs}, {len(sampled)} sampled frames à analyser.")

            # ── Pass 1 : inférence sur les frames samplées (seuil normal) ────
            sampled_dets: dict[int, list] = {}
            for b_start in range(0, len(sampled), bs):
                batch_idx    = sampled[b_start:b_start + bs]
                batch_frames = [frames_processed[i] for i in batch_idx]
                batch_dets   = detect_model.predict_batch(batch_frames)
                for idx, frame_dets in zip(batch_idx, batch_dets):
                    sampled_dets[idx] = frame_dets
                    for d in frame_dets:
                        detections.append({**d, "frame": idx})
                done = b_start + len(batch_idx)
                if done % 5 == 0 or done >= len(sampled):
                    go_print("info",
                             f"DETECT : {done}/{len(sampled)} sampled frames —"
                             f" {len(set(d['frame'] for d in detections))} frames avec détection(s).")

            # ── Pass 2 : suivi de la bbox sur les frames intermédiaires ───────
            # Pour chaque frame samplée avec une détection, on lance l'inférence
            # sur les frames intermédiaires suivantes avec seuil=0 afin que la
            # bounding box suive la tumeur.  Si le modèle ne trouve rien (faible
            # contraste, occultation partielle), on replie sur la bbox de la
            # frame samplée pour éviter un clignotement.
            followup_idx: list[int] = []
            followup_src: dict[int, int] = {}  # frame intermédiaire → frame samplée source
            for idx in sampled:
                if sampled_dets.get(idx):
                    for j in range(idx + 1, min(idx + stride, n_frames)):
                        followup_idx.append(j)
                        followup_src[j] = idx

            if followup_idx:
                go_print("info",
                         f"DETECT : suivi sur {len(followup_idx)} frames intermédiaires (seuil=0)…")
                followup_results: dict[int, list] = {}
                for b_start in range(0, len(followup_idx), bs):
                    batch_idx    = followup_idx[b_start:b_start + bs]
                    batch_frames = [frames_processed[i] for i in batch_idx]
                    batch_dets   = detect_model.predict_batch(batch_frames, score_thr=0.0)
                    for idx, frame_dets in zip(batch_idx, batch_dets):
                        followup_results[idx] = frame_dets

                for j, frame_dets in followup_results.items():
                    if frame_dets:
                        # Le modèle a localisé la tumeur → on utilise la vraie bbox
                        for d in frame_dets:
                            detections.append({**d, "frame": j})
                    else:
                        # Rien détecté → on propage la bbox de la frame samplée (fallback)
                        for d in sampled_dets[followup_src[j]]:
                            detections.append({**d, "frame": j})
    else:
        step += 1
        go_progress(step, TOTAL_STEPS, "STARHE-DETECT ignoré (run_detection=False).")

    # ── 7. Sauvegarde MongoDB ─────────────────────────────────────────────────
    doc_id = save_result(
        file_path  = dicom_path,
        num_frames = len(frames_processed),
        roi        = list(roi) if roi else [],
        risk       = risk_result,
        detections = detections,
        anon_mode  = anon_mode,
    )

    output = {
        "doc_id"     : doc_id,
        "num_frames" : len(frames_processed),
        "roi"        : list(roi) if roi else [],
        "risk"       : risk_result,
        "detections" : detections,
    }
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
    parser.add_argument("--no_detection", action="store_true",
                        help="Désactiver STARHE-DETECT (plus rapide)")
    parser.add_argument("--no_backscan", action="store_true",
                        help="Désactiver la conversion scan inverse prepUS")
    parser.add_argument("--backscan_width",  type=int, default=512,
                        help="Largeur de sortie backscan (défaut : 512)")
    parser.add_argument("--backscan_height", type=int, default=512,
                        help="Hauteur de sortie backscan (défaut : 512)")

    args = parser.parse_args()
    try:
        run_pipeline(
            dicom_path          = args.dicom_path,
            anon_mode           = args.anon_mode,
            run_detection       = not args.no_detection,
            back_scan_conversion= not args.no_backscan,
            backscan_width      = args.backscan_width,
            backscan_height     = args.backscan_height,
        )
    except Exception as exc:
        go_print("error", f"Pipeline échoué : {exc}")
        sys.exit(1)
