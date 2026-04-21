"""
ai/live_pipeline.py — Pipeline STARHE temps-réel (streaming DICOM)
===================================================================
Traite des frames individuelles au fil de l'eau, sans nécessiter
l'intégralité du clip à l'avance.

Différences vs pipeline.py (batch) :
  - Pas de prepUS/backscan : incompatible avec le traitement frame-à-frame.
    Utilise crop.py (ROI détecté sur les N premières frames) à la place.
  - STARHE-DETECT : inférence à chaque frame reçue (ou toutes les N via
    DETECT_EVERY_N), bbox communiquée immédiatement.
  - STARHE-RISK : mis à jour toutes les RISK_UPDATE_INTERVAL nouvelles frames
    sur une fenêtre glissante des RISK_WINDOW_FRAMES dernières frames.
  - Conçu pour tourner dans un thread de fond ; communique via queue.

Usage typique
-------------
    from starhe_plugin.ai.live_pipeline import LivePipeline

    def on_result(r: dict):
        # appelé dans le thread pipeline — synchroniser avec l'UI si besoin
        print(r["detections"], r["risk_score"])

    pipe = LivePipeline(on_result=on_result)
    pipe.start()

    # Depuis le récepteur DICOM / capture vidéo :
    pipe.push_frame(frame_rgb_uint8)   # (H, W, 3) uint8 RGB

    pipe.stop()

Format du dict résultat émis dans on_result
-------------------------------------------
    {
        "frame_idx"  : int,             # numéro de frame depuis start()
        "timestamp"  : float,           # time.monotonic() à l'arrivée de la frame
        "detections" : [                # liste vide si rien détecté
            {"bbox": [x0,y0,x1,y1], "score": float, "label": "tumor"},
            ...
        ],
        "risk_score"  : float | None,   # None tant que le buffer n'est pas assez rempli
        "risk_label"  : str   | None,
        "roi"         : (x0,y0,x1,y1) | None,   # ROI crop détecté
    }
"""

from __future__ import annotations

import threading
import time
import queue
import collections
import logging
from typing import Callable

import numpy as np
import cv2
import torch
import torch.nn.functional as F

from starhe_plugin.config import DETECT_EVERY_N, DETECT_SCORE_THRESHOLD
from starhe_plugin.dicom.anonymizer import remove_pixel_burnin
from starhe_plugin.dicom.crop import detect_ultrasound_roi_temporal, crop_frame
from starhe_plugin.utils.go_print import go_print

log = logging.getLogger(__name__)

# ── Constantes live ───────────────────────────────────────────────────────────

# Nombre de frames dans la fenêtre glissante pour STARHE-RISK
RISK_WINDOW_FRAMES = 160

# Mise à jour du score RISK toutes les N nouvelles frames
RISK_UPDATE_INTERVAL = 16

# Nombre de frames accumulées avant d'estimer le ROI (crop)
ROI_CALIBRATION_FRAMES = 30

# Taille max de la queue d'entrée (frames en attente de traitement)
# Au-delà, les frames les plus anciennes sont supprimées (backpressure)
INPUT_QUEUE_MAXSIZE = 8


class LiveRingBuffer:
    """
    Buffer circulaire thread-safe.
    Stocke les N dernières frames RGB (H, W, 3) uint8.
    """

    def __init__(self, maxlen: int = RISK_WINDOW_FRAMES):
        self._buf: collections.deque[np.ndarray] = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray) -> None:
        with self._lock:
            self._buf.append(frame)

    def snapshot(self) -> np.ndarray | None:
        """Retourne (T, H, W, 3) ou None si buffer vide."""
        with self._lock:
            if not self._buf:
                return None
            return np.stack(list(self._buf), axis=0)

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


class LivePipeline:
    """
    Pipeline STARHE non-bloquant pour l'analyse frame-à-frame.

    Paramètres
    ----------
    on_result : callable (dict) → None
        Callback appelé dans le thread pipeline à chaque frame traitée.
        Doit être thread-safe ou poster dans une queue UI.
    detect_every_n : int
        Lance STARHE-DETECT toutes les N frames (défaut : config.DETECT_EVERY_N).
    score_thr : float
        Seuil de confiance STARHE-DETECT.
    enable_risk : bool
        Active STARHE-RISK (désactiver pour réduire la latence si non nécessaire).
    """

    def __init__(
        self,
        on_result: Callable[[dict], None] | None = None,
        detect_every_n: int = DETECT_EVERY_N,
        score_thr: float = DETECT_SCORE_THRESHOLD,
        enable_risk: bool = True,
    ):
        self._on_result      = on_result
        self._detect_every_n = max(1, detect_every_n)
        self._score_thr      = score_thr
        self._enable_risk    = enable_risk

        # Queue d'entrée : le récepteur empile, le thread pipeline dépile
        self._input_q: queue.Queue[np.ndarray | None] = queue.Queue(
            maxsize=INPUT_QUEUE_MAXSIZE
        )

        self._ring = LiveRingBuffer(RISK_WINDOW_FRAMES)

        self._frame_idx    = 0          # compteur de frames reçues
        self._last_dets    : list = []  # dernières détections (propagées entre strides)
        self._last_risk    : dict | None = None  # dernier résultat RISK
        self._roi          : tuple | None = None  # (x0, y0, x1, y1) crop

        # Modèles — initialisés dans le thread (évite les problèmes de fork/pickling)
        self._detect_model = None
        self._risk_model   = None

        self._thread  : threading.Thread | None = None
        self._stop_evt: threading.Event = threading.Event()

    # ── API publique ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le thread de traitement et charge les modèles."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, name="live-pipeline", daemon=True
        )
        self._thread.start()
        go_print("info", "LivePipeline : thread démarré.")

    def stop(self, timeout: float = 5.0) -> None:
        """Arrête proprement le pipeline et libère les modèles."""
        self._stop_evt.set()
        # Débloquer le thread si en attente sur la queue
        try:
            self._input_q.put_nowait(None)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=timeout)
        go_print("info", "LivePipeline : arrêté.")

    def push_frame(self, frame: np.ndarray) -> bool:
        """
        Soumet une nouvelle frame (H, W, 3) uint8 RGB au pipeline.
        Retourne True si acceptée, False si la queue est pleine (frame ignorée).
        Les frames doivent venir dans l'ordre chronologique.
        """
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(f"frame doit être (H, W, 3) uint8 RGB, reçu shape={getattr(frame, 'shape', '?')}")
        try:
            self._input_q.put_nowait(frame.copy())
            return True
        except queue.Full:
            # Backpressure : on ignore la frame la plus ancienne et on insère la nouvelle
            try:
                self._input_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._input_q.put_nowait(frame.copy())
            except queue.Full:
                pass
            go_print("warning", "LivePipeline : queue pleine — frame ignorée.")
            return False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Thread de traitement ──────────────────────────────────────────────────

    def _run(self) -> None:
        """Corps du thread pipeline."""
        self._load_models()

        while not self._stop_evt.is_set():
            try:
                frame = self._input_q.get(timeout=0.1)
            except queue.Empty:
                continue

            if frame is None:   # signal d'arrêt
                break

            result = self._process_frame(frame)
            if result is not None and self._on_result:
                try:
                    self._on_result(result)
                except Exception as exc:
                    go_print("error", f"LivePipeline on_result exception: {exc}")

        self._unload_models()

    def _load_models(self) -> None:
        go_print("info", "LivePipeline : chargement des modèles…")
        from starhe_plugin.ai.starhe_detect import STARHEDetectModel
        self._detect_model = STARHEDetectModel()
        go_print("info", f"LivePipeline : RTMDet prêt (batch_size={self._detect_model.batch_size}).")

        if self._enable_risk:
            from starhe_plugin.ai.starhe_risk import STARHERiskModel
            self._risk_model = STARHERiskModel()
            go_print("info", "LivePipeline : C3D RISK prêt.")

    def _unload_models(self) -> None:
        if self._detect_model:
            try:
                self._detect_model.close()
            except Exception:
                pass
            self._detect_model = None
        self._risk_model = None
        go_print("info", "LivePipeline : modèles libérés.")

    def _process_frame(self, frame: np.ndarray) -> dict | None:
        """
        Traite une frame individuelle :
          1. Prétraitement léger (burnin + crop)
          2. Mise à jour du ring buffer
          3. STARHE-DETECT (toutes les detect_every_n frames)
          4. STARHE-RISK   (toutes les RISK_UPDATE_INTERVAL frames)
          5. Construction du résultat
        """
        ts = time.monotonic()
        idx = self._frame_idx
        self._frame_idx += 1

        # ── 1. Burnin removal ─────────────────────────────────────────────────
        # remove_pixel_burnin attend (T, H, W, 3) → on wrape en batch de 1
        frames_batch = frame[np.newaxis, ...]              # (1, H, W, 3)
        frames_batch = remove_pixel_burnin(frames_batch)
        frame = frames_batch[0]                            # (H, W, 3)

        # ── 2. Calibration ROI (premières frames) + crop ─────────────────────
        self._ring.push(frame)

        if self._roi is None and len(self._ring) >= ROI_CALIBRATION_FRAMES:
            self._roi = self._estimate_roi(self._ring.snapshot())
            go_print("info", f"LivePipeline : ROI calibré → {self._roi}")

        frame_cropped = self._apply_crop(frame)

        # ── 3. STARHE-DETECT ──────────────────────────────────────────────────
        if idx % self._detect_every_n == 0:
            try:
                dets = self._detect_model.predict(frame_cropped, score_thr=self._score_thr)
                # Remappe les bbox dans le repère de la frame originale
                self._last_dets = self._remap_detections(dets)
            except Exception as exc:
                go_print("error", f"LivePipeline DETECT: {exc}")
                self._last_dets = []

        # ── 4. STARHE-RISK ────────────────────────────────────────────────────
        if (self._enable_risk
                and self._risk_model is not None
                and idx % RISK_UPDATE_INTERVAL == 0
                and len(self._ring) >= RISK_UPDATE_INTERVAL):
            try:
                buf = self._ring.snapshot()   # (T, H, W, 3)
                self._last_risk = self._risk_model.predict(buf)
            except Exception as exc:
                go_print("error", f"LivePipeline RISK: {exc}")

        # ── 5. Résultat ───────────────────────────────────────────────────────
        return {
            "frame_idx"     : idx,
            "timestamp"     : ts,
            "detections"    : list(self._last_dets),
            "risk_score"    : self._last_risk["risk_score"] if self._last_risk else None,
            "risk_label"    : self._last_risk["risk_label"] if self._last_risk else None,
            "roi"           : self._roi,
            # Frame originale (avant crop) pour affichage UI — clé préfixée _
            "_frame_display": frame,
        }

    # ── Helpers internes ──────────────────────────────────────────────────────

    def _estimate_roi(self, frames: np.ndarray) -> tuple[int, int, int, int] | None:
        """
        Détecte le ROI (cône ultrason) sur les premières frames accumulées.
        Utilise l'approche temporelle de crop.py (variabilité pixel).
        Retourne (x0, y0, x1, y1) dans le repère de la frame originale,
        ou None si la détection échoue.
        """
        try:
            return detect_ultrasound_roi_temporal(frames)
        except Exception as exc:
            go_print("warning", f"LivePipeline ROI estimation failed: {exc}")
            return None

    def _apply_crop(self, frame: np.ndarray) -> np.ndarray:
        """
        Applique le crop ROI si disponible, sinon retourne la frame brute.
        Redimensionne vers 512×512 pour normaliser l'entrée RTMDet.
        """
        if self._roi is not None:
            x0, y0, x1, y1 = self._roi
            h, w = frame.shape[:2]
            # Clamper dans les bornes
            x0 = max(0, x0); y0 = max(0, y0)
            x1 = min(w, x1); y1 = min(h, y1)
            if x1 > x0 and y1 > y0:
                frame = frame[y0:y1, x0:x1]

        # Redimensionner vers 512×512 via F.interpolate (cross-plateforme)
        if frame.shape[0] != 512 or frame.shape[1] != 512:
            t = torch.from_numpy(
                np.ascontiguousarray(frame, dtype=np.float32)
            ).permute(2, 0, 1).unsqueeze(0)
            t = F.interpolate(t, size=(512, 512), mode='bilinear', align_corners=False)
            frame = t.squeeze(0).permute(1, 2, 0).numpy().clip(0, 255).astype(np.uint8)
        return frame

    def _remap_detections(self, dets: list) -> list:
        """
        Si un crop a été appliqué, remet les bbox dans le repère de la frame
        originale (avant crop + resize).
        Sans crop : retourne les détections inchangées.
        """
        if not dets or self._roi is None:
            return dets

        x0_roi, y0_roi, x1_roi, y1_roi = self._roi
        roi_w = max(1, x1_roi - x0_roi)
        roi_h = max(1, y1_roi - y0_roi)
        scale_x = roi_w / 512.0
        scale_y = roi_h / 512.0

        remapped = []
        for d in dets:
            bx0, by0, bx1, by1 = d["bbox"]
            remapped.append({
                **d,
                "bbox": [
                    x0_roi + bx0 * scale_x,
                    y0_roi + by0 * scale_y,
                    x0_roi + bx1 * scale_x,
                    y0_roi + by1 * scale_y,
                ],
            })
        return remapped
