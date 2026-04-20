"""
ui/live_tab.py — Onglet « Analyse en direct » de l'interface STARHE
====================================================================
Frame Tkinter autonome embarquant :
  - panneau gauche  : sélection de la source, contrôles start/stop,
                      compteurs FPS / frames, statut
  - panneau droit   : canvas temps-réel avec overlay bboxes + ROI
  - encart résultats : score de risque coloré + nb de détections

Sources supportées
------------------
  - 📡  C-STORE DICOM  (via live_receiver.py — intégré ici)
  - 📂  Dossier         (polling, fichiers .dcm ajoutés au fur et à mesure)
  - �  HDMI            (carte de capture → sonde échographique en direct)

Intégration dans STARHEApp
--------------------------
    from starhe_plugin.ui.live_tab import LiveTab
    tab = LiveTab(parent_frame, logger=self._log)
    tab.pack(fill="both", expand=True)

Thread safety
-------------
LivePipeline appelle on_result() depuis son thread interne.
Toute mise à jour Tkinter est postée via self.after(0, …) pour rester
dans le thread principal.
"""

from __future__ import annotations

import os
import time
import threading
import logging
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import ttk, filedialog

import numpy as np

# Importations optionnelles (présentes si les dépendances sont installées)
try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

try:
    import pydicom
    _PYDICOM_OK = True
except ImportError:
    _PYDICOM_OK = False

from starhe_plugin.ai.live_pipeline import LivePipeline

# ── Palette (identique à prototype_tkinter.py) ─────────────────────────────
SIDEBAR_BG  = "#151521"
SIDEBAR_HOV = "#1e1e2e"
SBAR_FG     = "#e2e8f0"
SBAR_MUTED  = "#7c8899"
MAIN_BG     = "#f4f6fb"
CANVAS_BG   = "#0d1117"
BLUE        = "#1565C0"
BLUE_TEXT   = "#1e40af"
CARD_BG     = "#ffffff"
CARD_BORDER = "#e2e8f0"
CARD_SHADOW = "#d1d9e6"
BORDER      = "#cbd5e0"
RISK_LOW_FG = "#4ade80"
RISK_HIGH_FG= "#f87171"
RISK_MED_FG = "#fbbf24"
DANGER_FG   = "#f87171"
LOG_BG      = "#0d1117"

FONT_TITLE  = ("Segoe UI", 12, "bold")
FONT_SEC    = ("Segoe UI",  7, "bold")
FONT_BTN    = ("Segoe UI",  9, "bold")
FONT_BTN_P  = ("Segoe UI", 10, "bold")
FONT_BODY   = ("Segoe UI",  9)
FONT_SMALL  = ("Segoe UI",  8)
FONT_MONO   = ("Consolas",  8)
FONT_NAV    = ("Segoe UI", 13, "bold")

SIDEBAR_W   = 270   # largeur du panneau gauche (px)
CANVAS_MIN_W = 480  # taille minimale du canvas
CANVAS_MIN_H = 360


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ndarray_to_photoimage(arr: np.ndarray, max_w: int, max_h: int) -> "ImageTk.PhotoImage":
    """Convertit un ndarray uint8 (H,W) ou (H,W,3) en PhotoImage adapté au canvas."""
    if arr.ndim == 2:
        img = Image.fromarray(arr, mode="L").convert("RGB")
    else:
        img = Image.fromarray(arr.astype(np.uint8), mode="RGB")
    img.thumbnail((max_w, max_h), Image.LANCZOS)
    return ImageTk.PhotoImage(img)


def _draw_detections_on_array(frame: np.ndarray, detections: list[dict]) -> np.ndarray:
    """Superpose les bboxes de détection sur une copie du frame."""
    if not _CV2_OK:
        return frame
    vis = frame.copy()
    for det in detections:
        x0, y0, x1, y1 = (int(v) for v in det["bbox"])
        color = (255, 80, 80) if "tumor" in det.get("label", "") else (80, 200, 80)
        cv2.rectangle(vis, (x0, y0), (x1, y1), color, 2)
        cv2.putText(vis, f"{det['label']} {det['score']:.2f}",
                    (x0, max(y0 - 6, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    return vis


def _make_btn(
    parent,
    text: str,
    command: Callable,
    bg: str = "#000000",
    fg: str = "#ffffff",
    font=FONT_BTN,
    padx: int = 12,
    pady: int = 6,
    width: int | None = None,
    anchor: str = "w",
) -> tk.Frame:
    """Bouton cliquable cross-platform (macOS ignore bg/fg sur tk.Button)."""
    kw: dict = dict(bg=bg, padx=2, pady=2, bd=0, relief="flat")
    frame = tk.Frame(parent, **kw, cursor="hand2")
    lbl_kw: dict = dict(bg=bg, fg=fg, font=font, padx=padx, pady=pady,
                        anchor=anchor, cursor="hand2")
    if width is not None:
        lbl_kw["width"] = width
    lbl = tk.Label(frame, text=text, **lbl_kw)
    lbl.pack(fill="both", expand=True)

    def _hover_in(_e):
        _lighter = "#1e1e2e" if bg == "#000000" else bg
        frame.configure(bg=_lighter)
        lbl  .configure(bg=_lighter)

    def _hover_out(_e):
        frame.configure(bg=bg)
        lbl  .configure(bg=bg)

    for w in (frame, lbl):
        w.bind("<Enter>",    _hover_in)
        w.bind("<Leave>",    _hover_out)
        w.bind("<Button-1>", lambda _e: command())

    return frame


def _sh(parent, title: str) -> tk.Frame:
    """En-tête de section (barre bleue + texte majuscule)."""
    row = tk.Frame(parent, bg=SIDEBAR_BG)
    row.pack(fill="x", padx=8, pady=(10, 2))
    tk.Frame(row, bg=BLUE, width=3).pack(side="left", fill="y")
    tk.Label(row, text=title.upper(), bg=SIDEBAR_BG, fg=SBAR_MUTED,
             font=FONT_SEC, padx=6).pack(side="left")
    return row


# ─────────────────────────────────────────────────────────────────────────────
#  Récepteur de dossier (polling)
# ─────────────────────────────────────────────────────────────────────────────

class _FolderWatcher(threading.Thread):
    """
    Surveille un dossier et pousse les fichiers .dcm vers le pipeline.
    S'arrête proprement via stop().
    """

    POLL_INTERVAL = 0.5   # secondes entre deux scans

    def __init__(self, folder: str, pipeline: LivePipeline, logger: logging.Logger,
                 on_preview: Callable[[np.ndarray], None] | None = None):
        super().__init__(daemon=True, name="FolderWatcher")
        self._folder      = folder
        self._pipe        = pipeline
        self._log         = logger
        self._on_preview  = on_preview
        self._seen: set[str] = set()
        self._stop_evt = threading.Event()

    def stop(self):
        self._stop_evt.set()

    def run(self):
        self._log.info(f"[LiveTab] Surveillance du dossier : {self._folder}")
        while not self._stop_evt.is_set():
            try:
                files = sorted(Path(self._folder).glob("*.dcm"),
                               key=lambda p: p.stat().st_mtime)
                for fp in files:
                    key = str(fp)
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    self._push_dicom(fp)
            except Exception as exc:
                self._log.warning(f"[FolderWatcher] {exc}")
            self._stop_evt.wait(self.POLL_INTERVAL)

    def _push_dicom(self, path: Path):
        if not _PYDICOM_OK:
            return
        try:
            ds = pydicom.dcmread(str(path), force=True)
            arr = ds.pixel_array
            # Normalisation uint8 si nécessaire
            if arr.dtype != np.uint8:
                mn, mx = arr.min(), arr.max()
                if mx > mn:
                    arr = ((arr.astype(np.float32) - mn) / (mx - mn) * 255).astype(np.uint8)
                else:
                    arr = np.zeros_like(arr, dtype=np.uint8)
            # Greyscale → RGB
            if arr.ndim == 2:
                arr = np.stack([arr, arr, arr], axis=-1)
            if self._on_preview is not None:
                self._on_preview(arr)
            self._pipe.push_frame(arr)
        except Exception as exc:
            self._log.warning(f"[FolderWatcher] Impossible de lire {path.name}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
#  Résolutions HDMI proposées dans l'interface
# ─────────────────────────────────────────────────────────────────────────────

# Mapping libellé → (largeur, hauteur) ; None = laisser la carte de capture choisir
_HDMI_RESOLUTIONS: dict[str, tuple[int | None, int | None]] = {
    "Auto (détection)":      (None, None),
    "1920 × 1080  Full HD":  (1920, 1080),
    "1280 × 720   HD":       (1280,  720),
    "720 × 576    PAL":       (720,  576),
    "640 × 480    SD":        (640,  480),
}


# ─────────────────────────────────────────────────────────────────────────────
#  Découverte des périphériques de capture (HDMI, cartes de capture USB…)
# ─────────────────────────────────────────────────────────────────────────────

def _list_capture_devices() -> list[tuple[int, str, float, int, int]]:
    """
    Retourne [(index_cv2, nom_lisible, fps, width, height), …] pour tous les
    périphériques de capture vidéo reconnus par le système.
    Inclut la résolution pour permettre de distinguer une carte de capture HDMI
    d'une caméra intégrée ou d'un iPhone via Continuity Camera.
    """
    import sys

    if not _CV2_OK:
        return []

    names: list[str] = []
    if sys.platform == "darwin":
        try:
            import subprocess, json
            result = subprocess.run(
                ["system_profiler", "SPCameraDataType", "-json"],
                capture_output=True, text=True, timeout=5
            )
            data = json.loads(result.stdout)
            for cam in data.get("SPCameraDataType", []):
                raw = cam.get("_name", "Périphérique inconnu")
                names.append(raw.replace("\xa0", " ").strip())
        except Exception:
            pass

    backends = [cv2.CAP_AVFOUNDATION] if sys.platform == "darwin" else [cv2.CAP_ANY]
    found: list[tuple[int, str, float, int, int]] = []
    for idx in range(10):
        opened = False
        for backend in backends:
            cap = cv2.VideoCapture(idx, backend)
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                name = names[len(found)] if len(found) < len(names) else f"Périphérique {idx}"
                found.append((idx, name, fps, w, h))
                opened = True
                break
            cap.release()
        if not opened and len(found) >= max(len(names), 2):
            break
    return found


# ─────────────────────────────────────────────────────────────────────────────
#  Lecteur HDMI (carte de capture via cv2.VideoCapture)
# ─────────────────────────────────────────────────────────────────────────────

class _HDMIReader(threading.Thread):
    """
    Lit les frames depuis une carte de capture HDMI (cv2.VideoCapture).
    Permet de recevoir le flux vidéo d'une sonde échographique branchée
    via HDMI → carte de capture USB → ordinateur.
    La résolution peut être imposée (sinon la carte choisit automatiquement).
    """

    def __init__(self, device: int, pipeline: LivePipeline,
                 logger: logging.Logger, fps_limit: float = 30.0,
                 width: int | None = None, height: int | None = None,
                 on_preview: Callable[[np.ndarray], None] | None = None,
                 on_error: Callable[[str], None] | None = None):
        super().__init__(daemon=True, name="HDMIReader")
        self._device     = device
        self._pipe       = pipeline
        self._log        = logger
        self._on_preview = on_preview
        self._on_error   = on_error
        self._width      = width
        self._height     = height
        self._interval   = 1.0 / max(fps_limit, 1.0)
        self._stop_evt   = threading.Event()

    def stop(self):
        self._stop_evt.set()

    def run(self):
        if not _CV2_OK:
            msg = "cv2 (OpenCV) non disponible — installez opencv-python"
            self._log.error(f"[LiveTab] {msg}")
            if self._on_error:
                self._on_error(msg)
            return

        import sys
        backends = [cv2.CAP_ANY]
        if sys.platform == "darwin":
            backends = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]

        cap = None
        for backend in backends:
            c = cv2.VideoCapture(self._device, backend)
            if c.isOpened():
                cap = c
                break
            c.release()

        if cap is None or not cap.isOpened():
            msg = (f"Impossible d'ouvrir le périphérique HDMI {self._device!r}. "
                   "Vérifiez que la carte de capture est bien connectée et "
                   "reconnue par le système (Gestionnaire de périphériques / "
                   "Réglages système → Confidentialité → Caméra).")
            self._log.error(f"[LiveTab] {msg}")
            if self._on_error:
                self._on_error(msg)
            return

        # Imposer la résolution si demandée
        if self._width and self._height:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._log.info(
            f"[LiveTab] Capture HDMI démarrée : device={self._device}, "
            f"résolution={actual_w}×{actual_h}"
        )
        next_t = time.monotonic()
        while not self._stop_evt.is_set():
            ret, frame_bgr = cap.read()
            if not ret:
                self._log.warning("[LiveTab] Fin du flux HDMI.")
                break
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            if self._on_preview is not None:
                self._on_preview(frame_rgb)
            self._pipe.push_frame(frame_rgb)
            next_t += self._interval
            wait = next_t - time.monotonic()
            if wait > 0:
                self._stop_evt.wait(wait)
        cap.release()
        self._log.info("[LiveTab] Capture HDMI arrêtée.")


# ─────────────────────────────────────────────────────────────────────────────
#  Récepteur DICOM C-STORE SCP (pynetdicom)
# ─────────────────────────────────────────────────────────────────────────────

class _DicomReceiver:
    """
    Serveur DICOM C-STORE minimal (AE title : STARHE_LIVE).
    Pousse les pixels de chaque instance reçue vers le pipeline.
    Nécessite pynetdicom.
    """

    def __init__(self, port: int, pipeline: LivePipeline, logger: logging.Logger,
                 on_preview: Callable[[np.ndarray], None] | None = None):
        self._port       = port
        self._pipe       = pipeline
        self._log        = logger
        self._on_preview = on_preview
        self._ae         = None   # ApplicationEntity pynetdicom

    def start(self):
        try:
            from pynetdicom import AE, evt
            from pynetdicom.sop_class import (
                DigitalXRayImageStorageForPresentation,
                UltrasoundImageStorage,
                UltrasoundMultiFrameImageStorage,
                SecondaryCaptureImageStorage,
            )
        except ImportError:
            self._log.error("[LiveTab] pynetdicom non installé : C-STORE désactivé.")
            return

        ae = AE(ae_title=b"STARHE_LIVE")
        for sop in (
            UltrasoundImageStorage,
            UltrasoundMultiFrameImageStorage,
            SecondaryCaptureImageStorage,
            DigitalXRayImageStorageForPresentation,
        ):
            ae.add_supported_context(sop)

        def _on_c_store(event):
            ds = event.dataset
            try:
                arr = ds.pixel_array
                if arr.dtype != np.uint8:
                    mn, mx = arr.min(), arr.max()
                    if mx > mn:
                        arr = ((arr.astype(np.float32) - mn) / (mx - mn) * 255).astype(np.uint8)
                    else:
                        arr = np.zeros_like(arr, dtype=np.uint8)
                if arr.ndim == 2:
                    arr = np.stack([arr, arr, arr], axis=-1)
                # Si multi-frame : itérer sur les frames
                if arr.ndim == 4:
                    for frame in arr:
                        if self._on_preview is not None:
                            self._on_preview(frame)
                        self._pipe.push_frame(frame)
                else:
                    if self._on_preview is not None:
                        self._on_preview(arr)
                    self._pipe.push_frame(arr)
            except Exception as exc:
                self._log.warning(f"[DicomReceiver] Erreur pixel_array : {exc}")
            return 0x0000  # Success

        self._ae = ae
        handlers = [(evt.EVT_C_STORE, _on_c_store)]
        self._ae.start_server(("0.0.0.0", self._port), block=False, evt_handlers=handlers)
        self._log.info(f"[LiveTab] C-STORE SCP démarré sur le port {self._port}")

    def stop(self):
        if self._ae is not None:
            try:
                self._ae.shutdown()
            except Exception:
                pass
            self._ae = None
            self._log.info("[LiveTab] C-STORE SCP arrêté.")


# ─────────────────────────────────────────────────────────────────────────────
#  LiveTab — Frame principale
# ─────────────────────────────────────────────────────────────────────────────

class LiveTab(tk.Frame):
    """
    Onglet « Analyse en direct » embarquable dans STARHEApp ou autonome.

    Utilisation autonome :
        root = tk.Tk()
        tab = LiveTab(root)
        tab.pack(fill="both", expand=True)
        root.mainloop()
    """

    SOURCE_CSTORE  = "cstore"
    SOURCE_FOLDER  = "folder"
    SOURCE_HDMI    = "hdmi"

    def __init__(self, parent, logger: logging.Logger | None = None, **kw):
        super().__init__(parent, bg=MAIN_BG, **kw)
        self._log = logger or logging.getLogger(__name__)

        # État courant
        self._pipeline  : LivePipeline | None = None
        self._source_runner               = None   # _HDMIReader | _FolderWatcher | _DicomReceiver
        self._running   : bool = False

        # HDMI : indique si une vraie carte de capture a été identifiée lors du scan
        self._hdmi_capture_card_found: bool = False

        # Dernière frame brute reçue de la source (écrite par thread source, lue par tick UI)
        # L'affectation simple est atomique sous le GIL de CPython.
        self._preview_frame: np.ndarray | None = None

        # Dernières bboxes connues issues du pipeline (mises à jour par on_result)
        self._latest_bboxes: list[dict] = []

        # ID du after() du tick vidéo (pour l'annulation)
        self._preview_tick_id: str | None = None

        # Statistiques source (frames brutes reçues)
        self._input_fps_times: list[float] = []  # timestamps sur 1 s
        self._frame_count: int = 0               # total frames reçues depuis start

        # Référence PhotoImage (évite la garbage collection)
        self._photo_ref: "ImageTk.PhotoImage | None" = None

        self._build_ui()

    # ── Construction de l'interface ───────────────────────────────────────────

    def _build_ui(self):
        # Panneau gauche (sidebar)
        self._sidebar = tk.Frame(self, bg=SIDEBAR_BG, width=SIDEBAR_W)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)
        self._build_sidebar(self._sidebar)

        # Séparateur vertical
        tk.Frame(self, bg=BORDER, width=1).pack(side="left", fill="y")

        # Zone principale
        self._main = tk.Frame(self, bg=MAIN_BG)
        self._main.pack(side="left", fill="both", expand=True)
        self._build_main(self._main)

    def _build_sidebar(self, parent: tk.Frame):
        # ── En-tête ────────────────────────────────────────────────────────
        hdr = tk.Frame(parent, bg=SIDEBAR_BG, height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Frame(hdr, bg=BLUE, width=3).pack(side="left", fill="y")
        tk.Label(hdr, text="📡  Analyse en direct",
                 bg=SIDEBAR_BG, fg=SBAR_FG,
                 font=FONT_TITLE, padx=10).pack(side="left", pady=10)

        # Scrollable interior
        sc_canvas = tk.Canvas(parent, bg=SIDEBAR_BG, highlightthickness=0)
        sc_canvas.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=sc_canvas.yview)
        sc_canvas.configure(yscrollcommand=scrollbar.set)
        sc = tk.Frame(sc_canvas, bg=SIDEBAR_BG)
        sc_canvas.create_window((0, 0), window=sc, anchor="nw")
        sc.bind("<Configure>",
                lambda _e: sc_canvas.configure(scrollregion=sc_canvas.bbox("all")))
        sc_canvas.bind("<MouseWheel>",
                       lambda e: sc_canvas.yview_scroll(
                           int(-1 * (e.delta if abs(e.delta) < 50 else e.delta // 120)),
                           "units"))

        # ── Source ─────────────────────────────────────────────────────────
        _sh(sc, "Source")
        self._source_var = tk.StringVar(value=self.SOURCE_CSTORE)
        _sources = [
            ("📡  C-STORE DICOM",  self.SOURCE_CSTORE),
            ("📂  Dossier",         self.SOURCE_FOLDER),
            ("🔌  HDMI / Sonde",   self.SOURCE_HDMI),
        ]
        for label, val in _sources:
            tk.Radiobutton(
                sc, text=label, variable=self._source_var, value=val,
                command=self._on_source_changed,
                bg=SIDEBAR_BG, fg=SBAR_FG, selectcolor=SIDEBAR_BG,
                activebackground=SIDEBAR_BG, activeforeground=SBAR_FG,
                font=FONT_BODY, anchor="w",
            ).pack(fill="x", padx=14, pady=1)

        # ── Paramètres de source ───────────────────────────────────────────
        _sh(sc, "Paramètres")

        # — C-STORE port —
        self._cstore_frame = tk.Frame(sc, bg=SIDEBAR_BG)
        self._cstore_frame.pack(fill="x", padx=10, pady=2)
        tk.Label(self._cstore_frame, text="Port TCP :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).pack(side="left")
        self._port_var = tk.StringVar(value="11112")
        tk.Entry(self._cstore_frame, textvariable=self._port_var, width=7,
                 bg="#1a1a2e", fg=SBAR_FG, insertbackground=SBAR_FG,
                 relief="flat", font=FONT_BODY).pack(side="left", padx=6)

        # — Dossier —
        self._folder_frame = tk.Frame(sc, bg=SIDEBAR_BG)
        self._folder_var = tk.StringVar(value="")
        tk.Label(self._folder_frame, text="Chemin :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).grid(row=0, column=0, sticky="w", padx=(0, 4))
        self._folder_entry = tk.Entry(
            self._folder_frame, textvariable=self._folder_var, width=18,
            bg="#1a1a2e", fg=SBAR_FG, insertbackground=SBAR_FG,
            relief="flat", font=FONT_BODY)
        self._folder_entry.grid(row=0, column=1, sticky="ew")
        self._folder_frame.columnconfigure(1, weight=1)
        _browse_btn = _make_btn(self._folder_frame, "…", self._browse_folder,
                                bg="#1e1e2e", fg=SBAR_FG, font=FONT_BODY,
                                padx=6, pady=3)
        _browse_btn.grid(row=0, column=2, padx=(4, 0))

        # — HDMI / Carte de capture —
        self._hdmi_frame = tk.Frame(sc, bg=SIDEBAR_BG)
        self._hdmi_scanned = False

        # Ligne 0 : libellé + bouton Rafraîchir
        hdmi_row0 = tk.Frame(self._hdmi_frame, bg=SIDEBAR_BG)
        hdmi_row0.pack(fill="x")
        tk.Label(hdmi_row0, text="Périphérique :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).pack(side="left")
        _hdmi_refresh = _make_btn(hdmi_row0, "↺", self._refresh_hdmi_devices,
                                  bg="#1e1e2e", fg=SBAR_FG, font=FONT_SMALL,
                                  padx=6, pady=2)
        _hdmi_refresh.pack(side="right")

        # Ligne 1 : Combobox des périphériques de capture
        self._hdmi_device_var = tk.StringVar(value="")  # vide jusqu'au scan
        self._hdmi_combo = ttk.Combobox(
            self._hdmi_frame, textvariable=self._hdmi_device_var,
            state="readonly", font=FONT_SMALL, width=24,
        )
        self._hdmi_combo.pack(fill="x", pady=(2, 4))

        # Ligne 2 : Résolution
        tk.Label(self._hdmi_frame, text="Résolution :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).pack(anchor="w")
        self._hdmi_res_var = tk.StringVar(value="Auto (détection)")
        self._hdmi_res_combo = ttk.Combobox(
            self._hdmi_frame, textvariable=self._hdmi_res_var,
            values=list(_HDMI_RESOLUTIONS.keys()),
            state="readonly", font=FONT_SMALL, width=24,
        )
        self._hdmi_res_combo.current(0)
        self._hdmi_res_combo.pack(fill="x", pady=(2, 4))

        # Note d'info
        self._hdmi_warn_lbl = tk.Label(
            self._hdmi_frame,
            text="⚠  Matériel requis : carte de capture USB\n"
                 "   (Elgato, AVerMedia, Magewell…)\n"
                 "   Un port HDMI Mac est en SORTIE uniquement.",
            bg=SIDEBAR_BG, fg="#f59e0b",
            font=("Segoe UI", 7), justify="left",
        )
        self._hdmi_warn_lbl.pack(anchor="w", pady=(0, 2))

        # Affichage initial
        self._on_source_changed()

        # Options pipeline
        _sh(sc, "Pipeline")
        opt_row = tk.Frame(sc, bg=SIDEBAR_BG)
        opt_row.pack(fill="x", padx=10, pady=2)
        self._risk_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opt_row, text="Score de risque",
                       variable=self._risk_var,
                       bg=SIDEBAR_BG, fg=SBAR_FG, selectcolor=SIDEBAR_BG,
                       activebackground=SIDEBAR_BG, activeforeground=SBAR_FG,
                       font=FONT_SMALL).pack(side="left")

        # ── Contrôles ──────────────────────────────────────────────────────
        _sh(sc, "Contrôles")
        self._start_btn = _make_btn(sc, "▶  Démarrer", self._start_live,
                                    bg=BLUE, fg="#ffffff", font=FONT_BTN_P,
                                    pady=8)
        self._start_btn.pack(fill="x", padx=10, pady=(4, 2))
        self._stop_btn = _make_btn(sc, "■  Arrêter", self._stop_live,
                                   bg="#374151", fg="#9ca3af", font=FONT_BTN,
                                   pady=8)
        self._stop_btn.pack(fill="x", padx=10, pady=(0, 4))

        # ── Statut ─────────────────────────────────────────────────────────
        _sh(sc, "Statut")
        status_frame = tk.Frame(sc, bg=SIDEBAR_BG)
        status_frame.pack(fill="x", padx=10, pady=(2, 0))

        self._status_dot = tk.Label(status_frame, text="●",
                                    bg=SIDEBAR_BG, fg="#374151", font=FONT_BODY)
        self._status_dot.pack(side="left")
        self._status_lbl = tk.Label(status_frame, text="Inactif",
                                     bg=SIDEBAR_BG, fg=SBAR_MUTED, font=FONT_SMALL)
        self._status_lbl.pack(side="left", padx=4)

        stats_frame = tk.Frame(sc, bg=SIDEBAR_BG)
        stats_frame.pack(fill="x", padx=10, pady=2)
        tk.Label(stats_frame, text="FPS :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).grid(row=0, column=0, sticky="w")
        self._fps_lbl = tk.Label(stats_frame, text="—",
                                  bg=SIDEBAR_BG, fg=SBAR_FG, font=FONT_SMALL)
        self._fps_lbl.grid(row=0, column=1, sticky="w", padx=6)
        tk.Label(stats_frame, text="Frames :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).grid(row=1, column=0, sticky="w")
        self._frames_lbl = tk.Label(stats_frame, text="0",
                                     bg=SIDEBAR_BG, fg=SBAR_FG, font=FONT_SMALL)
        self._frames_lbl.grid(row=1, column=1, sticky="w", padx=6)

        # ── Résultats ──────────────────────────────────────────────────────
        _sh(sc, "Résultats")
        res_frame = tk.Frame(sc, bg=SIDEBAR_BG)
        res_frame.pack(fill="x", padx=10, pady=(2, 6))

        tk.Label(res_frame, text="Risque :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).grid(row=0, column=0, sticky="w")
        self._risk_score_lbl = tk.Label(res_frame, text="—",
                                         bg=SIDEBAR_BG, fg=SBAR_FG,
                                         font=("Segoe UI", 11, "bold"))
        self._risk_score_lbl.grid(row=0, column=1, sticky="w", padx=6)

        tk.Label(res_frame, text="Label :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).grid(row=1, column=0, sticky="w")
        self._risk_label_lbl = tk.Label(res_frame, text="—",
                                         bg=SIDEBAR_BG, fg=SBAR_MUTED,
                                         font=FONT_SMALL)
        self._risk_label_lbl.grid(row=1, column=1, sticky="w", padx=6)

        tk.Label(res_frame, text="Détections :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).grid(row=2, column=0, sticky="w")
        self._det_count_lbl = tk.Label(res_frame, text="—",
                                        bg=SIDEBAR_BG, fg=SBAR_MUTED,
                                        font=FONT_SMALL)
        self._det_count_lbl.grid(row=2, column=1, sticky="w", padx=6)

    def _build_main(self, parent: tk.Frame):
        # ── En-tête carte ──────────────────────────────────────────────────
        hdr = tk.Frame(parent, bg=CARD_BG, height=36)
        hdr.pack(fill="x", padx=13, pady=(10, 0))
        hdr.pack_propagate(False)
        tk.Frame(hdr, bg=BORDER, height=1).pack(side="bottom", fill="x")
        tk.Label(hdr, text="Flux vidéo en direct",
                 bg=CARD_BG, fg=BLUE_TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=12, pady=8)
        self._live_badge = tk.Label(hdr, text="● EN DIRECT",
                                     bg="#fef2f2", fg="#dc2626",
                                     font=("Segoe UI", 7, "bold"),
                                     padx=7, pady=2)
        # Badge masqué tant que pas démarré
        self._live_badge_visible = False

        # ── Canvas ────────────────────────────────────────────────────────
        card_wrap = tk.Frame(parent, bg=CARD_SHADOW, bd=0)
        card_wrap.pack(fill="both", expand=True, padx=13, pady=(0, 4))
        card = tk.Frame(card_wrap, bg=CARD_BG, bd=0,
                        highlightbackground=CARD_BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=1, pady=1)

        canvas_wrap = tk.Frame(card, bg=CANVAS_BG)
        canvas_wrap.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(canvas_wrap, bg=CANVAS_BG,
                                  highlightthickness=0,
                                  width=CANVAS_MIN_W, height=CANVAS_MIN_H)
        self._canvas.pack(fill="both", expand=True)

        self._canvas_text = self._canvas.create_text(
            CANVAS_MIN_W // 2, CANVAS_MIN_H // 2,
            text="En attente du flux…\n\nSélectionnez une source et cliquez sur « Démarrer »",
            fill="#2a2a3e", font=("Segoe UI", 12), justify="center",
        )
        self._canvas_image_id: int | None = None

    # ── Callbacks sidebar ─────────────────────────────────────────────────────

    def _on_source_changed(self):
        src = self._source_var.get()
        self._cstore_frame.pack_forget()
        self._folder_frame.pack_forget()
        self._hdmi_frame.pack_forget()

        if src == self.SOURCE_CSTORE:
            self._cstore_frame.pack(fill="x", padx=10, pady=2)
        elif src == self.SOURCE_FOLDER:
            self._folder_frame.pack(fill="x", padx=10, pady=2)
        elif src == self.SOURCE_HDMI:
            self._hdmi_frame.pack(fill="x", padx=10, pady=2)
            # Scan paresseux : déclenché au premier affichage seulement
            if not self._hdmi_scanned:
                self._hdmi_scanned = True
                threading.Thread(target=self._refresh_hdmi_devices, daemon=True).start()

    def _browse_folder(self):
        path = filedialog.askdirectory(title="Sélectionner le dossier DICOM")
        if path:
            self._folder_var.set(path)

    def _refresh_hdmi_devices(self):
        """Détecte les périphériques de capture vidéo et met à jour le Combobox HDMI."""
        self._hdmi_scanned = True
        devices = _list_capture_devices()  # [(idx, name, fps, w, h), …]

        # Mots-clés pour identifier les cartes de capture HDMI
        _PREFER  = {"capture", "hdmi", "elgato", "avermedia", "magewell",
                    "usb video", "usb capture", "video capture"}
        # Mots-clés pour exclure les caméras intégrées / iPhones
        _EXCLUDE = {"iphone", "ipad", "facetime", "continuity",
                    "macbook", "built-in", "integrated", "isight"}

        def _pick_preferred(devs: list) -> int:
            # 1ère passe : nom explicitement reconnu comme carte de capture
            for i, (_, name, fps, w, h) in enumerate(devs):
                if any(k in name.lower() for k in _PREFER):
                    return i
            # 2ème passe : écarter les caméras connues (iPhone, FaceTime…)
            for i, (_, name, fps, w, h) in enumerate(devs):
                if not any(k in name.lower() for k in _EXCLUDE):
                    return i
            # 3ème passe : sélectionner la plus haute résolution
            return max(range(len(devs)), key=lambda i: devs[i][3] * devs[i][4])

        def _update():
            labels = [
                f"{idx}  —  {name}  [{w}×{h} @{fps:.0f}fps]"
                for idx, name, fps, w, h in devices
            ]
            if not labels:
                self._hdmi_combo["values"] = ["Aucun périphérique détecté"]
                self._hdmi_device_var.set("Aucun périphérique détecté")
                self._hdmi_capture_card_found = False
                self._hdmi_warn_lbl.configure(
                    text="⚠  Aucune carte de capture trouvée.\n"
                         "   Branchez la carte USB et\n"
                         "   cliquez sur ↺ pour rescanner.\n"
                         "   Le port HDMI Mac est en SORTIE.",
                    fg=DANGER_FG,
                )
                return
            self._hdmi_combo["values"] = labels
            preferred = _pick_preferred(devices)
            self._hdmi_combo.current(preferred)
            # Avertir si aucun périphérique reconnu comme carte de capture
            sel_name = devices[preferred][1].lower()
            card_found = any(k in sel_name for k in _PREFER)
            self._hdmi_capture_card_found = card_found
            if card_found:
                self._hdmi_warn_lbl.configure(
                    text="✅  Carte de capture détectée.",
                    fg=RISK_LOW_FG,
                )
            else:
                self._hdmi_warn_lbl.configure(
                    text="⚠  Carte de capture non identifiée.\n"
                         "   Vérifiez la sélection ci-dessus.\n"
                         "   Port HDMI Mac = sortie uniquement.",
                    fg="#f59e0b",
                )
        self.after(0, _update)

    # ── Démarrage / arrêt ─────────────────────────────────────────────────────

    def _start_live(self):
        if self._running:
            return

        src = self._source_var.get()

        # Validation des paramètres
        if src == self.SOURCE_CSTORE:
            try:
                port = int(self._port_var.get())
                if not (1 <= port <= 65535):
                    raise ValueError
            except ValueError:
                self._set_status("Port invalide", error=True)
                return

        elif src == self.SOURCE_FOLDER:
            folder = self._folder_var.get().strip()
            if not folder or not os.path.isdir(folder):
                self._set_status("Dossier introuvable", error=True)
                return

        elif src == self.SOURCE_HDMI:
            raw = self._hdmi_device_var.get().strip()
            if not raw or "Aucun" in raw:
                self._set_status("Aucun périphérique HDMI sélectionné", error=True)
                if not self._hdmi_scanned:
                    threading.Thread(target=self._refresh_hdmi_devices, daemon=True).start()
                return
            if not self._hdmi_capture_card_found:
                self._set_status(
                    "Carte de capture introuvable — branchez le matériel",
                    error=True,
                )
                return
            try:
                hdmi_device = int(raw.split("—")[0].strip())
            except (ValueError, IndexError):
                self._set_status("Périphérique HDMI invalide", error=True)
                return
            res_label = self._hdmi_res_var.get()
            hdmi_w, hdmi_h = _HDMI_RESOLUTIONS.get(res_label, (None, None))

        # Callback appelé par la source pour chaque frame brute (thread source)
        def _on_preview_raw(frame: np.ndarray) -> None:
            self._preview_frame = frame          # atomic sous le GIL
            now = time.monotonic()
            self._input_fps_times.append(now)
            self._frame_count += 1

        # Callback appelé si la source rencontre une erreur fatale
        def _on_source_error(msg: str) -> None:
            self.after(0, lambda m=msg: self._set_status(m[:60], error=True))

        # Créer et démarrer le pipeline
        self._pipeline = LivePipeline(
            on_result=self._on_pipeline_result,
            enable_risk=self._risk_var.get(),
        )
        self._pipeline.start()

        # Démarrer la source
        if src == self.SOURCE_CSTORE:
            self._source_runner = _DicomReceiver(
                port, self._pipeline, self._log, on_preview=_on_preview_raw)
            self._source_runner.start()
        elif src == self.SOURCE_FOLDER:
            self._source_runner = _FolderWatcher(
                folder, self._pipeline, self._log, on_preview=_on_preview_raw)
            self._source_runner.start()
        elif src == self.SOURCE_HDMI:
            self._source_runner = _HDMIReader(
                hdmi_device, self._pipeline, self._log,
                width=hdmi_w, height=hdmi_h,
                on_preview=_on_preview_raw, on_error=_on_source_error)
            self._source_runner.start()

        self._running = True
        self._frame_count = 0
        self._input_fps_times.clear()
        self._latest_bboxes = []
        self._preview_frame = None
        self._set_status("En cours…", running=True)
        self._show_live_badge(True)
        # Démarre la boucle d'affichage (~30 fps)
        self._preview_tick()

    def _stop_live(self):
        if not self._running:
            return
        # Stoppe le tick d'affichage
        if self._preview_tick_id is not None:
            self.after_cancel(self._preview_tick_id)
            self._preview_tick_id = None
        # Arrêt de la source
        if self._source_runner is not None:
            self._source_runner.stop()
            self._source_runner = None
        # Arrêt du pipeline
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None
        self._running = False
        self._set_status("Arrêté", running=False)
        self._show_live_badge(False)

    # ── Boucle d'affichage (~30 fps) ─────────────────────────────────────────

    def _preview_tick(self) -> None:
        """
        Appelé toutes les ~33 ms dans le main thread.
        Affiche la dernière frame brute reçue de la source, avec overlay bboxes.
        Découplé du pipeline : la frame s'affiche même si l'inférence est lente.
        """
        if not self._running:
            return

        frame = self._preview_frame  # lecture atomique (GIL)
        if frame is not None and _PIL_OK:
            bboxes = self._latest_bboxes
            vis = _draw_detections_on_array(frame, bboxes) if bboxes else frame
            cw = max(self._canvas.winfo_width(),  CANVAS_MIN_W)
            ch = max(self._canvas.winfo_height(), CANVAS_MIN_H)
            photo = _ndarray_to_photoimage(vis, cw, ch)
            self._photo_ref = photo  # évite la garbage collection
            if self._canvas_image_id is None:
                self._canvas.delete(self._canvas_text)
                self._canvas_image_id = self._canvas.create_image(
                    0, 0, image=photo, anchor="nw")
            else:
                self._canvas.itemconfigure(self._canvas_image_id, image=photo)

        # Mise à jour FPS source (glissant sur 1 s)
        now = time.monotonic()
        cutoff = now - 1.0
        self._input_fps_times = [t for t in self._input_fps_times if t >= cutoff]
        fps = len(self._input_fps_times)
        self._fps_lbl.configure(text=str(fps) if self._frame_count else "—")
        self._frames_lbl.configure(text=str(self._frame_count))

        # Reschedule
        self._preview_tick_id = self.after(33, self._preview_tick)

    # ── Callback pipeline (thread externe → Tkinter via after) ────────────────

    def _on_pipeline_result(self, result: dict):
        """Appelé depuis le thread pipeline — poste la mise à jour dans le main thread."""
        self.after(0, lambda r=result: self._apply_result(r))

    def _apply_result(self, r: dict):
        """
        Met à jour les bboxes et les labels sidebar depuis le résultat pipeline.
        L'affichage de la frame est géré indépendamment par _preview_tick.
        """
        # Mise à jour des bboxes connues → utilisées par _preview_tick
        self._latest_bboxes = r.get("detections", [])

        # ── Résultats risque ───────────────────────────────────────────────
        risk_score = r.get("risk_score")
        risk_label = r.get("risk_label")
        if risk_score is not None:
            pct = f"{risk_score * 100:.1f} %"
            if risk_score >= 0.6:
                fg = RISK_HIGH_FG
            elif risk_score >= 0.35:
                fg = RISK_MED_FG
            else:
                fg = RISK_LOW_FG
            self._risk_score_lbl.configure(text=pct, fg=fg)
            self._risk_label_lbl.configure(
                text=risk_label or "—",
                fg=RISK_HIGH_FG if "high" in (risk_label or "").lower() else RISK_LOW_FG,
            )
        else:
            self._risk_score_lbl.configure(text="—", fg=SBAR_MUTED)
            self._risk_label_lbl.configure(text="calibration…", fg=SBAR_MUTED)

        # ── Compteur détections ────────────────────────────────────────────
        n = len(self._latest_bboxes)
        self._det_count_lbl.configure(
            text=str(n),
            fg=RISK_HIGH_FG if n > 0 else SBAR_MUTED,
        )

    # ── Helpers d'état ────────────────────────────────────────────────────────

    def _set_status(self, text: str, *, running: bool = False, error: bool = False):
        if error:
            dot_fg, lbl_fg = DANGER_FG, DANGER_FG
        elif running:
            dot_fg, lbl_fg = RISK_LOW_FG, SBAR_FG
        else:
            dot_fg, lbl_fg = "#374151", SBAR_MUTED
        self._status_dot.configure(fg=dot_fg)
        self._status_lbl.configure(text=text, fg=lbl_fg)

    def _show_live_badge(self, visible: bool):
        if visible and not self._live_badge_visible:
            self._live_badge.pack(side="left", padx=(6, 0))
            self._live_badge_visible = True
        elif not visible and self._live_badge_visible:
            self._live_badge.pack_forget()
            self._live_badge_visible = False

    # ── Nettoyage ─────────────────────────────────────────────────────────────

    def destroy(self):
        """Arrête proprement la session avant de détruire le widget."""
        self._stop_live()
        super().destroy()
