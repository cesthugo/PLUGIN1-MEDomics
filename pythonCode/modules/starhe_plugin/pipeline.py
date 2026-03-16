"""
pipeline.py — Orchestrateur du flux de traitement STARHE
=========================================================
Enchaîne toutes les étapes :
  1. Chargement DICOM
  2. Extraction des frames
  3. Anonymisation
  4. Crop (suppression du cadre échographe)
  5. Inférence STARHE-RISK
  6. Inférence STARHE-DETECT (frame médian uniquement)
  7. Sauvegarde MongoDB

Point d'entrée appelé par le blueprint Go.
"""

from starhe_plugin.dicom.reader     import load_dicom, extract_frames, frame_to_uint8
from starhe_plugin.dicom.crop       import crop_clip
from starhe_plugin.dicom.anonymizer import anonymize
from starhe_plugin.ai.starhe_risk   import STARHERiskModel
from starhe_plugin.ai.starhe_detect import STARHEDetectModel
from starhe_plugin.db.mongo_client  import save_result
from starhe_plugin.utils.go_print   import go_print, go_progress, go_result


def run_pipeline(dicom_path: str,
                 anon_mode: str = "hash",
                 run_detection: bool = True) -> dict:
    """
    Exécute le pipeline complet STARHE sur un fichier DICOM.

    Paramètres :
      dicom_path     : chemin absolu du fichier .dcm
      anon_mode      : "hash" | "remove" | "none"
      run_detection  : si False, saute STARHE-DETECT (plus rapide)

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
    frames_raw = extract_frames(ds)  # (T, H, W) ou (T, H, W, 3)
    frames_u8  = frame_to_uint8(frames_raw[0])  # normalise pour crop base

    # ── 4. Crop ───────────────────────────────────────────────────────────────
    go_progress(step := step + 1, TOTAL_STEPS, "Détection et suppression du cadre échographe…")
    # Normalise d'abord tous les frames en uint8 pour le crop
    import numpy as np
    frames_norm = np.stack([frame_to_uint8(f) for f in frames_raw])  # (T, H, W) uint8
    # Assure 3 canaux pour le crop (requis par OpenCV)
    if frames_norm.ndim == 3:
        frames_rgb = np.stack([frames_norm] * 3, axis=-1)   # (T, H, W, 3)
    else:
        frames_rgb = frames_norm

    frames_cropped, roi = crop_clip(frames_rgb)   # (T, H', W', 3)

    # ── 5. STARHE-RISK ────────────────────────────────────────────────────────
    go_progress(step := step + 1, TOTAL_STEPS, "Inférence STARHE-RISK (C3D)…")
    risk_model  = STARHERiskModel()
    risk_result = risk_model.predict(frames_cropped)

    # ── 6. STARHE-DETECT (frame médian) ───────────────────────────────────────
    detections = []
    if run_detection:
        go_progress(step := step + 1, TOTAL_STEPS, "Inférence STARHE-DETECT (DINO-DETR)…")
        detect_model = STARHEDetectModel()
        mid_frame    = frames_cropped[len(frames_cropped) // 2]
        detections   = detect_model.predict(mid_frame)
    else:
        step += 1
        go_progress(step, TOTAL_STEPS, "STARHE-DETECT ignoré (run_detection=False).")

    # ── 7. Sauvegarde MongoDB ─────────────────────────────────────────────────
    doc_id = save_result(
        file_path  = dicom_path,
        num_frames = len(frames_cropped),
        roi        = list(roi),
        risk       = risk_result,
        detections = detections,
        anon_mode  = anon_mode,
    )

    output = {
        "doc_id"     : doc_id,
        "num_frames" : len(frames_cropped),
        "roi"        : list(roi),
        "risk"       : risk_result,
        "detections" : detections,
    }
    go_result(output)
    return output
