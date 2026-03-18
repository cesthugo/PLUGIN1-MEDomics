"""
ui/prototype_tkinter.py — Prototype de validation STARHE
=========================================================
Interface inspirée de MEDomics v1.8.0 :
  - Barre de titre sombre (#151521) avec logo MEDomics
  - Sidebar gauche sombre (280 px) : contrôles et résultats
  - Zone principale claire (#f4f6fb) : visionneuse DICOM + console
  - Palette MEDomics : bleu primaire #1565C0, cartes blanches, Segoe UI

Mise en page :
  ┌─────────────────────────────────────────────────────────────────┐
  │  ⬡ MEDomics  │  STARHE — Détection cancer du foie        v0.1 │  ← header sombre
  ├───────────────┬─────────────────────────────────────────────────┤
  │  SIDEBAR      │  ZONE PRINCIPALE (#f4f6fb)                      │
  │  (#151521)    │  ┌─────────────────────────────────────────┐   │
  │  FICHIER ──── │  │  Visionneuse DICOM (fond sombre)         │   │
  │   Charger     │  │                                          │   │
  │  NAVIGATION ─ │  └─────────────────────────────────────────┘   │
  │   ◀  X/N  ▶  │  Console ─────────────────────────────────────  │
  │   ▶ Play      │  ▌ log messages...                             │
  │  PRÉ-TRAIT ── │                                                  │
  │   ✂ Crop      │                                                  │
  │   🔒 Anon     │                                                  │
  │  ANALYSE IA ─ │                                                  │
  │   🧠 Lancer   │                                                  │  ← bleu #1565C0
  │  RÉSULTATS ── │                                                  │
  └───────────────┴─────────────────────────────────────────────────┘

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
from starhe_plugin.dicom.prepus_bridge import preprocess_with_prepus
from starhe_plugin.dicom.anonymizer import anonymize
from starhe_plugin.config           import DATA_DIR, PROJECT_ROOT


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

# ─── Palette MEDomics ──────────────────────────────────────────────────────
SIDEBAR_BG  = "#151521"   # fond barre latérale (très sombre)
SIDEBAR_SEC = "#1e1d2f"   # sections / séparateurs sidebar
SIDEBAR_HOV = "#252438"   # hover sidebar
MAIN_BG     = "#f4f6fb"   # fond zone principale
CARD_BG     = "#ffffff"   # fond cartes / panneaux
CANVAS_BG   = "#0d1117"   # visionneuse DICOM (toujours sombre)
LOG_BG      = "#111118"   # fond console log
BLUE        = "#1565C0"   # bleu primaire MEDomics (CTA)
BLUE_HOV    = "#1976D2"   # hover bouton primaire
BLUE_TEXT   = "#1565C0"   # titres sections zone claire
SBAR_FG     = "#e2e8f0"   # texte clair sur fond sombre
SBAR_MUTED  = "#7c8899"   # texte secondaire sidebar
MAIN_FG     = "#1a202c"   # texte principal zone claire
BORDER      = "#cbd5e0"   # bordure cartes
SUCCESS_FG  = "#4ade80"   # vert console
WARN_FG     = "#fb923c"   # orange console
DANGER_FG    = "#f87171"   # rouge console
CARD_BORDER  = "#e2e8f0"   # bordure visible des cartes
CARD_SHADOW  = "#d4d9e4"   # ombre portée simulée (cadre derrière carte)
RISK_LOW_FG  = "#4ade80"   # vert — risque faible CHC
RISK_HIGH_FG = "#f87171"   # rouge — risque élevé CHC

CANVAS_W  = 640
CANVAS_H  = 500
APP_TITLE = "STARHE Plugin — Détection CHC  |  MEDomics"

FONT_TITLE  = ("Segoe UI", 12, "bold")
FONT_SEC    = ("Segoe UI",  7, "bold")
FONT_BODY   = ("Segoe UI",  9)
FONT_SMALL  = ("Segoe UI",  8)
FONT_MONO   = ("Consolas",  8)
FONT_BTN    = ("Segoe UI",  9,  "bold")
FONT_BTN_P  = ("Segoe UI", 10, "bold")
FONT_NAV    = ("Segoe UI", 13, "bold")  # compteur de frames de navigation


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
        self.configure(bg=MAIN_BG)
        self.resizable(True, True)
        self.minsize(1020, 680)

        # ── État interne ──────────────────────────────────────────────────────
        self._frames_raw      : np.ndarray | None = None  # (T, H, W, 3) uint8
        self._frames_cropped  : np.ndarray | None = None
        self._frames_backscan : np.ndarray | None = None  # résultat backscan prepUS
        self._frames_crop_only: np.ndarray | None = None  # résultat crop-seulement prepUS
        self._roi             : tuple | None      = None
        self._frame_idx       : int               = 0
        self._detections    : list[dict]        = []
        self._show_cropped  : bool              = False
        self._photo_ref     = None   # garde la référence PyImage en vie
        self._playing       : bool              = False
        self._play_after_id = None   # ID retourné par self.after()
        self._dark_mode     : bool              = False   # thème clair par défaut

        # ttk style pour le Scale de navigation (doit être créé après super().__init__)
        _sty = ttk.Style()
        _sty.theme_use("clam")
        _sty.configure("Sidebar.Horizontal.TScale",
                       background=SIDEBAR_BG,
                       troughcolor=SIDEBAR_SEC,
                       sliderthickness=12, sliderlength=14)

        self._build_ui()
        self._log("Bienvenue dans STARHE Plugin  —  interface MEDomics.")
        self._log("Chargez un fichier DICOM (.dcm) dans le panneau latéral pour commencer.")

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Barre de titre MEDomics ─────────────────────────────────────────────
        header = tk.Frame(self, bg=SIDEBAR_BG, height=50)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Logo MEDomics : image PNG réelle
        _logo_path = os.path.join(PROJECT_ROOT, "MEDomicsLab_LOGO.png")
        self._logo_img = None   # garde la référence pour éviter le GC
        try:
            _pil_logo = Image.open(_logo_path).convert("RGBA")
            # Fond header (#151521) pour remplacer la transparence PNG
            _bg = Image.new("RGBA", _pil_logo.size, "#151521")
            _bg.paste(_pil_logo, mask=_pil_logo.split()[3])
            _pil_logo = _bg.convert("RGB")
            _pil_logo.thumbnail((38, 38), Image.LANCZOS)
            self._logo_img = ImageTk.PhotoImage(_pil_logo)
            tk.Label(header, image=self._logo_img,
                     bg=SIDEBAR_BG).pack(side="left", padx=(10, 4), pady=6)
        except Exception:
            # Fallback : initiales "M" si le fichier est absent
            tk.Label(header, text="M", bg="#1565C0", fg="#fff",
                     font=("Segoe UI", 14, "bold"), width=2,
                     relief="flat").pack(side="left", padx=(10, 4), pady=6)

        tk.Label(header, text=" │ ", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=("Segoe UI", 13)).pack(side="left")
        tk.Label(header, text="STARHE — Détection cancer du foie",
                 bg=SIDEBAR_BG, fg=SBAR_FG,
                 font=("Segoe UI", 11)).pack(side="left")
        tk.Label(header, text="v0.1.0-prototype", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=("Segoe UI", 8)).pack(side="right", padx=16)

        # Ligne de séparation 1 px (like MEDomics divider)
        tk.Frame(self, bg="#0a0a14", height=1).pack(fill="x")

        # Corps : sidebar sombre + zone principale claire
        body = tk.Frame(self, bg=MAIN_BG)
        body.pack(fill="both", expand=True)

        self._build_sidebar(body)
        tk.Frame(body, bg="#0a0a14", width=1).pack(side="left", fill="y")
        self._build_main(body)

    def _build_sidebar(self, parent):
        """Barre latérale sombre style MEDomics."""
        sb = tk.Frame(parent, bg=SIDEBAR_BG, width=270)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        # ── Bouton thème en bas (doit être packé AVANT le contenu scrollable) ──
        sb_footer = tk.Frame(sb, bg="#0d0d1a", height=46)
        sb_footer.pack(side="bottom", fill="x")
        sb_footer.pack_propagate(False)
        self._sb_theme_btn = tk.Button(
            sb_footer, text="🌙   Thème sombre",
            command=self._toggle_theme,
            bg="#0d0d1a", fg=SBAR_MUTED,
            relief="flat", bd=0,
            activebackground=SIDEBAR_HOV, activeforeground=SBAR_FG,
            font=FONT_SMALL, cursor="hand2", anchor="w", padx=14
        )
        self._sb_theme_btn.pack(fill="both", expand=True)

        # ── Zone scrollable pour le contenu principal ─────────────────────────
        _sb_canvas = tk.Canvas(sb, bg=SIDEBAR_BG, highlightthickness=0, bd=0)
        _sb_vbar   = ttk.Scrollbar(sb, orient="vertical", command=_sb_canvas.yview)
        _sb_canvas.configure(yscrollcommand=_sb_vbar.set)
        _sb_vbar  .pack(side="right", fill="y")
        _sb_canvas.pack(side="left",  fill="both", expand=True)

        sc = tk.Frame(_sb_canvas, bg=SIDEBAR_BG)
        _sc_id = _sb_canvas.create_window((0, 0), window=sc, anchor="nw")

        def _sb_on_frame_configure(event, c=_sb_canvas):
            c.configure(scrollregion=c.bbox("all"))

        def _sb_on_canvas_configure(event, c=_sb_canvas, wid=_sc_id):
            c.itemconfigure(wid, width=event.width)

        sc        .bind("<Configure>", _sb_on_frame_configure)
        _sb_canvas.bind("<Configure>", _sb_on_canvas_configure)

        # Défilement à la molette quand la souris survole la sidebar
        def _sb_scroll(event, c=_sb_canvas):
            c.yview_scroll(int(-1 * (event.delta / 120)), "units")

        _sb_canvas.bind("<Enter>", lambda _: _sb_canvas.bind_all("<MouseWheel>", _sb_scroll))
        _sb_canvas.bind("<Leave>", lambda _: _sb_canvas.unbind_all("<MouseWheel>"))

        def _sh(title: str):
            """En-tête de section sidebar avec barre d'accent bleu gauche."""
            frm = tk.Frame(sc, bg=SIDEBAR_BG)
            frm.pack(fill="x", pady=(16, 4))
            tk.Frame(frm, bg=BLUE, width=3).pack(side="left", fill="y")
            tk.Label(frm, text=f"  {title.upper()}", bg=SIDEBAR_BG, fg="#9ca3af",
                     font=("Segoe UI", 7, "bold"), anchor="w") \
              .pack(side="left", fill="x", expand=True, pady=5)

        # ─── FICHIER DICOM ───────────────────────────────────────────────────
        _sh("Fichier DICOM")
        self._btn_load = self._sbtn(sc, "📂   Charger un fichier DICOM",
                                    self._on_load_dicom)
        self._btn_load.pack(fill="x", padx=10, pady=(6, 3))

        self._label_file = tk.Label(sc, text="Aucun fichier sélectionné",
                                    bg=SIDEBAR_BG, fg=SBAR_MUTED,
                                    font=FONT_SMALL, wraplength=240,
                                    anchor="w", justify="left")
        self._label_file.pack(fill="x", padx=14)

        self._info_var = tk.StringVar(value="")
        tk.Label(sc, textvariable=self._info_var, bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_MONO, justify="left", anchor="nw",
                 wraplength=240).pack(fill="x", padx=14, pady=(2, 0))

        # ─── NAVIGATION ──────────────────────────────────────────────────────
        _sh("Navigation")
        nav_row = tk.Frame(sc, bg=SIDEBAR_BG)
        nav_row.pack(fill="x", padx=10, pady=(6, 2))
        self._sibtn(nav_row, "◀", self._prev_frame).pack(side="left")
        self._frame_label = tk.Label(nav_row, text="— / —",
                                     bg=SIDEBAR_BG, fg="#ffffff",
                                     font=FONT_NAV, width=8, anchor="center")
        self._frame_label.pack(side="left", expand=True)
        self._sibtn(nav_row, "▶", self._next_frame).pack(side="right")

        # Scrollbar horizontale de navigation entre les frames
        self._frame_scale = ttk.Scale(sc, orient="horizontal",
                                      from_=0, to=1, value=0,
                                      command=self._on_scale_drag,
                                      style="Sidebar.Horizontal.TScale")
        self._frame_scale.pack(fill="x", padx=10, pady=(2, 2))

        self._btn_play = self._sbtn(sc, "▶   Play", self._toggle_play)
        self._btn_play.pack(fill="x", padx=10, pady=(2, 6))

        # ─── PRÉ-TRAITEMENT ──────────────────────────────────────────────────
        _sh("Pré-traitement")
        self._btn_preprocess = self._sbtn(sc, "⚙   Pré-Traitement",
                                          self._on_preprocess)
        self._btn_preprocess.pack(fill="x", padx=10, pady=(6, 2))

        # Indicateur d'état du pré-traitement
        self._preprocess_status = tk.Label(sc, text="",
                                           bg=SIDEBAR_BG, fg=SBAR_MUTED,
                                           font=FONT_SMALL, anchor="w")
        self._preprocess_status.pack(fill="x", padx=14, pady=(0, 4))

        # Options pré-traitement
        prepus_opts = tk.Frame(sc, bg=SIDEBAR_BG)
        prepus_opts.pack(fill="x", padx=16, pady=(0, 2))
        self._prepus_bsc = tk.BooleanVar(value=True)
        tk.Checkbutton(prepus_opts, text="Backscan (512×512)",
                       variable=self._prepus_bsc,
                       command=self._on_bsc_toggle,
                       bg=SIDEBAR_BG, fg=SBAR_FG, selectcolor=SIDEBAR_SEC,
                       activebackground=SIDEBAR_BG, activeforeground=SBAR_FG,
                       cursor="hand2", font=FONT_SMALL).pack(anchor="w")

        self._crop_toggle = tk.BooleanVar(value=False)
        tk.Checkbutton(sc, text="Afficher résultat pré-traitement",
                       variable=self._crop_toggle, command=self._refresh_canvas,
                       bg=SIDEBAR_BG, fg=SBAR_FG, selectcolor=SIDEBAR_SEC,
                       activebackground=SIDEBAR_BG, activeforeground=SBAR_FG,
                       cursor="hand2", font=FONT_SMALL).pack(anchor="w", padx=16)

        tk.Label(sc, text="Mode anonymisation :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(8, 2))
        self._anon_mode = tk.StringVar(value="hash")
        for val, lbl in (("hash", "Hachage SHA-256"),
                         ("remove", "Suppression"),
                         ("none", "Désactivée")):
            tk.Radiobutton(sc, text=lbl, variable=self._anon_mode, value=val,
                           bg=SIDEBAR_BG, fg=SBAR_FG, selectcolor=SIDEBAR_SEC,
                           activebackground=SIDEBAR_BG, activeforeground=SBAR_FG,
                           cursor="hand2", font=FONT_SMALL).pack(anchor="w", padx=26)

        self._sbtn(sc, "🔒   Anonymiser",
                   self._on_anonymize).pack(fill="x", padx=10, pady=(6, 6))

        # ─── ANALYSE IA ──────────────────────────────────────────────────────
        _sh("Analyse IA")
        self._pbtn(sc, "🧠   Lancer l'analyse STARHE",
                   self._on_run_pipeline).pack(fill="x", padx=10, pady=(8, 6))

        # ─── RÉSULTATS ───────────────────────────────────────────────────────
        _sh("Résultats")
        risk_row = tk.Frame(sc, bg=SIDEBAR_BG)
        risk_row.pack(fill="x", padx=14, pady=(6, 1))
        tk.Label(risk_row, text="Risque CHC :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL, anchor="w").pack(side="left")
        self._risk_lbl = tk.Label(risk_row, text="—", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                                   font=("Segoe UI", 9, "bold"), anchor="w")
        self._risk_lbl.pack(side="left", padx=(6, 0))

        det_row = tk.Frame(sc, bg=SIDEBAR_BG)
        det_row.pack(fill="x", padx=14, pady=(1, 12))
        tk.Label(det_row, text="Lésions :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL, anchor="w").pack(side="left")
        self._det_lbl = tk.Label(det_row, text="—", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                                  font=("Segoe UI", 9, "bold"), anchor="w")
        self._det_lbl.pack(side="left", padx=(6, 0))

    def _build_main(self, parent):
        """Zone principale claire : carte visionneuse + console."""
        self._main_frame = tk.Frame(parent, bg=MAIN_BG)
        self._main_frame.pack(side="left", fill="both", expand=True)
        main = self._main_frame

        # ── Carte visionneuse DICOM (avec ombre portée simulée + bordure subtile) ───
        self._card_wrap = tk.Frame(main, bg=CARD_SHADOW, bd=0)
        self._card_wrap.pack(fill="both", expand=True, padx=13, pady=(10, 4))
        self._card = tk.Frame(self._card_wrap, bg=CARD_BG, bd=0,
                              highlightbackground=CARD_BORDER, highlightthickness=1)
        self._card.pack(fill="both", expand=True, padx=1, pady=1)
        card = self._card

        # En-tête de la carte
        self._card_hdr = tk.Frame(card, bg=CARD_BG, height=36)
        self._card_hdr.pack(fill="x")
        self._card_hdr.pack_propagate(False)
        self._card_hdr_lbl = tk.Label(self._card_hdr, text="Visionneuse DICOM",
                                       bg=CARD_BG, fg=BLUE_TEXT,
                                       font=("Segoe UI", 9, "bold"))
        self._card_hdr_lbl.pack(side="left", padx=12, pady=8)
        # Badge indiquant le mode d'affichage courant
        self._mode_badge = tk.Label(self._card_hdr, text="ORIGINAL",
                                     bg="#dbeafe", fg="#1d4ed8",
                                     font=("Segoe UI", 7, "bold"),
                                     padx=7, pady=2)
        self._mode_badge.pack(side="left", padx=(6, 0))
        self._card_divider = tk.Frame(card, bg=BORDER, height=1)
        self._card_divider.pack(fill="x")

        # Canvas DICOM (fond sombre à l'intérieur de la carte)
        canvas_wrap = tk.Frame(card, bg=CANVAS_BG)
        canvas_wrap.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(canvas_wrap, bg=CANVAS_BG,
                                 highlightthickness=0,
                                 width=CANVAS_W, height=CANVAS_H)
        self._canvas.pack(fill="both", expand=True)
        self._canvas_text = self._canvas.create_text(
            CANVAS_W // 2, CANVAS_H // 2,
            text="Aucun DICOM chargé\n\nUtilisez  « Charger un fichier DICOM »  dans le panneau latéral",
            fill="#2a2a3e", font=("Segoe UI", 12), justify="center"
        )

        # ── Console log ──────────────────────────────────────────────────────
        self._log_hdr_frame = tk.Frame(main, bg=MAIN_BG)
        self._log_hdr_frame.pack(fill="x", padx=14, pady=(0, 2))
        self._log_hdr_lbl = tk.Label(self._log_hdr_frame, text="Console",
                                      bg=MAIN_BG, fg=BLUE_TEXT,
                                      font=("Segoe UI", 9, "bold"))
        self._log_hdr_lbl.pack(side="left")
        self._log_widget = scrolledtext.ScrolledText(
            main, height=7, bg=LOG_BG, fg="#8892a4",
            font=FONT_MONO, state="disabled", relief="flat",
            insertbackground=SBAR_FG, bd=0
        )
        self._log_widget.pack(fill="x", padx=14, pady=(0, 10))

    def _sbtn(self, parent, text: str, command) -> tk.Button:
        """Bouton secondaire sidebar (fond SIDEBAR_SEC, texte clair)."""
        return tk.Button(parent, text=text, command=command,
                         bg=SIDEBAR_SEC, fg=SBAR_FG,
                         relief="flat", bd=0,
                         activebackground=SIDEBAR_HOV,
                         activeforeground="#ffffff",
                         font=FONT_BTN, padx=10, pady=6,
                         cursor="hand2", anchor="w")

    def _sibtn(self, parent, text: str, command) -> tk.Button:
        """Petit bouton icône carré pour la navigation."""
        return tk.Button(parent, text=text, command=command,
                         bg=SIDEBAR_SEC, fg=SBAR_FG,
                         relief="flat", bd=0,
                         activebackground=BLUE, activeforeground="#ffffff",
                         font=("Segoe UI", 10, "bold"), width=4, pady=4,
                         cursor="hand2")

    def _pbtn(self, parent, text: str, command) -> tk.Button:
        """Bouton primaire bleu MEDomics (CTA équivalent de 'Set Workspace')."""
        return tk.Button(parent, text=text, command=command,
                         bg=BLUE, fg="#ffffff",
                         relief="flat", bd=0,
                         activebackground=BLUE_HOV,
                         activeforeground="#ffffff",
                         font=FONT_BTN_P, padx=10, pady=8,
                         cursor="hand2", anchor="w")

    # ── Thème clair / sombre ──────────────────────────────────────────────────

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        if self._dark_mode:
            mb  = "#1a1a2e"   # fond zone principale → sombre
            cb  = "#16213e"   # fond carte
            cft = "#89b4fa"   # titres (bleu clair)
            div = "#2a2a4e"   # séparateur
            lbg = LOG_BG      # console (inchangé)
            icon, lbl = "☀", "Thème clair"
        else:
            mb  = MAIN_BG
            cb  = CARD_BG
            cft = BLUE_TEXT
            div = BORDER
            lbg = LOG_BG
            icon, lbl = "🌙", "Thème sombre"

        self.configure(bg=mb)
        self._main_frame .configure(bg=mb)
        self._card       .configure(bg=cb)
        self._card_hdr   .configure(bg=cb)
        self._card_hdr_lbl.configure(bg=cb, fg=cft)
        self._card_divider.configure(bg=div)
        self._log_hdr_frame.configure(bg=mb)
        self._log_hdr_lbl  .configure(bg=mb, fg=cft)
        self._log_widget   .configure(bg=lbg)
        self._sb_theme_btn .configure(text=f"{icon}   {lbl}")
        if hasattr(self, "_card_wrap"):
            self._card_wrap.configure(bg="#c8cdd8" if self._dark_mode else CARD_SHADOW)
        if hasattr(self, "_mode_badge"):
            if self._dark_mode:
                self._mode_badge.configure(bg="#1e3a5f", fg="#90caf9")
            else:
                self._mode_badge.configure(bg="#dbeafe", fg="#1d4ed8")

    # ── Bascule backscan / crop-seulement ─────────────────────────────────────

    def _on_bsc_toggle(self):
        """Bascule la vue entre backscan et crop-seulement si les deux sont disponibles."""
        if self._frames_backscan is None and self._frames_crop_only is None:
            return  # prepUS pas encore exécuté, la checkbox n'est qu'un paramètre
        want_bsc = self._prepus_bsc.get()
        if want_bsc and self._frames_backscan is not None:
            self._frames_cropped = self._frames_backscan
            self._log("Vue → backscan (512×512)")
        elif not want_bsc and self._frames_crop_only is not None:
            self._frames_cropped = self._frames_crop_only
            self._log("Vue → crop seulement")
        else:
            self._log("Version demandée non disponible — relancez prepUS avec ce mode.",
                      level="warning")
            return
        self._crop_toggle.set(True)
        self._refresh_canvas()

    # ── Scale de navigation ───────────────────────────────────────────────────

    def _on_scale_drag(self, val: str):
        """Appelé à chaque déplacement du curseur de la scrollbar de navigation."""
        if self._frames_raw is None:
            return
        n   = len(self._frames_raw)
        idx = max(0, min(n - 1, int(float(val))))
        if idx == self._frame_idx:
            return
        if self._playing:
            self._toggle_play()   # pause à la navigation manuelle
        self._frame_idx = idx
        self._frame_label.config(text=f"{idx + 1} / {n}")
        self._refresh_canvas()

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _toggle_play(self):
        if self._frames_raw is None:
            return
        self._playing = not self._playing
        if self._playing:
            self._btn_play.config(text="⏸   Pause")
            self._play_step()
        else:
            self._btn_play.config(text="▶   Play")
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

            self._frames_raw       = frames
            self._frames_cropped   = None
            self._frames_backscan  = None
            self._frames_crop_only = None
            self._roi              = None
            self._frame_idx        = 0
            self._detections       = []
            self._crop_toggle.set(False)
            self._prepus_bsc.set(True)   # réinitialise backscan=on à chaque nouveau fichier

            # Affiche métadonnées
            name  = str(getattr(ds, "PatientName",   "N/A"))
            pid   = str(getattr(ds, "PatientID",     "N/A"))
            mod   = str(getattr(ds, "Modality",      "N/A"))
            rows  = int(getattr(ds, "Rows",           0))
            cols  = int(getattr(ds, "Columns",        0))
            self._info_var.set(
                f"Patient : {name}\nID      : {pid}\nModalité: {mod}\n"
                f"Taille  : {rows}×{cols}\nFrames  : {len(frames)}"
            )
            self._label_file.config(text=os.path.basename(path), fg=SBAR_FG)
            if self._playing:
                self._toggle_play()  # stoppe la lecture si un autre DICOM était en cours
            # Recalibre la scrollbar sur la durée du nouveau clip
            self._frame_scale.configure(to=max(1, len(frames) - 1))
            self._frame_scale.set(0)
            self._update_frame_label()
            self._refresh_canvas()
            self._log(f"DICOM chargé — {len(frames)} frame(s), {rows}×{cols} px.")

        except Exception as exc:
            messagebox.showerror("Erreur de chargement", str(exc))
            self._log(f"ERREUR : {exc}", level="error")

    def _on_preprocess(self):
        """Lance le pré-traitement prepUS dans un thread (backscan selon checkbox)."""
        if self._frames_raw is None:
            messagebox.showwarning("Aucun DICOM", "Chargez d'abord un fichier DICOM.")
            return
        self._btn_preprocess.config(state="disabled")
        self._preprocess_status.config(text="⟳  Traitement en cours…", fg=WARN_FG)
        self._log("Pré-traitement prepUS (removeLayout) en cours…")
        t = threading.Thread(target=self._run_prepus_thread, daemon=True)
        t.start()

    def _run_prepus_thread(self):
        """
        Toujours lancé avec back_scan_conversion=True pour obtenir les deux sorties :
          - backscan_video.mp4 → image rectangulaire 512×512 (scan inverse)
          - video.mp4          → crop masqué par prepUS (annotations supprimées)
        La checkbox détermine uniquement ce qui est AFFICHÉ après le traitement.
        """
        try:
            want_bsc = self._prepus_bsc.get()
            self._log(f"  → removeLayoutFile | backscan=on "
                      f"| affichage={'backscan' if want_bsc else 'crop masqué'}…")
            backscan_arr, crop_only_arr, info = preprocess_with_prepus(
                self._frames_raw,
                fps=22.0,
                thresh=-1.0,
                back_scan_conversion=True,   # toujours True → produit video.mp4 masqué
                backscan_width=512,
                backscan_height=512,
            )
            import numpy as _np

            def _rgb(a):
                return _np.stack([a, a, a], axis=-1)

            self._frames_backscan  = _rgb(backscan_arr)
            self._frames_crop_only = _rgb(crop_only_arr) if crop_only_arr is not None \
                                     else self._frames_backscan

            # Affiche selon la préférence de la checkbox
            self._frames_cropped = self._frames_backscan if want_bsc \
                                   else self._frames_crop_only
            self._roi = None

            ref = backscan_arr if want_bsc \
                  else (crop_only_arr if crop_only_arr is not None else backscan_arr)
            shape_str = f"{ref.shape[2]}×{ref.shape[1]}"
            msg = f"Pré-traitement terminé — {ref.shape[0]} frames, {shape_str} px"
            if info and "crop" in info:
                c = info["crop"]
                msg += f" | crop y=[{c['ymin']},{c['ymax']}] x=[{c['xmin']},{c['xmax']}]"
            msg += "  ·  ☑ bascule backscan/crop disponible"

            self.after(0, lambda: self._crop_toggle.set(True))
            self.after(0, self._refresh_canvas)
            self.after(0, lambda: self._btn_preprocess.config(state="normal"))
            self.after(0, lambda: self._preprocess_status.config(
                text="✓  Terminé", fg=SUCCESS_FG))
            self._log(msg, level="success")
        except Exception as exc:
            self.after(0, lambda: self._btn_preprocess.config(state="normal"))
            self.after(0, lambda: self._preprocess_status.config(
                text="✗  Erreur", fg=DANGER_FG))
            self._log(f"ERREUR pré-traitement : {exc}", level="error")
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
            risk_fg = RISK_HIGH_FG if any(
                w in label.lower() for w in ("élevé", "high")
            ) else RISK_LOW_FG
            self.after(0, lambda l=label, s=score, c=risk_fg:
                       self._risk_lbl.config(text=f"{l}  ({s:.1%})", fg=c))
            self._log(f"  → RISK : {label} | score={score:.3f}", level="success")

            # STARHE-DETECT
            self._log("  → STARHE-DETECT (DINO-DETR) en cours…")
            from starhe_plugin.ai.starhe_detect import STARHEDetectModel
            mid  = len(frames) // 2
            dets = STARHEDetectModel().predict(frames[mid])
            self._detections = dets
            det_fg = WARN_FG if len(dets) > 0 else SUCCESS_FG
            self.after(0, lambda n=len(dets), c=det_fg:
                       self._det_lbl.config(text=str(n), fg=c))
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

        # Met à jour le badge de mode d'affichage
        if use_cropped and self._frames_backscan is not None and self._prepus_bsc.get():
            mode_txt = "BACKSCAN 512×512"
        elif use_cropped:
            mode_txt = "CROP + MASQUE"
        else:
            mode_txt = "ORIGINAL"
        if hasattr(self, "_mode_badge"):
            self._mode_badge.config(text=mode_txt)

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
            self._frame_label.config(text="— / —")
            return
        n = len(self._frames_raw)
        self._frame_label.config(text=f"{self._frame_idx + 1} / {n}")
        # Synchronise le curseur de la scrollbar avec l'index courant
        self._frame_scale.set(self._frame_idx)

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, message: str, level: str = "info"):
        color_map = {
            "info"   : "#8892a4",
            "success": SUCCESS_FG,
            "warning": WARN_FG,
            "error"  : DANGER_FG,
        }
        color = color_map.get(level, "#8892a4")
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
