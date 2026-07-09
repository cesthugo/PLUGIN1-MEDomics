"""
ai/live_pipeline.py — Real-time STARHE pipeline (DICOM streaming)
===================================================================
Processes individual frames on the fly, without requiring
the whole clip in advance.

Differences vs pipeline.py (batch):
  - No prepUS/backscan: incompatible with frame-by-frame processing.
    Uses crop.py (ROI detected on the first N frames) instead.
  - STARHE-DETECT: inference on each received frame (or every N via
    DETECT_EVERY_N), bbox reported immediately.
  - STARHE-RISK: updated every RISK_UPDATE_INTERVAL new frames
    on a sliding window of the last RISK_WINDOW_FRAMES frames.
  - Designed to run in a background thread; communicates via queue.

Typical usage
-------------
    from starhe_plugin.ai.live_pipeline import LivePipeline

    def on_result(r: dict):
        # called in the pipeline thread — synchronize with the UI if needed
        print(r["detections"], r["risk_score"])

    pipe = LivePipeline(on_result=on_result)
    pipe.start()

    # From the DICOM receiver / video capture:
    pipe.push_frame(frame_rgb_uint8)   # (H, W, 3) uint8 RGB

    pipe.stop()

Format of the result dict emitted to on_result
----------------------------------------------
    {
        "frame_idx"  : int,             # frame number since start()
        "timestamp"  : float,           # time.monotonic() at frame arrival
        "detections" : [                # empty list if nothing detected
            {"bbox": [x0,y0,x1,y1], "score": float, "label": "tumor"},
            ...
        ],
        "risk_score"  : float | None,   # None until the buffer is filled enough
        "risk_label"  : str   | None,
        "roi"         : (x0,y0,x1,y1) | None,   # detected crop ROI
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

# ── Live constants ────────────────────────────────────────────────────────────

# Number of frames in the sliding window for STARHE-RISK
RISK_WINDOW_FRAMES = 160

# RISK score update every N new frames
RISK_UPDATE_INTERVAL = 16

# Number of frames accumulated before estimating the ROI (crop)
ROI_CALIBRATION_FRAMES = 30

# Max size of the input queue (frames awaiting processing)
# Beyond that, the oldest frames are dropped (backpressure)
INPUT_QUEUE_MAXSIZE = 8


class LiveRingBuffer:
    """
    Thread-safe circular buffer.
    Stores the last N RGB frames (H, W, 3) uint8.
    """

    def __init__(self, maxlen: int = RISK_WINDOW_FRAMES):
        self._buf: collections.deque[np.ndarray] = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray) -> None:
        with self._lock:
            self._buf.append(frame)

    def snapshot(self) -> np.ndarray | None:
        """Returns (T, H, W, 3) or None if the buffer is empty."""
        with self._lock:
            if not self._buf:
                return None
            return np.stack(list(self._buf), axis=0)

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


class LivePipeline:
    """
    Non-blocking STARHE pipeline for frame-by-frame analysis.

    Parameters
    ----------
    on_result : callable (dict) → None
        Callback invoked in the pipeline thread for each processed frame.
        Must be thread-safe or post into a UI queue.
    detect_every_n : int
        Runs STARHE-DETECT every N frames (default: config.DETECT_EVERY_N).
    score_thr : float
        STARHE-DETECT confidence threshold.
    enable_risk : bool
        Enables STARHE-RISK (disable to reduce latency if not needed).
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

        # Input queue: the receiver pushes, the pipeline thread pops
        self._input_q: queue.Queue[np.ndarray | None] = queue.Queue(
            maxsize=INPUT_QUEUE_MAXSIZE
        )

        self._ring = LiveRingBuffer(RISK_WINDOW_FRAMES)

        self._frame_idx    = 0          # counter of received frames
        self._last_dets    : list = []  # latest detections (propagated between strides)
        self._last_risk    : dict | None = None  # latest RISK result
        self._roi          : tuple | None = None  # (x0, y0, x1, y1) crop

        # Models — initialized inside the thread (avoids fork/pickling issues)
        self._detect_model = None
        self._risk_model   = None

        self._thread  : threading.Thread | None = None
        self._stop_evt: threading.Event = threading.Event()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Starts the processing thread and loads the models."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, name="live-pipeline", daemon=True
        )
        self._thread.start()
        go_print("info", "LivePipeline : thread démarré.")

    def stop(self, timeout: float = 5.0) -> None:
        """Cleanly stops the pipeline and releases the models."""
        self._stop_evt.set()
        # Unblock the thread if it is waiting on the queue
        try:
            self._input_q.put_nowait(None)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=timeout)
        go_print("info", "LivePipeline : arrêté.")

    def push_frame(self, frame: np.ndarray) -> bool:
        """
        Submits a new (H, W, 3) uint8 RGB frame to the pipeline.
        Returns True if accepted, False if the queue is full (frame dropped).
        Frames must arrive in chronological order.
        """
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(f"frame doit être (H, W, 3) uint8 RGB, reçu shape={getattr(frame, 'shape', '?')}")
        try:
            self._input_q.put_nowait(frame.copy())
            return True
        except queue.Full:
            # Backpressure: drop the oldest frame and insert the new one
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

    # ── Processing thread ─────────────────────────────────────────────────────

    def _run(self) -> None:
        """Body of the pipeline thread."""
        self._load_models()

        while not self._stop_evt.is_set():
            try:
                frame = self._input_q.get(timeout=0.1)
            except queue.Empty:
                continue

            if frame is None:   # stop signal
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
        Processes an individual frame:
          1. Light preprocessing (burnin + crop)
          2. Ring buffer update
          3. STARHE-DETECT (every detect_every_n frames)
          4. STARHE-RISK   (every RISK_UPDATE_INTERVAL frames)
          5. Result construction
        """
        ts = time.monotonic()
        idx = self._frame_idx
        self._frame_idx += 1

        # ── 1. Burnin removal ─────────────────────────────────────────────────
        # remove_pixel_burnin expects (T, H, W, 3) → wrap into a batch of 1
        frames_batch = frame[np.newaxis, ...]              # (1, H, W, 3)
        frames_batch = remove_pixel_burnin(frames_batch)
        frame = frames_batch[0]                            # (H, W, 3)

        # ── 2. ROI calibration (first frames) + crop ─────────────────────────
        self._ring.push(frame)

        if self._roi is None and len(self._ring) >= ROI_CALIBRATION_FRAMES:
            self._roi = self._estimate_roi(self._ring.snapshot())
            go_print("info", f"LivePipeline : ROI calibré → {self._roi}")

        frame_cropped = self._apply_crop(frame)

        # ── 3. STARHE-DETECT ──────────────────────────────────────────────────
        if idx % self._detect_every_n == 0:
            try:
                dets = self._detect_model.predict(frame_cropped, score_thr=self._score_thr)
                # Remap the bboxes into the original frame's coordinate system
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

        # ── 5. Result ─────────────────────────────────────────────────────────
        return {
            "frame_idx"     : idx,
            "timestamp"     : ts,
            "detections"    : list(self._last_dets),
            "risk_score"    : self._last_risk["risk_score"] if self._last_risk else None,
            "risk_label"    : self._last_risk["risk_label"] if self._last_risk else None,
            "roi"           : self._roi,
            # Original frame (before crop) for UI display — key prefixed with _
            "_frame_display": frame,
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _estimate_roi(self, frames: np.ndarray) -> tuple[int, int, int, int] | None:
        """
        Detects the ROI (ultrasound cone) on the first accumulated frames.
        Uses crop.py's temporal approach (pixel variability).
        Returns (x0, y0, x1, y1) in the original frame's coordinate system,
        or None if detection fails.
        """
        try:
            return detect_ultrasound_roi_temporal(frames)
        except Exception as exc:
            go_print("warning", f"LivePipeline ROI estimation failed: {exc}")
            return None

    def _apply_crop(self, frame: np.ndarray) -> np.ndarray:
        """
        Applies the ROI crop if available, otherwise returns the raw frame.
        Resizes to 512×512 to normalize the RTMDet input.
        """
        if self._roi is not None:
            x0, y0, x1, y1 = self._roi
            h, w = frame.shape[:2]
            # Clamp within bounds
            x0 = max(0, x0); y0 = max(0, y0)
            x1 = min(w, x1); y1 = min(h, y1)
            if x1 > x0 and y1 > y0:
                frame = frame[y0:y1, x0:x1]

        # Resize to 512×512 via F.interpolate (cross-platform)
        if frame.shape[0] != 512 or frame.shape[1] != 512:
            t = torch.from_numpy(
                np.ascontiguousarray(frame, dtype=np.float32)
            ).permute(2, 0, 1).unsqueeze(0)
            t = F.interpolate(t, size=(512, 512), mode='bilinear', align_corners=False)
            frame = t.squeeze(0).permute(1, 2, 0).numpy().clip(0, 255).astype(np.uint8)
        return frame

    def _remap_detections(self, dets: list) -> list:
        """
        If a crop was applied, puts the bboxes back into the original
        frame's coordinate system (before crop + resize).
        Without a crop: returns the detections unchanged.
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
