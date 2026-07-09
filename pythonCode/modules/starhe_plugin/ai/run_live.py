"""
ai/run_live.py — CLI entry point for the live analysis mode
==================================================================
Launched by the Go server as a subprocess for `POST /starhe/live`.

Usage:
    python -m starhe_plugin.ai.run_live --source folder --folder /path/to/watch
    python -m starhe_plugin.ai.run_live --source cstore --port 11112
    python -m starhe_plugin.ai.run_live --source hdmi --device 0 [--no_risk]

stdout protocol (identical to pipeline.py):
    GO_PRINT|info|{"level":"info","message":"..."}
    GO_PRINT|result|{"level":"result","message":"Frame N",
                     "data":{"frame_b64":"..jpeg_b64..","detections":[...],"risk":{...}}}

The process runs until it receives SIGTERM (sent by the Go server when the
SSE client disconnects) or until the source stops by itself.
"""

from __future__ import annotations

import argparse
import base64
import itertools
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from starhe_plugin.ai.live_pipeline import LivePipeline
from starhe_plugin.utils.go_print import go_print

# ── JPEG quality for SSE transmission ────────────────────────────────────────
_JPEG_QUALITY = 82   # good quality/size trade-off (~20–40 KB/frame)

# ── Global stop event (SIGTERM or source error) ──────────────────────────────
_stop_event = threading.Event()

# ── Immediate frame emission for display (decoupled from inference) ───────────
_preview_idx = itertools.count()


def _emit_preview_frame(frame: np.ndarray) -> None:
    """
    Encodes the frame as JPEG and emits it immediately on stdout for display
    in the UI, BEFORE inference has finished.
    The 'detections' key is intentionally absent → the frontend keeps
    the bboxes of the latest inference as overlay.
    """
    ok, buf = cv2.imencode(
        ".jpg",
        cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY],
    )
    if ok:
        go_print(
            "result",
            f"Preview {next(_preview_idx)}",
            {"frame_b64": base64.b64encode(buf.tobytes()).decode("ascii")},
        )


def _install_signal_handlers() -> None:
    def _handler(sig, frame):
        _stop_event.set()

    signal.signal(signal.SIGTERM, _handler)
    try:
        signal.signal(signal.SIGINT, _handler)
    except OSError:
        pass  # Windows: SIGINT sometimes not supported via signal.signal


# ── Frame sources ─────────────────────────────────────────────────────────────

class _FolderWatcher(threading.Thread):
    """
    Watches a folder and pushes new .dcm/.dicom files to
    the pipeline as they appear.
    """

    POLL_INTERVAL = 0.5  # seconds between two scans

    def __init__(self, folder: str, pipeline: LivePipeline) -> None:
        super().__init__(daemon=True, name="FolderWatcher")
        self._folder   = folder
        self._pipe     = pipeline
        self._seen: set[str] = set()
        self._stop_evt = threading.Event()

    def stop(self) -> None:
        self._stop_evt.set()

    def run(self) -> None:
        go_print("info", f"[Live] Surveillance du dossier : {self._folder}")
        while not self._stop_evt.is_set():
            try:
                dcm_files = sorted(
                    [p for p in Path(self._folder).iterdir()
                     if p.suffix.lower() in (".dcm", ".dicom")],
                    key=lambda p: p.stat().st_mtime,
                )
                for fp in dcm_files:
                    key = str(fp)
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    self._push_dicom(fp)
            except Exception as exc:
                go_print("warning", f"[FolderWatcher] {exc}")
            self._stop_evt.wait(self.POLL_INTERVAL)

    def _push_dicom(self, path: Path) -> None:
        try:
            import pydicom
            ds  = pydicom.dcmread(str(path), force=True)
            arr = ds.pixel_array

            if arr.dtype != np.uint8:
                mn, mx = arr.min(), arr.max()
                arr = (
                    ((arr.astype(np.float32) - mn) / (mx - mn) * 255).astype(np.uint8)
                    if mx > mn else np.zeros_like(arr, dtype=np.uint8)
                )

            # Inter-frame interval from DICOM FrameTime (ms → s), default 15 fps
            try:
                interval = float(ds.FrameTime) / 1000.0
            except AttributeError:
                interval = 1.0 / 15.0

            if arr.ndim == 2:
                # Single grayscale frame (H, W)
                rgb = np.stack([arr, arr, arr], axis=-1)
                _emit_preview_frame(rgb)
                self._pipe.push_frame(rgb)

            elif arr.ndim == 3 and arr.shape[2] == 3:
                # Single RGB frame (H, W, 3)
                _emit_preview_frame(arr)
                self._pipe.push_frame(arr)

            elif arr.ndim == 3:
                # Multi-frame grayscale cine (T, H, W)
                for frame in arr:
                    if self._stop_evt.is_set():
                        break
                    rgb = np.stack([frame, frame, frame], axis=-1)
                    _emit_preview_frame(rgb)
                    self._pipe.push_frame(rgb)
                    self._stop_evt.wait(interval)

            elif arr.ndim == 4:
                # Multi-frame RGB cine (T, H, W, 3)
                for frame in arr:
                    if self._stop_evt.is_set():
                        break
                    _emit_preview_frame(frame)
                    self._pipe.push_frame(frame)
                    self._stop_evt.wait(interval)

        except Exception as exc:
            go_print("warning", f"[FolderWatcher] Impossible de lire {path.name}: {exc}")


class _HDMIReader(threading.Thread):
    """
    Reads frames from an HDMI capture card via cv2.VideoCapture.
    Limits the rate to fps_limit frames/second (30 by default).
    """

    def __init__(self, device: int, pipeline: LivePipeline,
                 fps_limit: float = 30.0) -> None:
        super().__init__(daemon=True, name="HDMIReader")
        self._device   = device
        self._pipe     = pipeline
        self._interval = 1.0 / max(fps_limit, 1.0)
        self._stop_evt = threading.Event()

    def stop(self) -> None:
        self._stop_evt.set()

    def run(self) -> None:
        backends = (
            [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
            if sys.platform == "darwin"
            else [cv2.CAP_ANY]
        )
        cap = None
        for backend in backends:
            c = cv2.VideoCapture(self._device, backend)
            if c.isOpened():
                cap = c
                break
            c.release()

        if cap is None:
            go_print("error",
                     f"[Live] Impossible d'ouvrir le périphérique HDMI {self._device}. "
                     "Vérifiez que la carte de capture est connectée.")
            _stop_event.set()
            return

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        go_print("info",
                 f"[Live] Capture HDMI démarrée : device={self._device}, "
                 f"résolution={w}×{h}")

        next_t = time.monotonic()
        while not self._stop_evt.is_set():
            ret, frame_bgr = cap.read()
            if not ret:
                go_print("warning", "[Live] Fin du flux HDMI (aucune frame reçue).")
                break
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            _emit_preview_frame(frame_rgb)
            self._pipe.push_frame(frame_rgb)
            next_t += self._interval
            wait = next_t - time.monotonic()
            if wait > 0:
                self._stop_evt.wait(wait)

        cap.release()
        go_print("info", "[Live] Capture HDMI arrêtée.")
        _stop_event.set()


class _CStoreReceiver:
    """
    DICOM C-STORE SCP server (AE title: STARHE_LIVE).
    Pushes the pixels of each received instance to the pipeline.
    Requires pynetdicom.
    """

    def __init__(self, port: int, pipeline: LivePipeline) -> None:
        self._port = port
        self._pipe = pipeline
        self._ae   = None

    def start(self) -> None:
        try:
            from pynetdicom import AE, evt
            from pynetdicom.sop_class import (
                UltrasoundImageStorage,
                UltrasoundMultiFrameImageStorage,
                SecondaryCaptureImageStorage,
                DigitalXRayImageStorageForPresentation,
            )
        except ImportError:
            go_print("error",
                     "[Live] pynetdicom non installé — source C-STORE indisponible. "
                     "Installez-le avec : pip install pynetdicom")
            _stop_event.set()
            return

        ae = AE(ae_title=b"STARHE_LIVE")
        for sop in (
            UltrasoundImageStorage,
            UltrasoundMultiFrameImageStorage,
            SecondaryCaptureImageStorage,
            DigitalXRayImageStorageForPresentation,
        ):
            ae.add_supported_context(sop)

        pipe = self._pipe

        def _on_c_store(event):
            ds = event.dataset
            try:
                arr = ds.pixel_array
                if arr.dtype != np.uint8:
                    mn, mx = arr.min(), arr.max()
                    arr = (
                        ((arr.astype(np.float32) - mn) / (mx - mn) * 255).astype(np.uint8)
                        if mx > mn else np.zeros_like(arr, dtype=np.uint8)
                    )
                if arr.ndim == 2:
                    arr = np.stack([arr, arr, arr], axis=-1)
                if arr.ndim == 4:
                    for frame in arr:
                        _emit_preview_frame(frame)
                        pipe.push_frame(frame)
                else:
                    _emit_preview_frame(arr)
                    pipe.push_frame(arr)
            except Exception as exc:
                go_print("warning", f"[CStoreReceiver] Erreur pixel_array : {exc}")
            return 0x0000  # DICOM Success status

        self._ae = ae
        ae.start_server(
            ("0.0.0.0", self._port),
            block=False,
            evt_handlers=[(evt.EVT_C_STORE, _on_c_store)],
        )
        go_print("info",
                 f"[Live] C-STORE SCP démarré sur le port {self._port} "
                 "(AE title : STARHE_LIVE)")

    def stop(self) -> None:
        if self._ae is not None:
            try:
                self._ae.shutdown()
            except Exception:
                pass
            self._ae = None
            go_print("info", "[Live] C-STORE SCP arrêté.")


# ── Result callback ───────────────────────────────────────────────────────────

def _make_on_result() -> Callable[[dict], None]:
    """
    Returns the on_result callback emitting only the inference results
    (detections + risk) — without frame_b64.

    The frame was already emitted as a preview by the source thread → the video
    display stays smooth regardless of the RTMDet inference latency.
    When detections arrive, the frontend overlays them on the last
    displayed frame ("surveillance camera" behavior).
    """
    def on_result(result: dict) -> None:
        data: dict = {
            "detections": result.get("detections", []),
        }
        risk_score = result.get("risk_score")
        if risk_score is not None:
            data["risk"] = {
                "score": float(risk_score),
                "label": result.get("risk_label") or "",
            }
        go_print("result", f"Detections {result['frame_idx']}", data)

    return on_result


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="STARHE live analysis subprocess — launched by the Go server"
    )
    parser.add_argument(
        "--source", required=True,
        choices=["cstore", "folder", "hdmi"],
        help="Frame source: C-STORE DICOM | folder | HDMI capture card",
    )
    parser.add_argument("--port",    type=int, default=11112,
                        help="TCP port of the C-STORE SCP server (source=cstore)")
    parser.add_argument("--folder",  type=str, default="",
                        help="Path of the folder to watch (source=folder)")
    parser.add_argument("--device",  type=int, default=0,
                        help="cv2.VideoCapture index (source=hdmi)")
    parser.add_argument("--no_risk", action="store_true",
                        help="Disable STARHE-RISK (reduces latency)")
    args = parser.parse_args()

    _install_signal_handlers()

    # ── Pipeline ──────────────────────────────────────────────────────────────
    pipeline = LivePipeline(
        on_result=_make_on_result(),
        enable_risk=not args.no_risk,
    )
    pipeline.start()

    # ── Source ────────────────────────────────────────────────────────────────
    source_runner = None

    if args.source == "folder":
        if not args.folder:
            go_print("error", "--folder est requis avec --source folder")
            sys.exit(1)
        source_runner = _FolderWatcher(args.folder, pipeline)
        source_runner.start()

    elif args.source == "hdmi":
        source_runner = _HDMIReader(args.device, pipeline)
        source_runner.start()

    elif args.source == "cstore":
        source_runner = _CStoreReceiver(args.port, pipeline)
        source_runner.start()

    go_print("info", f"[Live] Analyse en direct démarrée (source={args.source})")

    # ── Block until stop (SIGTERM or source error) ────────────────────────────
    _stop_event.wait()

    # ── Clean shutdown ────────────────────────────────────────────────────────
    go_print("info", "[Live] Arrêt en cours…")
    if source_runner is not None and hasattr(source_runner, "stop"):
        source_runner.stop()
    pipeline.stop()
    go_print("info", "[Live] Arrêté.")


if __name__ == "__main__":
    main()
