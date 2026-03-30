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
import time
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
from starhe_plugin.dicom.anonymizer import anonymize, remove_pixel_burnin
from starhe_plugin.config           import DATA_DIR, PROJECT_ROOT, DICOM_SENSITIVE_TAGS
from starhe_plugin.utils.go_print   import set_log_sink


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
APP_TITLE = "Plugin1 Hugo  |  STARHE - Detection CHC"

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
    """Superpose les bboxes de détection sur une copie du frame."""
    import cv2
    vis = frame.copy()
    for det in detections:
        x0, y0, x1, y1 = (int(v) for v in det["bbox"])   # float → int requis par cv2
        color = (255, 80, 80) if "tumor" in det["label"] else (80, 200, 80)
        cv2.rectangle(vis, (x0, y0), (x1, y1), color, 2)
        cv2.putText(vis, f"{det['label']} {det['score']:.2f}",
                    (x0, max(y0 - 6, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    return vis


# ─────────────────────────────────────────────────────────────────────────────
#  Dialogue d'ajustement générique (contraste / luminosité)
# ─────────────────────────────────────────────────────────────────────────────

class _AdjustDialog(tk.Toplevel):
    """Petite fenêtre flottante avec slider pour ajuster une valeur image."""

    def __init__(self, master, title: str, initial: float,
                 min_val: float, max_val: float, neutral: float,
                 callback):
        super().__init__(master)
        self.title(title)
        self.configure(bg=SIDEBAR_BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        tk.Label(self, text=title, bg=SIDEBAR_BG, fg=SBAR_FG,
                 font=FONT_BTN).pack(pady=(12, 4), padx=20)

        self._var = tk.DoubleVar(value=initial)
        self._lbl = tk.Label(self, text=f"{initial:.2f}",
                             bg=SIDEBAR_BG, fg=SBAR_FG,
                             font=FONT_MONO, width=7)
        self._lbl.pack()

        def _on_change(val):
            v = float(val)
            self._lbl.config(text=f"{v:.2f}")
            callback(v)

        ttk.Scale(self, orient="horizontal", from_=min_val, to=max_val,
                  variable=self._var, command=_on_change,
                  length=220).pack(padx=20, pady=(4, 6))

        _neutral = neutral
        tk.Button(self, text="Réinitialiser",
                  command=lambda n=_neutral: (
                      self._var.set(n), _on_change(n)),
                  bg=SIDEBAR_SEC, fg=SBAR_FG, relief="flat",
                  font=FONT_SMALL, cursor="hand2",
                  pady=4).pack(pady=(0, 12), padx=20, fill="x")


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
        self._frame_idx            : int               = 0
        self._detections_per_frame : list[list[dict]]  = []
        self._show_cropped         : bool              = False
        self._original_sensitive   : list              = []   # valeurs avant anonymisation
        self._kept_metadata        : list              = []   # métadonnées conservées
        self._photo_ref     = None   # garde la référence PyImage en vie
        self._playing       : bool              = False
        self._play_after_id = None   # ID retourné par self.after()
        self._dark_mode     : bool              = False   # thème clair par défaut
        # ── Lecture vidéo avancée ─────────────────────────────────────────────
        self._base_fps      : float           = 22.0         # fps natif du DICOM
        self._speed_mult    : float           = 1.0          # multiplicateur (×)
        self._play_fps      : float           = 22.0         # fps effectif = base × mult
        self._loop_var      : tk.BooleanVar   = tk.BooleanVar(value=True)

        # ── Vue interactive (pan / zoom / mesure / series scroll) ─────────────
        self._view_mode     : str             = "normal"     # "normal"|"pan"|"measure"|"series"
        self._zoom          : float           = 1.0
        self._pan_x         : float           = 0.0
        self._pan_y         : float           = 0.0
        self._drag_start    : tuple | None    = None         # (ex, ey, pan_x, pan_y)
        self._measure_pts   : list            = []           # [(x,y), (x,y)]
        self._measure_items : list            = []           # IDs canvas overlay
        self._contrast      : float           = 1.0          # 0.1 – 3.0
        self._brightness    : float           = 0.0          # -100 – +100
        self._pixel_spacing : tuple | None    = None         # (row_mm, col_mm) extrait du tag PixelSpacing DICOM
        # ttk style pour le Scale de navigation (doit être créé après super().__init__)
        _sty = ttk.Style()
        _sty.theme_use("clam")
        _sty.configure("Sidebar.Horizontal.TScale",
                       background=SIDEBAR_BG,
                       troughcolor=SIDEBAR_SEC,
                       sliderthickness=12, sliderlength=14)

        self._build_ui()
        # Redirige go_print() des modules librairie vers la console Tkinter
        set_log_sink(lambda level, msg: self._log(msg, level=level))
        self._log("Bienvenue dans Plugin1 Hugo  —  plugin STARHE.")
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
        tk.Label(header, text="Plugin1 Hugo  —  STARHE",
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
        self._btn_play.pack(fill="x", padx=10, pady=(2, 2))

        # Boucle
        tk.Checkbutton(sc, text="Boucle",
                       variable=self._loop_var,
                       bg=SIDEBAR_BG, fg=SBAR_FG, selectcolor=SIDEBAR_SEC,
                       activebackground=SIDEBAR_BG, activeforeground=SBAR_FG,
                       cursor="hand2", font=FONT_SMALL
                       ).pack(anchor="w", padx=16, pady=(2, 0))

        # Vitesse de lecture (multiplicateur ×)
        fps_row = tk.Frame(sc, bg=SIDEBAR_BG)
        fps_row.pack(fill="x", padx=10, pady=(2, 0))
        tk.Label(fps_row, text="Vitesse :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL).pack(side="left")
        self._speed_label = tk.Label(fps_row, text="×1.00", bg=SIDEBAR_BG,
                                     fg=SBAR_FG, font=FONT_SMALL)
        self._speed_label.pack(side="right", padx=(0, 4))
        self._speed_var = tk.DoubleVar(value=1.0)
        self._speed_scale = tk.Scale(
            sc, variable=self._speed_var, orient="horizontal",
            from_=0.25, to=3.0, resolution=0.25,
            showvalue=False, bg=SIDEBAR_BG, fg=SBAR_MUTED,
            troughcolor=SIDEBAR_SEC, highlightthickness=0,
            activebackground=BLUE, bd=0,
            command=self._on_speed_change,
        )
        self._speed_scale.pack(fill="x", padx=10, pady=(0, 4))

        # Reset
        self._sbtn(sc, "⏮   Revenir au début", self._reset_video) \
            .pack(fill="x", padx=10, pady=(0, 6))

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

        # ─── ANALYSE IA ──────────────────────────────────────────────────────
        _sh("Analyse IA")
        self._btn_pipeline = self._pbtn(sc, "🧠   Lancer l'analyse STARHE",
                                        self._on_run_pipeline)
        self._btn_pipeline.pack(fill="x", padx=10, pady=(8, 6))

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

        # ─── MÉTADONNÉES CONSERVÉES ──────────────────────────────────────────
        _sh("Métadonnées conservées")
        self._kept_meta_widget = tk.Text(
            sc, height=8,
            bg="#111827", fg="#6ee7b7",
            font=FONT_MONO, state="disabled", relief="flat",
            wrap="none", bd=0,
            selectbackground=SIDEBAR_HOV,
        )
        self._kept_meta_widget.pack(fill="x", padx=10, pady=(2, 4))

        # ─── TAGS ANONYMISÉS (valeurs originales) ──────────────────────────────
        _sh("Tags anonymisés")
        self._anon_tags_widget = tk.Text(
            sc, height=10,
            bg="#1a0a0a", fg=DANGER_FG,
            font=FONT_MONO, state="disabled", relief="flat",
            wrap="none", bd=0,
            selectbackground=SIDEBAR_HOV,
        )
        self._anon_tags_widget.pack(fill="x", padx=10, pady=(2, 10))

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
        # Clic droit → menu contextuel
        self._canvas.bind("<Button-3>",        self._show_context_menu)
        # Interactions pan / zoom / mesure / series (actives selon self._view_mode)
        self._canvas.bind("<ButtonPress-1>",   self._on_canvas_press)
        self._canvas.bind("<B1-Motion>",       self._on_canvas_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self._canvas.bind("<MouseWheel>",      self._on_canvas_scroll)
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
        # ×1+ : saute N frames par tick → vitesse indépendante du temps de rendu
        # ×<1 : avance 1 frame par tick, allonge l'intervalle
        skip = max(1, round(self._speed_mult)) if self._speed_mult >= 1.0 else 1

        next_idx = self._frame_idx + skip
        if next_idx >= n:
            if not self._loop_var.get():
                self._playing = False
                self._btn_play.config(text="▶   Play")
                return
            next_idx = next_idx % n
        self._frame_idx = next_idx
        self._update_frame_label()
        t0 = time.perf_counter()
        self._refresh_canvas()
        render_ms = (time.perf_counter() - t0) * 1000
        # Intervalle de base (fps natif du DICOM, non multiplié)
        base_ms = 1000.0 / max(1.0, self._base_fps)
        # En dessous de ×1 : ralentit en allongeant l'intervalle
        interval_ms = base_ms if self._speed_mult >= 1.0 else base_ms / self._speed_mult
        delay = max(1, int(interval_ms - render_ms))
        self._play_after_id = self.after(delay, self._play_step)

    def _on_load_dicom(self):
        path = filedialog.askopenfilename(
            title="Sélectionner un fichier DICOM",
            initialdir=DATA_DIR,
            filetypes=[("Fichiers DICOM", "*.dcm *"), ("Tous fichiers", "*.*")]
        )
        if not path:
            return
        self._log(f"Chargement : {os.path.basename(path)}")
        try:
            ds = load_dicom(path)

            # ── Capture les valeurs originales AVANT anonymisation ─────────────────────
            _SENS_LABEL = {
                (0x0010, 0x0010): "PatientName",
                (0x0010, 0x0020): "PatientID",
                (0x0010, 0x0030): "PatientBirthDate",
                (0x0010, 0x0040): "PatientSex",
                (0x0010, 0x1010): "PatientAge",
                (0x0008, 0x0020): "StudyDate",
                (0x0008, 0x0030): "StudyTime",
                (0x0008, 0x0090): "ReferringPhysician",
                (0x0008, 0x1030): "StudyDescription",
                (0x0008, 0x103E): "SeriesDescription",
                (0x0020, 0x000D): "StudyInstanceUID",
                (0x0020, 0x000E): "SeriesInstanceUID",
                (0x0008, 0x0018): "SOPInstanceUID",
                (0x0032, 0x1032): "RequestingPhysician",
                (0x0040, 0xA124): "UID",
            }
            original_sensitive = []
            for tag in DICOM_SENSITIVE_TAGS:
                name = _SENS_LABEL.get(tag, str(tag))
                val  = str(ds[tag].value).strip() if tag in ds else "— absent"
                original_sensitive.append((name, val))

            ds = anonymize(ds)  # suppression automatique des métadonnées sensibles
            frames = extract_frames(ds)

            # Normalise → (T, H, W, 3) uint8
            if frames.ndim == 3:
                frames = np.stack([frame_to_uint8(f) for f in frames])
                frames = np.stack([frames] * 3, axis=-1)
            else:
                frames = np.stack([frame_to_uint8(f) for f in frames])

            # Supprime le bandeau brûlé contenant les infos patient (PHI pixel)
            frames = remove_pixel_burnin(frames)

            self._frames_raw       = frames
            self._frames_cropped   = None
            self._frames_backscan  = None
            self._frames_crop_only = None
            self._roi              = None
            self._frame_idx             = 0
            self._detections_per_frame  = []
            self._crop_toggle.set(False)
            self._prepus_bsc.set(True)   # réinitialise backscan=on à chaque nouveau fichier

            # Extrait le pixel spacing pour la mesure en mm
            # Priorité : PixelSpacing → ImagerPixelSpacing → US Regions (PhysicalDeltaX/Y en cm)
            self._pixel_spacing = None
            try:
                ps = ds.PixelSpacing
                self._pixel_spacing = (float(ps[0]), float(ps[1]))
            except AttributeError:
                pass
            if self._pixel_spacing is None:
                try:
                    ps = ds.ImagerPixelSpacing
                    self._pixel_spacing = (float(ps[0]), float(ps[1]))
                except AttributeError:
                    pass
            if self._pixel_spacing is None:
                try:  # Échographie : SequenceOfUltrasoundRegions
                    region = ds.SequenceOfUltrasoundRegions[0]
                    # PhysicalDeltaX/Y sont en cm/pixel → ×10 pour mm/pixel
                    row_mm = abs(float(region.PhysicalDeltaY)) * 10.0
                    col_mm = abs(float(region.PhysicalDeltaX)) * 10.0
                    if row_mm > 0 and col_mm > 0:
                        self._pixel_spacing = (row_mm, col_mm)
                except (AttributeError, IndexError, TypeError):
                    pass

            # Affiche métadonnées non-sensibles
            mod   = str(getattr(ds, "Modality",  "N/A"))
            rows  = int(getattr(ds, "Rows",       0))
            cols  = int(getattr(ds, "Columns",    0))
            ps_str = f"{self._pixel_spacing[0]:.3f} mm/px" if self._pixel_spacing else "N/A"
            self._info_var.set(
                f"Modalité : {mod}\nTaille   : {rows}×{cols}\nFrames   : {len(frames)}\nPixel    : {ps_str}"
            )
            self._label_file.config(text=os.path.basename(path), fg=SBAR_FG)

            # ── Métadonnées conservées (non-sensibles) ───────────────────────────
            _KEPT_ATTRS = [
                ("Modality",                  "Modalité"),
                ("Manufacturer",              "Fabricant"),
                ("ManufacturerModelName",     "Modèle"),
                ("InstitutionName",           "Institution"),
                ("BodyPartExamined",          "Zone exam."),
                ("Rows",                      "Lignes"),
                ("Columns",                   "Colonnes"),
                ("NumberOfFrames",            "Nb frames"),
                ("FrameTime",                 "Tps/frame ms"),
                ("PhotometricInterpretation", "Photométrie"),
                ("BitsAllocated",             "Bits alloués"),
                ("SamplesPerPixel",           "Canaux"),
                ("TransducerType",            "Transducteur"),
            ]
            kept_meta = []
            for attr, label in _KEPT_ATTRS:
                val = getattr(ds, attr, None)
                if val is not None:
                    kept_meta.append((label, str(val).strip()))

            self._original_sensitive = original_sensitive
            self._kept_metadata      = kept_meta
            self._update_meta_widgets()

            # Calibre la vitesse de lecture sur le FPS natif du DICOM
            frame_time_ms = getattr(ds, "FrameTime", None)
            if frame_time_ms:
                try:
                    self._base_fps = 1000.0 / float(frame_time_ms)
                except (ValueError, ZeroDivisionError):
                    self._base_fps = 22.0
            else:
                self._base_fps = 22.0
            self._speed_var.set(1.0)
            self._speed_mult = 1.0
            self._play_fps   = self._base_fps
            self._speed_label.config(text="×1.00")

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
    def _on_run_pipeline(self):
        """Lance l'analyse IA dans un thread pour ne pas bloquer l'UI."""
        if self._frames_raw is None:
            messagebox.showwarning("Aucun DICOM", "Chargez d'abord un fichier DICOM.")
            return
        # Empêche un double lancement
        btn = getattr(self, "_btn_pipeline", None)
        if btn:
            btn.config(state="disabled")
        self._log("Lancement de l'analyse STARHE (thread IA)…")
        t = threading.Thread(target=self._run_ia_thread, daemon=True)
        t.start()

    def _run_ia_thread(self):
        """Exécutée dans un thread secondaire — détection sur chaque frame."""
        def _re_enable():
            btn = getattr(self, "_btn_pipeline", None)
            if btn:
                btn.config(state="normal")

        try:
            frames = (self._frames_cropped
                      if self._frames_cropped is not None
                      else self._frames_raw)
            n = len(frames)

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

            # STARHE-DETECT — une inférence par frame
            self._log(f"  → STARHE-DETECT : analyse de {n} frame(s)…")
            from starhe_plugin.ai.starhe_detect import STARHEDetectModel
            model = STARHEDetectModel()
            per_frame: list[list[dict]] = []

            for i, frm in enumerate(frames):
                dets = model.predict(frm)
                per_frame.append(dets)

                # Mise à jour progressive toutes les 5 frames
                if i % 5 == 0 or i == n - 1:
                    captured = list(per_frame)   # copie locale pour la closure
                    n_det = sum(1 for d in captured if d)
                    self._detections_per_frame = captured
                    self.after(0, lambda j=i + 1, nd=n_det:
                               self._det_lbl.config(
                                   text=f"Analyse… {j}/{n}  ({nd} frames)",
                                   fg=SBAR_MUTED))
                    self.after(0, self._refresh_canvas)

            # Résultat final
            self._detections_per_frame = per_frame
            n_frames_with_det = sum(1 for d in per_frame if d)
            det_fg = WARN_FG if n_frames_with_det > 0 else SUCCESS_FG
            self.after(0, lambda nf=n_frames_with_det, c=det_fg:
                       self._det_lbl.config(
                           text=f"{nf}/{n} frames avec lésion(s)", fg=c))
            self._log(
                f"  → DETECT terminé : {n_frames_with_det}/{n} frames avec lésion(s).",
                level="success"
            )

            if n_frames_with_det > 0 and self._frames_cropped is not None:
                self.after(0, lambda: self._crop_toggle.set(True))

            self.after(0, self._refresh_canvas)

        except Exception as exc:
            self._log(f"ERREUR IA : {exc}", level="error")
        finally:
            self.after(0, _re_enable)

    # ── Affichage canvas ──────────────────────────────────────────────────────

    def _refresh_canvas(self):
        if self._frames_raw is None:
            return

        use_cropped = (self._crop_toggle.get()
                       and self._frames_cropped is not None)
        frames = self._frames_cropped if use_cropped else self._frames_raw
        idx    = min(self._frame_idx, len(frames) - 1)
        frame  = frames[idx].copy()

        # Superpose les détections du frame courant
        if self._detections_per_frame and idx < len(self._detections_per_frame):
            frame_dets = self._detections_per_frame[idx]
            if frame_dets:
                frame = _draw_detections_on_array(frame, frame_dets)

        # Pad au format original
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

        # ── Conversion PIL + ajustements contraste / luminosité ────────────────
        from PIL import ImageEnhance
        if frame.ndim == 2:
            img = Image.fromarray(frame, mode="L").convert("RGB")
        else:
            img = Image.fromarray(frame.astype(np.uint8), mode="RGB")

        if self._contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(max(0.01, self._contrast))
        if self._brightness != 0.0:
            factor = 1.0 + self._brightness / 100.0
            img = ImageEnhance.Brightness(img).enhance(max(0.0, factor))

        # ── Zoom + pan ───────────────────────────────────────────────────────
        iw, ih    = img.size
        fit_scale = min(cw / iw, ch / ih) if iw > 0 and ih > 0 else 1.0
        scaled_w  = max(1, int(iw * fit_scale * self._zoom))
        scaled_h  = max(1, int(ih * fit_scale * self._zoom))
        img = img.resize((scaled_w, scaled_h), Image.LANCZOS)

        off_x = cw // 2 - scaled_w // 2 + int(self._pan_x)
        off_y = ch // 2 - scaled_h // 2 + int(self._pan_y)

        result = Image.new("RGB", (cw, ch), (0, 0, 0))
        src_x0 = max(0, -off_x);  src_y0 = max(0, -off_y)
        src_x1 = min(scaled_w, cw - off_x)
        src_y1 = min(scaled_h, ch - off_y)
        if src_x1 > src_x0 and src_y1 > src_y0:
            result.paste(img.crop((src_x0, src_y0, src_x1, src_y1)),
                         (max(0, off_x), max(0, off_y)))

        photo = ImageTk.PhotoImage(result)
        self._photo_ref = photo

        # ── Badge mode d'affichage ──────────────────────────────────────────
        if use_cropped and self._frames_backscan is not None and self._prepus_bsc.get():
            mode_txt = "BACKSCAN 512×512"
        elif use_cropped:
            mode_txt = "CROP + MASQUE"
        else:
            mode_txt = "ORIGINAL"
        if hasattr(self, "_mode_badge"):
            self._mode_badge.config(text=mode_txt)

        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=photo)

        # Redessine l'overlay de mesure par-dessus l'image
        if self._view_mode == "measure" and len(self._measure_pts) == 2:
            self._measure_items.clear()
            self._draw_measure_overlay(self._measure_pts[0], self._measure_pts[1])

    # ── Vitesse FPS ───────────────────────────────────────────────────────────

    def _on_speed_change(self, _=None):
        """Appelé à chaque déplacement du slider de vitesse."""
        self._speed_mult = self._speed_var.get()
        self._play_fps   = max(1.0, self._base_fps * self._speed_mult)
        self._speed_label.config(text=f"×{self._speed_mult:.2f}")
        if self._playing and self._play_after_id is not None:
            self.after_cancel(self._play_after_id)
            self._play_after_id = None
            self._play_step()

    # ── Reset vidéo ───────────────────────────────────────────────────────────

    def _reset_video(self):
        if self._frames_raw is None:
            return
        if self._playing:
            self._toggle_play()
        self._frame_idx = 0
        self._update_frame_label()
        self._refresh_canvas()

    # ── Réinitialisation complète de la vue ───────────────────────────────────

    def _reset_view(self):
        self._zoom       = 1.0
        self._pan_x      = 0.0
        self._pan_y      = 0.0
        self._contrast   = 1.0
        self._brightness = 0.0
        self._clear_measure()
        self._view_mode = "normal"
        self._canvas.config(cursor="")
        self._refresh_canvas()

    # ── Interactions canvas ───────────────────────────────────────────────────

    def _on_canvas_press(self, event):
        if self._view_mode == "pan":
            self._drag_start = (event.x, event.y, self._pan_x, self._pan_y)
        elif self._view_mode == "measure":
            self._clear_measure()
            self._measure_pts = [(event.x, event.y)]

    def _on_canvas_drag(self, event):
        if self._view_mode == "pan" and self._drag_start:
            dx = event.x - self._drag_start[0]
            dy = event.y - self._drag_start[1]
            self._pan_x = self._drag_start[2] + dx
            self._pan_y = self._drag_start[3] + dy
            self._refresh_canvas()
        elif self._view_mode == "measure" and self._measure_pts:
            # Redessine la ligne en temps réel sans rafraîchir tout le canvas
            self._draw_measure_overlay(self._measure_pts[0], (event.x, event.y))

    def _on_canvas_release(self, event):
        if self._view_mode == "pan":
            self._drag_start = None
        elif self._view_mode == "measure" and self._measure_pts:
            p2 = (event.x, event.y)
            self._measure_pts = [self._measure_pts[0], p2]
            self._draw_measure_overlay(self._measure_pts[0], p2)

    def _on_canvas_scroll(self, event):
        if self._view_mode == "pan":
            # Molette = zoom centré sur la position du curseur
            factor = 1.15 if event.delta > 0 else 1 / 1.15
            self._zoom = max(0.1, min(10.0, self._zoom * factor))
            self._refresh_canvas()
        elif self._view_mode == "series":
            if self._frames_raw is None:
                return
            delta = -1 if event.delta > 0 else 1
            n = len(self._frames_raw)
            self._frame_idx = max(0, min(n - 1, self._frame_idx + delta))
            self._update_frame_label()
            self._refresh_canvas()

    # ── Overlay de mesure ─────────────────────────────────────────────────────

    def _draw_measure_overlay(self, p1: tuple, p2: tuple):
        """Dessine la règle de mesure sur le canvas (coordonnées écran).

        La distance est affichée en mm si le PixelSpacing DICOM est disponible,
        sinon en pixels. La conversion tient compte du zoom et du fit_scale
        courants pour passer des coordonnées écran aux coordonnées image réelles.
        """
        import math
        # Supprime l'overlay précédent
        for item in self._measure_items:
            self._canvas.delete(item)
        self._measure_items.clear()

        x1, y1 = p1;  x2, y2 = p2
        # Distance en pixels-écran
        dist_screen = math.hypot(x2 - x1, y2 - y1)
        r    = 3
        mx, my = (x1 + x2) // 2, (y1 + y2) // 2

        # ── Calcul distance réelle ──────────────────────────────────────────
        # Le canvas affiche l'image avec fit_scale × zoom pixels-écran par pixel-image.
        # On récupère les dimensions de l'image source pour calculer fit_scale.
        frames = (self._frames_cropped
                  if (self._crop_toggle.get() and self._frames_cropped is not None)
                  else self._frames_raw)
        if frames is not None:
            cw = self._canvas.winfo_width()  or CANVAS_W
            ch = self._canvas.winfo_height() or CANVAS_H
            ih, iw = frames[0].shape[:2]
            fit_scale = min(cw / iw, ch / ih) if iw > 0 and ih > 0 else 1.0
            screen_per_img_px = fit_scale * self._zoom
        else:
            screen_per_img_px = 1.0

        dist_img_px = dist_screen / screen_per_img_px if screen_per_img_px > 0 else dist_screen

        if self._pixel_spacing is not None:
            dx_screen = abs(x2 - x1)
            dy_screen = abs(y2 - y1)
            dx_img = dx_screen / screen_per_img_px
            dy_img = dy_screen / screen_per_img_px
            dist_mm = math.hypot(dx_img * self._pixel_spacing[1],
                                  dy_img * self._pixel_spacing[0])
            dist_label = f"{dist_mm:.1f} mm"
        else:
            dist_label = f"{dist_img_px:.1f} px (pas de calibration)"

        line  = self._canvas.create_line(x1, y1, x2, y2,
                                          fill="#ffff00", width=2, dash=(5, 3))
        dot1  = self._canvas.create_oval(x1-r, y1-r, x1+r, y1+r,
                                          fill="#ffff00", outline="")
        dot2  = self._canvas.create_oval(x2-r, y2-r, x2+r, y2+r,
                                          fill="#ffff00", outline="")
        shadow = self._canvas.create_text(mx+1, my+1,
                                           text=dist_label,
                                           fill="#000000", font=FONT_SMALL)
        label  = self._canvas.create_text(mx, my,
                                           text=dist_label,
                                           fill="#ffff00", font=FONT_SMALL)
        self._measure_items = [line, dot1, dot2, shadow, label]

    def _clear_measure(self):
        for item in self._measure_items:
            self._canvas.delete(item)
        self._measure_items.clear()
        self._measure_pts.clear()

    # ── Menu contextuel clic droit ────────────────────────────────────────────

    def _show_context_menu(self, event):
        def _check(mode: str) -> str:
            return "✓  " if self._view_mode == mode else "    "

        menu = tk.Menu(self, tearoff=0,
                       bg=SIDEBAR_BG, fg=SBAR_FG,
                       activebackground=BLUE, activeforeground="#ffffff",
                       font=FONT_BODY, bd=0, relief="flat")

        menu.add_command(label=f"{_check('pan')}Déplacer / Zoomer",
                         command=self._toggle_pan_zoom)
        menu.add_command(label=f"{_check('measure')}Mesurer",
                         command=self._toggle_measure)
        menu.add_separator()
        menu.add_command(label="    Contraste…",
                         command=self._open_contrast_dialog)
        menu.add_command(label="    Luminosité…",
                         command=self._open_brightness_dialog)
        menu.add_separator()
        menu.add_command(label=f"{_check('series')}Series Scroll",
                         command=self._toggle_series_scroll)
        menu.add_separator()
        menu.add_command(label="    Réinitialiser la vue",
                         command=self._reset_view)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ── Modes interactifs ─────────────────────────────────────────────────────

    def _toggle_pan_zoom(self):
        if self._view_mode == "pan":
            self._view_mode = "normal"
            self._canvas.config(cursor="")
        else:
            self._view_mode = "pan"
            self._canvas.config(cursor="fleur")
            self._clear_measure()

    def _toggle_measure(self):
        if self._view_mode == "measure":
            self._view_mode = "normal"
            self._canvas.config(cursor="")
            self._clear_measure()
        else:
            self._view_mode = "measure"
            self._canvas.config(cursor="crosshair")

    def _toggle_series_scroll(self):
        if self._view_mode == "series":
            self._view_mode = "normal"
            self._canvas.config(cursor="")
        else:
            self._view_mode = "series"
            self._canvas.config(cursor="sb_v_double_arrow")

    # ── Dialogues contraste / luminosité ─────────────────────────────────────

    def _open_contrast_dialog(self):
        if hasattr(self, "_contrast_win") and self._contrast_win.winfo_exists():
            self._contrast_win.lift()
            return
        self._contrast_win = _AdjustDialog(
            self, "Contraste", self._contrast,
            0.1, 3.0, 1.0,
            lambda v: self._set_contrast(v))

    def _open_brightness_dialog(self):
        if hasattr(self, "_brightness_win") and self._brightness_win.winfo_exists():
            self._brightness_win.lift()
            return
        self._brightness_win = _AdjustDialog(
            self, "Luminosité", self._brightness,
            -100.0, 100.0, 0.0,
            lambda v: self._set_brightness(v))

    def _set_contrast(self, value: float):
        self._contrast = value
        self._refresh_canvas()

    def _set_brightness(self, value: float):
        self._brightness = value
        self._refresh_canvas()

    # ── Navigation frames ─────────────────────────────────────────────────────

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

    # ── Mise à jour sections métadonnées ─────────────────────────────────────

    def _update_meta_widgets(self):
        """Remplit les deux widgets texte (conservées / anonymisées) après chargement."""
        # ── Métadonnées conservées (vert menthe) ──────────────────────────────
        self._kept_meta_widget.config(state="normal")
        self._kept_meta_widget.delete("1.0", "end")
        for label, val in self._kept_metadata:
            val_s = val if len(val) <= 24 else val[:21] + "…"
            self._kept_meta_widget.insert("end", f"  {label:<14} {val_s}\n")
        if not self._kept_metadata:
            self._kept_meta_widget.insert("end", "  (aucune métadonnée trouvée)")
        self._kept_meta_widget.config(state="disabled")

        # ── Tags anonymisés (rouge — valeurs originales) ──────────────────────
        self._anon_tags_widget.config(state="normal")
        self._anon_tags_widget.delete("1.0", "end")
        for name, val in self._original_sensitive:
            val_s = val if len(val) <= 22 else val[:19] + "…"
            self._anon_tags_widget.insert("end", f"  ✗ {name:<20} {val_s}\n")
        self._anon_tags_widget.config(state="disabled")

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
