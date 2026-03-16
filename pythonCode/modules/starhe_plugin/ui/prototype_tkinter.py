"""
ui/prototype_tkinter.py — Prototype de validation STARHE
=========================================================
Objectif : valider le flux utilisateur AVANT le portage React.

Fenêtre principale :
  ┌──────────────────────────────────────────────────────────────┐
  │  STARHE Plugin — Prototype de validation                     │
  ├──────────────────────┬───────────────────────────────────────┤
  │  Panneau de contrôle │  Visionneuse (frame + bbox)           │
  │  ─────────────────── │  ─────────────────────────────────────│
  │  [Charger DICOM]     │                                       │
  │  [← ] Frame [X/N] [→]│    <canvas Tkinter>                  │
  │  [Appliquer Crop]    │                                       │
  │  [Lancer Analyse IA] │                                       │
  │  ─────────────────── │                                       │
  │  Résultats :         ├───────────────────────────────────────┤
  │  Risque : —          │  Log console                         │
  │  Détections : —      │  ─────────────────────────────────────│
  │                      │  <zone de texte scrollable>           │
  └──────────────────────┴───────────────────────────────────────┘

Dépendances :
  pip install pydicom opencv-python-headless Pillow
"""

import sys
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import numpy as np
from PIL import Image, ImageTk

# ── Ajout du dossier modules au path pour les imports relatifs ────────────────
# __file__ est dans starhe_plugin/ui/ → "../.." remonte à pythonCode/modules/
_MODULES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from starhe_plugin.dicom.reader     import load_dicom, extract_frames, frame_to_uint8
from starhe_plugin.dicom.crop       import crop_clip
from starhe_plugin.dicom.anonymizer import anonymize
from starhe_plugin.config           import DATA_DIR


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

CANVAS_W = 560
CANVAS_H = 480
APP_TITLE = "STARHE Plugin — Prototype de validation"
BG_COLOR  = "#1e1e2e"
FG_COLOR  = "#cdd6f4"
ACCENT    = "#89b4fa"
BTN_BG    = "#313244"
BTN_FG    = "#cdd6f4"
SUCCESS   = "#a6e3a1"
WARNING   = "#fab387"
DANGER    = "#f38ba8"


def _ndarray_to_photoimage(arr: np.ndarray, max_w: int, max_h: int) -> ImageTk.PhotoImage:
    """Convertit un ndarray uint8 (H,W) ou (H,W,3) en PhotoImage adapté au canvas."""
    if arr.ndim == 2:
        img = Image.fromarray(arr, mode="L").convert("RGB")
    else:
        img = Image.fromarray(arr.astype(np.uint8), mode="RGB")

    img.thumbnail((max_w, max_h), Image.LANCZOS)
    return ImageTk.PhotoImage(img)


def _draw_detections_on_array(frame: np.ndarray,
                               detections: list[dict]) -> np.ndarray:
    """Superpose les bboxes de détection sur une copie du frame (sans OpenCV)."""
    import cv2
    vis = frame.copy()
    for det in detections:
        x0, y0, x1, y1 = det["bbox"]
        color = (255, 80, 80) if "maligne" in det["label"] else (80, 200, 80)
        cv2.rectangle(vis, (x0, y0), (x1, y1), color, 2)
        cv2.putText(vis, f"{det['label']} {det['score']:.2f}",
                    (x0, max(y0 - 6, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    return vis


# ─────────────────────────────────────────────────────────────────────────────
#  Application principale
# ─────────────────────────────────────────────────────────────────────────────

class STARHEApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=BG_COLOR)
        self.resizable(True, True)
        self.minsize(900, 600)

        # ── État interne ──────────────────────────────────────────────────────
        self._frames_raw    : np.ndarray | None = None  # (T, H, W, 3) uint8
        self._frames_cropped: np.ndarray | None = None
        self._roi           : tuple | None      = None
        self._frame_idx     : int               = 0
        self._detections    : list[dict]        = []
        self._show_cropped  : bool              = False
        self._photo_ref     = None   # garde la référence PyImage en vie
        self._playing       : bool              = False
        self._play_after_id = None   # ID retourné par self.after()

        self._build_ui()
        self._log("Bienvenue dans STARHE Plugin — Prototype Tkinter.")
        self._log("Chargez un fichier DICOM (.dcm) pour commencer.")

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Barre de titre personnalisée (label uniquement, Tk gère la vraie barre)
        header = tk.Label(self, text="🩻  STARHE Plugin — Détection cancer du foie",
                          bg=BG_COLOR, fg=ACCENT,
                          font=("Segoe UI", 13, "bold"), pady=8)
        header.pack(fill="x")

        # Séparateur
        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # Corps principal : panneau gauche + droit
        body = tk.Frame(self, bg=BG_COLOR)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_left_panel(body)
        self._build_right_panel(body)

    def _build_left_panel(self, parent):
        left = tk.Frame(parent, bg=BG_COLOR, width=240)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        def section(title):
            tk.Label(left, text=title, bg=BG_COLOR, fg=ACCENT,
                     font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", pady=(10, 2))
            ttk.Separator(left, orient="horizontal").pack(fill="x")

        # ── Section : Fichier ─────────────────────────────────────────────────
        section("FICHIER DICOM")
        self._btn_load = self._btn(left, "📂  Charger DICOM", self._on_load_dicom)
        self._btn_load.pack(fill="x", pady=3)

        self._label_file = tk.Label(left, text="Aucun fichier", bg=BG_COLOR,
                                    fg=FG_COLOR, font=("Segoe UI", 8),
                                    wraplength=220, anchor="w", justify="left")
        self._label_file.pack(fill="x")

        # Infos DICOM
        self._info_var = tk.StringVar(value="—")
        tk.Label(left, textvariable=self._info_var, bg=BG_COLOR, fg=FG_COLOR,
                 font=("Consolas", 8), justify="left", anchor="nw",
                 wraplength=220).pack(fill="x", pady=(4, 0))

        # ── Section : Navigation frames ───────────────────────────────────────
        section("NAVIGATION")
        nav = tk.Frame(left, bg=BG_COLOR)
        nav.pack(fill="x", pady=3)
        self._btn(nav, "◀", self._prev_frame, width=4).pack(side="left")
        self._frame_label = tk.Label(nav, text="0 / 0", bg=BG_COLOR, fg=FG_COLOR,
                                     font=("Segoe UI", 9), width=8)
        self._frame_label.pack(side="left", expand=True)
        self._btn(nav, "▶", self._next_frame, width=4).pack(side="right")

        self._btn_play = self._btn(left, "▶  Play", self._toggle_play)
        self._btn_play.pack(fill="x", pady=(1, 4))

        # ── Section : Prétraitement ───────────────────────────────────────────
        section("PRÉ-TRAITEMENT")
        self._btn(left, "✂  Appliquer Crop", self._on_crop).pack(fill="x", pady=3)
        self._crop_toggle = tk.BooleanVar(value=False)
        tk.Checkbutton(left, text="Afficher image rognée",
                       variable=self._crop_toggle,
                       bg=BG_COLOR, fg=FG_COLOR, selectcolor=BTN_BG,
                       activebackground=BG_COLOR, activeforeground=FG_COLOR,
                       command=self._refresh_canvas).pack(anchor="w")

        self._anon_mode = tk.StringVar(value="hash")
        tk.Label(left, text="Mode anonymisation :", bg=BG_COLOR, fg=FG_COLOR,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))
        for mode, label in (("hash", "Hachage SHA-256"), ("remove", "Suppression"),
                             ("none", "Désactivée")):
            tk.Radiobutton(left, text=label, variable=self._anon_mode, value=mode,
                           bg=BG_COLOR, fg=FG_COLOR, selectcolor=BTN_BG,
                           activebackground=BG_COLOR).pack(anchor="w")

        self._btn(left, "🔒  Anonymiser", self._on_anonymize).pack(fill="x", pady=(6, 3))

        # ── Section : Analyse IA ──────────────────────────────────────────────
        section("ANALYSE IA")
        self._btn(left, "🧠  Lancer Analyse STARHE",
                  self._on_run_pipeline, accent=True).pack(fill="x", pady=3)

        # Résultats
        section("RÉSULTATS")
        self._risk_var  = tk.StringVar(value="Risque : —")
        self._det_var   = tk.StringVar(value="Détections : —")
        tk.Label(left, textvariable=self._risk_var,  bg=BG_COLOR, fg=FG_COLOR,
                 font=("Consolas", 9), anchor="w").pack(fill="x")
        tk.Label(left, textvariable=self._det_var,   bg=BG_COLOR, fg=FG_COLOR,
                 font=("Consolas", 9), anchor="w").pack(fill="x")

    def _build_right_panel(self, parent):
        right = tk.Frame(parent, bg=BG_COLOR)
        right.pack(side="left", fill="both", expand=True)

        # Canvas d'affichage
        canvas_frame = tk.Frame(right, bg="#11111b", relief="sunken", bd=1)
        canvas_frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(canvas_frame, bg="#11111b",
                                 highlightthickness=0,
                                 width=CANVAS_W, height=CANVAS_H)
        self._canvas.pack(fill="both", expand=True)
        self._canvas_text = self._canvas.create_text(
            CANVAS_W // 2, CANVAS_H // 2,
            text="Aucun DICOM chargé\nCliquez sur « Charger DICOM »",
            fill="#585b70", font=("Segoe UI", 13), justify="center"
        )

        # Zone de log
        tk.Label(right, text="Console", bg=BG_COLOR, fg=ACCENT,
                 font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x", pady=(6, 0))
        self._log_widget = scrolledtext.ScrolledText(
            right, height=8, bg="#11111b", fg="#6c7086",
            font=("Consolas", 8), state="disabled", relief="flat",
            insertbackground=FG_COLOR
        )
        self._log_widget.pack(fill="x")

    def _btn(self, parent, text, command, width=None, accent=False):
        kw = dict(text=text, command=command, bg=ACCENT if accent else BTN_BG,
                  fg="#1e1e2e" if accent else BTN_FG,
                  relief="flat", activebackground=BTN_BG,
                  activeforeground=FG_COLOR,
                  font=("Segoe UI", 9, "bold" if accent else "normal"),
                  padx=8, pady=5, cursor="hand2")
        if width:
            kw["width"] = width
        return tk.Button(parent, **kw)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _toggle_play(self):
        if self._frames_raw is None:
            return
        self._playing = not self._playing
        if self._playing:
            self._btn_play.config(text="⏸  Pause")
            self._play_step()
        else:
            self._btn_play.config(text="▶  Play")
            if self._play_after_id is not None:
                self.after_cancel(self._play_after_id)
                self._play_after_id = None

    def _play_step(self):
        if not self._playing or self._frames_raw is None:
            return
        n = len(self._frames_raw)
        self._frame_idx = (self._frame_idx + 1) % n
        self._update_frame_label()
        self._refresh_canvas()
        self._play_after_id = self.after(45, self._play_step)  # ~22 fps (FrameTime natif DICOM)

    def _on_load_dicom(self):
        path = filedialog.askopenfilename(
            title="Sélectionner un fichier DICOM",
            initialdir=DATA_DIR,
            filetypes=[("Fichiers DICOM", "*.dcm"), ("Tous fichiers", "*.*")]
        )
        if not path:
            return
        self._log(f"Chargement : {os.path.basename(path)}")
        try:
            ds = load_dicom(path)
            frames = extract_frames(ds)

            # Normalise → (T, H, W, 3) uint8
            if frames.ndim == 3:
                frames = np.stack([frame_to_uint8(f) for f in frames])
                frames = np.stack([frames] * 3, axis=-1)
            else:
                frames = np.stack([frame_to_uint8(f) for f in frames])

            self._frames_raw     = frames
            self._frames_cropped = None
            self._roi            = None
            self._frame_idx      = 0
            self._detections     = []
            self._crop_toggle.set(False)

            # Affiche métadonnées
            name  = str(getattr(ds, "PatientName",   "N/A"))
            pid   = str(getattr(ds, "PatientID",     "N/A"))
            mod   = str(getattr(ds, "Modality",      "N/A"))
            rows  = int(getattr(ds, "Rows",           0))
            cols  = int(getattr(ds, "Columns",        0))
            self._info_var.set(
                f"Patient : {name}\nID : {pid}\nModalité : {mod}\n"
                f"Taille : {rows}×{cols}\nFrames : {len(frames)}"
            )
            self._label_file.config(text=os.path.basename(path))
            if self._playing:
                self._toggle_play()  # stoppe la lecture si un autre DICOM était en cours
            self._update_frame_label()
            self._refresh_canvas()
            self._log(f"DICOM chargé — {len(frames)} frame(s), {rows}×{cols} px.")

        except Exception as exc:
            messagebox.showerror("Erreur de chargement", str(exc))
            self._log(f"ERREUR : {exc}", level="error")

    def _on_crop(self):
        if self._frames_raw is None:
            messagebox.showwarning("Aucun DICOM", "Chargez d'abord un fichier DICOM.")
            return
        self._log("Application du crop echographique…")
        try:
            cropped, roi = crop_clip(self._frames_raw)
            self._frames_cropped = cropped
            self._roi            = roi
            self._crop_toggle.set(True)
            self._refresh_canvas()
            x0, y0, x1, y1 = roi
            self._log(f"Crop appliqué — ROI : ({x0},{y0}) → ({x1},{y1}) "
                      f"| {cropped.shape[2]}×{cropped.shape[1]} px.")
        except Exception as exc:
            messagebox.showerror("Erreur Crop", str(exc))
            self._log(f"ERREUR crop : {exc}", level="error")

    def _on_anonymize(self):
        path = filedialog.askopenfilename(
            title="Sélectionner le DICOM à anonymiser",
            initialdir=DATA_DIR,
            filetypes=[("Fichiers DICOM", "*.dcm"), ("Tous fichiers", "*.*")]
        )
        if not path:
            return
        mode = self._anon_mode.get()
        out_path = path.replace(".dcm", f"_anon_{mode}.dcm")
        try:
            import pydicom
            ds = pydicom.dcmread(path, force=False)
            ds = anonymize(ds, mode=mode)
            ds.save_as(out_path)
            self._log(f"Anonymisation ({mode}) → {os.path.basename(out_path)}", level="success")
            messagebox.showinfo("Anonymisation terminée",
                                f"Fichier sauvegardé :\n{out_path}")
        except Exception as exc:
            messagebox.showerror("Erreur Anonymisation", str(exc))
            self._log(f"ERREUR anonymisation : {exc}", level="error")

    def _on_run_pipeline(self):
        """Lance l'analyse IA dans un thread pour ne pas bloquer l'UI."""
        if self._frames_raw is None:
            messagebox.showwarning("Aucun DICOM", "Chargez d'abord un fichier DICOM.")
            return
        self._log("Lancement de l'analyse STARHE (thread IA)…")
        t = threading.Thread(target=self._run_ia_thread, daemon=True)
        t.start()

    def _run_ia_thread(self):
        """Exécutée dans un thread secondaire."""
        try:
            frames = (self._frames_cropped
                      if self._frames_cropped is not None
                      else self._frames_raw)

            # STARHE-RISK
            self._log("  → STARHE-RISK (C3D) en cours…")
            from starhe_plugin.ai.starhe_risk import STARHERiskModel
            risk_result = STARHERiskModel().predict(frames)
            score = risk_result["risk_score"]
            label = risk_result["risk_label"]
            color = SUCCESS if label == "Faible" else DANGER
            self._risk_var.set(f"Risque : {label}  ({score:.1%})")
            self._log(f"  → RISK : {label} | score={score:.3f}", level="success")

            # STARHE-DETECT
            self._log("  → STARHE-DETECT (DINO-DETR) en cours…")
            from starhe_plugin.ai.starhe_detect import STARHEDetectModel
            mid  = len(frames) // 2
            dets = STARHEDetectModel().predict(frames[mid])
            self._detections = dets
            self._det_var.set(f"Détections : {len(dets)}")
            self._log(f"  → DETECT : {len(dets)} lésion(s) trouvée(s).", level="success")

            # Rafraîchit le canvas avec les bbox
            self.after(0, self._refresh_canvas)

        except Exception as exc:
            self._log(f"ERREUR IA : {exc}", level="error")

    # ── Affichage canvas ──────────────────────────────────────────────────────

    def _refresh_canvas(self):
        if self._frames_raw is None:
            return

        use_cropped = (self._crop_toggle.get()
                       and self._frames_cropped is not None)
        frames = self._frames_cropped if use_cropped else self._frames_raw
        idx    = min(self._frame_idx, len(frames) - 1)
        frame  = frames[idx].copy()

        # Superpose les détections avant le padding (coordonnées image rognée)
        if self._detections and use_cropped:
            frame = _draw_detections_on_array(frame, self._detections)

        # Pad au format original : le crop ne change pas le zoom d'affichage,
        # il ajoute juste un cadre noir autour de la zone utile.
        if use_cropped:
            orig_h = self._frames_raw.shape[1]
            orig_w = self._frames_raw.shape[2]
            fh, fw = frame.shape[:2]
            if fh != orig_h or fw != orig_w:
                padded = np.zeros((orig_h, orig_w, 3), dtype=np.uint8)
                y0 = (orig_h - fh) // 2
                x0 = (orig_w - fw) // 2
                padded[y0:y0 + fh, x0:x0 + fw] = frame
                frame = padded

        cw = self._canvas.winfo_width()  or CANVAS_W
        ch = self._canvas.winfo_height() or CANVAS_H

        photo = _ndarray_to_photoimage(frame, cw, ch)
        self._photo_ref = photo       # éviter le GC

        self._canvas.delete("all")
        self._canvas.create_image(cw // 2, ch // 2, anchor="center", image=photo)

    def _prev_frame(self):
        if self._frames_raw is None:
            return
        if self._playing:
            self._toggle_play()
        n = len(self._frames_raw)
        self._frame_idx = (self._frame_idx - 1) % n
        self._update_frame_label()
        self._refresh_canvas()

    def _next_frame(self):
        if self._frames_raw is None:
            return
        if self._playing:
            self._toggle_play()
        n = len(self._frames_raw)
        self._frame_idx = (self._frame_idx + 1) % n
        self._update_frame_label()
        self._refresh_canvas()

    def _update_frame_label(self):
        if self._frames_raw is None:
            self._frame_label.config(text="0 / 0")
            return
        n = len(self._frames_raw)
        self._frame_label.config(text=f"{self._frame_idx + 1} / {n}")

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, message: str, level: str = "info"):
        color_map = {
            "info"   : FG_COLOR,
            "success": SUCCESS,
            "warning": WARNING,
            "error"  : DANGER,
        }
        color = color_map.get(level, FG_COLOR)
        prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "·")

        self._log_widget.configure(state="normal")
        self._log_widget.insert("end", f" {prefix}  {message}\n")

        # Coloration de la dernière ligne
        last_line_start = self._log_widget.index("end-2l linestart")
        last_line_end   = self._log_widget.index("end-1c")
        tag = f"tag_{level}"
        self._log_widget.tag_config(tag, foreground=color)
        self._log_widget.tag_add(tag, last_line_start, last_line_end)

        self._log_widget.configure(state="disabled")
        self._log_widget.see("end")

        # Miroir go_print
        import json, sys
        print(f"GO_PRINT|{level}|" + json.dumps({"level": level, "message": message}),
              flush=True)


# ── Point d'entrée ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = STARHEApp()
    app.mainloop()
