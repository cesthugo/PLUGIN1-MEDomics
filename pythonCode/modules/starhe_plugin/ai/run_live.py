"""
ai/run_live.py — Point d'entrée CLI pour le mode analyse en direct
==================================================================
Lancé par le serveur Go comme subprocess pour `POST /starhe/live`.

Usage :
    python -m starhe_plugin.ai.run_live --source folder --folder /path/to/watch
    python -m starhe_plugin.ai.run_live --source cstore --port 11112
    python -m starhe_plugin.ai.run_live --source hdmi --device 0 [--no_risk]

Protocole stdout (identique à pipeline.py) :
    GO_PRINT|info|{"level":"info","message":"..."}
    GO_PRINT|result|{"level":"result","message":"Frame N",
                     "data":{"frame_b64":"..jpeg_b64..","detections":[...],"risk":{...}}}

Le processus tourne jusqu'à recevoir SIGTERM (envoyé par le serveur Go quand le
client SSE se déconnecte) ou jusqu'à ce que la source s'arrête d'elle-même.
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

# ── Qualité JPEG pour la transmission SSE ────────────────────────────────────
_JPEG_QUALITY = 82   # bon compromis qualité / taille (~20–40 KB/frame)

# ── Événement global de stop (SIGTERM ou erreur de source) ───────────────────
_stop_event = threading.Event()

# ── Émission immédiate de frames pour l'affichage (découplé de l'inférence) ───
_preview_idx = itertools.count()


def _emit_preview_frame(frame: np.ndarray) -> None:
    """
    Encode la frame en JPEG et l'émet immédiatement sur stdout pour l'affichage
    dans l'interface, AVANT que l'inférence soit terminée.
    La clé 'detections' est intentionnellement absente → le frontend conserve
    les bbox de la dernière inférence en overlay.
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
        pass  # Windows : SIGINT parfois non supporté via signal.signal


# ── Sources de frames ─────────────────────────────────────────────────────────

class _FolderWatcher(threading.Thread):
    """
    Surveille un dossier et pousse les nouveaux fichiers .dcm/.dicom vers
    le pipeline au fur et à mesure qu'ils apparaissent.
    """

    POLL_INTERVAL = 0.5  # secondes entre deux scans

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

            # Intervalle inter-frames depuis DICOM FrameTime (ms → s), défaut 15 fps
            try:
                interval = float(ds.FrameTime) / 1000.0
            except AttributeError:
                interval = 1.0 / 15.0

            if arr.ndim == 2:
                # Frame unique en niveaux de gris (H, W)
                rgb = np.stack([arr, arr, arr], axis=-1)
                _emit_preview_frame(rgb)
                self._pipe.push_frame(rgb)

            elif arr.ndim == 3 and arr.shape[2] == 3:
                # Frame unique RGB (H, W, 3)
                _emit_preview_frame(arr)
                self._pipe.push_frame(arr)

            elif arr.ndim == 3:
                # Cine multi-frame en niveaux de gris (T, H, W)
                for frame in arr:
                    if self._stop_evt.is_set():
                        break
                    rgb = np.stack([frame, frame, frame], axis=-1)
                    _emit_preview_frame(rgb)
                    self._pipe.push_frame(rgb)
                    self._stop_evt.wait(interval)

            elif arr.ndim == 4:
                # Cine multi-frame RGB (T, H, W, 3)
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
    Lit les frames depuis une carte de capture HDMI via cv2.VideoCapture.
    Limite le débit à fps_limit images/seconde (30 par défaut).
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
    Serveur DICOM C-STORE SCP (AE title : STARHE_LIVE).
    Pousse les pixels de chaque instance reçue vers le pipeline.
    Requiert pynetdicom.
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


# ── Callback résultat ─────────────────────────────────────────────────────────

def _make_on_result() -> Callable[[dict], None]:
    """
    Retourne le callback on_result émettant uniquement les résultats d'inférence
    (détections + risque) — sans frame_b64.

    La frame a déjà été émise en preview par le thread source → l'affichage
    vidéo est fluide indépendamment de la latence d'inférence RTMDet.
    Quand les détections arrivent, le frontend les superpose sur la dernière
    frame affichée (comportement « caméra de surveillance »).
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


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="STARHE live analysis subprocess — lancé par le serveur Go"
    )
    parser.add_argument(
        "--source", required=True,
        choices=["cstore", "folder", "hdmi"],
        help="Source de frames : C-STORE DICOM | dossier | carte HDMI",
    )
    parser.add_argument("--port",    type=int, default=11112,
                        help="Port TCP du serveur C-STORE SCP (source=cstore)")
    parser.add_argument("--folder",  type=str, default="",
                        help="Chemin du dossier à surveiller (source=folder)")
    parser.add_argument("--device",  type=int, default=0,
                        help="Index cv2.VideoCapture (source=hdmi)")
    parser.add_argument("--no_risk", action="store_true",
                        help="Désactiver STARHE-RISK (réduit la latence)")
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

    # ── Bloque jusqu'au stop (SIGTERM ou erreur de source) ────────────────────
    _stop_event.wait()

    # ── Arrêt propre ──────────────────────────────────────────────────────────
    go_print("info", "[Live] Arrêt en cours…")
    if source_runner is not None and hasattr(source_runner, "stop"):
        source_runner.stop()
    pipeline.stop()
    go_print("info", "[Live] Arrêté.")


if __name__ == "__main__":
    main()
