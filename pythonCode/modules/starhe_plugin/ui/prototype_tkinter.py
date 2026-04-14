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
import math
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
FONT_MEASURE = ("Segoe UI", 11, "bold")
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


def _map_bbox_backscan_to_original(bbox: list, prepus_info: dict) -> list:
    """
    Convertit une bounding box de l'espace backscan (512×512) vers
    l'espace de l'image DICOM originale en inversant la transformation
    polaire de prepUS, puis en ajoutant l'offset de crop.

    bbox        : [x0, y0, x1, y1] en pixels backscan (x=col, y=row)
    prepus_info : dict issu de info.json (clés "crop" et "backscan")
    Retourne      [x0, y0, x1, y1] en pixels de l'image originale.
    """
    bsc  = prepus_info["backscan"]
    crop = prepus_info["crop"]

    rc      = bsc["rc"]
    dc      = bsc["dc"]
    theta_c = bsc["theta_c"]
    xoff    = bsc["xoffset"]   # valeurs telles que stockées par prepUS
    yoff    = bsc["yoffset"]
    bsc_h   = bsc["height"]
    bsc_w   = bsc["width"]

    delta_r     = dc / bsc_h
    delta_theta = theta_c / bsc_w

    x0, y0, x1, y1 = bbox          # backscan : x=col (bj), y=row (bi)

    # Échantillonner des points le long des 4 bords (transformation non-linéaire)
    N = 12
    bj_vals = np.linspace(x0, x1, N)
    bi_vals = np.linspace(y0, y1, N)

    sample_points = (
        [(bj, y0) for bj in bj_vals] +  # bord haut
        [(bj, y1) for bj in bj_vals] +  # bord bas
        [(x0, bi) for bi in bi_vals] +  # bord gauche
        [(x1, bi) for bi in bi_vals]    # bord droit
    )

    orig_cols: list[float] = []
    orig_rows: list[float] = []
    for bj, bi in sample_points:
        r     = rc + bi * delta_r
        angle = -theta_c / 2 + bj * delta_theta
        # coord_transform avec le swap xoffset/yoffset du CLI prepUS
        crop_row = r * math.cos(angle) - yoff
        crop_col = r * math.sin(angle) + xoff
        orig_rows.append(crop_row + crop["ymin"])
        orig_cols.append(crop_col + crop["xmin"])

    # Clipper aux limites de la zone de crop (cône échographique)
    ox0 = max(min(orig_cols), crop["xmin"])
    oy0 = max(min(orig_rows), crop["ymin"])
    ox1 = min(max(orig_cols), crop["xmax"])
    oy1 = min(max(orig_rows), crop["ymax"])
    if ox1 <= ox0 or oy1 <= oy0:
        return bbox  # bbox entièrement hors crop → retourner tel quel
    return [ox0, oy0, ox1, oy1]


def _map_all_detections_to_original(
    per_frame: list[list[dict]],
    prepus_info: dict,
) -> list[list[dict]]:
    """Remappe toutes les détections (toutes frames) du backscan vers l'image originale."""
    mapped: list[list[dict]] = []
    for frame_dets in per_frame:
        mapped_dets: list[dict] = []
        for det in frame_dets:
            new_det = dict(det)
            new_det["bbox"] = _map_bbox_backscan_to_original(det["bbox"], prepus_info)
            mapped_dets.append(new_det)
        mapped.append(mapped_dets)
    return mapped


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
#  Bouton cliquable cross-platform (macOS ignore bg/fg sur tk.Button)
# ─────────────────────────────────────────────────────────────────────────────

class _ClickableFrame(tk.Frame):
    """tk.Frame qui proxy .config(text=…) et .config(state=…) vers son label."""

    def __init__(self, parent, lbl: tk.Label, rest_bg: str, rest_fg: str,
                 command=None, **kw):
        super().__init__(parent, **kw)
        self._lbl = lbl
        self._rest_bg = rest_bg
        self._rest_fg = rest_fg
        self._command = command

    # --- proxy config / configure ---
    def config(self, **kw):
        return self.configure(**kw)

    def configure(self, **kw):
        text  = kw.pop("text",  None)
        state = kw.pop("state", None)
        fg    = kw.pop("fg",    None)
        if text is not None:
            self._lbl.configure(text=text)
        if fg is not None:
            self._rest_fg = fg
            self._lbl.configure(fg=fg)
        if state == "disabled":
            self._lbl.configure(fg="#555555")
            for w in (self, self._lbl):
                w.configure(cursor="")
                w.unbind("<Button-1>")
        elif state == "normal":
            self._lbl.configure(fg=self._rest_fg)
            cmd = self._command
            for w in (self, self._lbl):
                w.configure(cursor="hand2")
                w.bind("<Button-1>", lambda e, c=cmd: c())
        if kw:
            super().configure(**kw)


def _make_btn(parent, text, command, bg="#000000", fg="#ffffff",
              font=None, padx=10, pady=6, anchor="w", width=None):
    """Label cliquable avec hover — fonctionne sur macOS contrairement à tk.Button."""
    frm = _ClickableFrame(parent, lbl=None, rest_bg=bg, rest_fg=fg,
                           command=command, bg=bg, cursor="hand2")
    kw = dict(text=text, bg=bg, fg=fg, font=font or FONT_BTN,
              padx=padx, pady=pady, anchor=anchor, cursor="hand2")
    if width is not None:
        kw["width"] = width
    lbl = tk.Label(frm, **kw)
    frm._lbl = lbl
    lbl.pack(fill="both", expand=True)
    hover_bg = "#222222"
    for w in (frm, lbl):
        w.bind("<Button-1>", lambda e, c=command: c())
        w.bind("<Enter>", lambda e, l=lbl, f=frm: (l.configure(bg=hover_bg), f.configure(bg=hover_bg)))
        w.bind("<Leave>", lambda e, l=lbl, f=frm, b=bg: (l.configure(bg=b), f.configure(bg=b)))
    return frm


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
        rst = _make_btn(self, "Réinitialiser",
                        lambda n=_neutral: (self._var.set(n), _on_change(n)),
                        bg="#000000", fg="#ffffff", font=FONT_SMALL, pady=4)
        rst.pack(pady=(0, 12), padx=20, fill="x")


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
        self._prepus_info     : dict | None       = None  # info.json de prepUS (crop + backscan)
        self._roi             : tuple | None      = None
        self._frame_idx            : int               = 0
        self._detections_by_mode   : dict[str, list[list[dict]]] = {}   # mode→per-frame dets
        self._results_by_mode      : dict[str, dict]              = {}   # mode→{risk_text,risk_fg,det_text,det_fg}
        self._show_cropped         : bool              = False
        self._original_sensitive   : list              = []   # valeurs avant anonymisation
        self._kept_metadata        : list              = []   # métadonnées conservées
        self._dicom_path           : str | None        = None  # chemin .dcm chargé
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
        self._drag_start    : tuple | None    = None         # (ex, ey, val_a, val_b)
        self._press_time    : float           = 0.0          # horodatage du ButtonPress-1
        self._press_pos     : tuple           = (0, 0)       # position du ButtonPress-1
        # Mesures multiples (par frame)
        self._measures_by_frame     : dict[int, list] = {}   # frame_idx -> [{pts:[(x1,y1),(x2,y2)], items:[...]}]
        self._measure_drawing       : list            = []   # [(x,y)] ou [] — segment en cours
        self._measure_selected      : int | None      = None # index segment sélectionné
        self._measure_edit          : dict | None     = None # édition drag
        self._measure_preview_items : list            = []   # canvas items temporaires (preview)
        # Système d'onglets multi-fichiers
        self._tabs          : list[dict]      = []           # un dict d'état par onglet
        self._active_tab    : int             = -1           # index de l'onglet actif (-1 = aucun)
        self._patients      : list[dict]      = []           # [{"name": str, "tabs": [idx_in_self._tabs, …]}, …]
        self._active_patient: int             = -1           # index du patient actif (-1 = aucun)
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
        self._setup_kb_shortcuts()
        # Redirige go_print() des modules librairie vers la console Tkinter
        set_log_sink(lambda level, msg: self._log(msg, level=level))
        self._log("Bienvenue dans Plugin1 Hugo  —  plugin STARHE.")
        self._log("Chargez un fichier DICOM (.dcm) dans le panneau latéral pour commencer.")

    # ── Raccourcis clavier globaux ────────────────────────────────────────────

    def _setup_kb_shortcuts(self):
        """Enregistre les raccourcis clavier sur la fenêtre principale.

        Les raccourcis sont inactifs si le focus est dans un champ de saisie
        (Entry / Text) pour éviter toute interférence lors de la frappe.

        Tableau des raccourcis
        ──────────────────────
        Espace          Play / Pause
        ←  →            Frame précédente / suivante
        Shift+← / →     Saut de −10 / +10 frames
        Home / End      Premier / Dernier frame
        P               Toggle mode Pan/Zoom
        M               Toggle mode Mesure
        S               Toggle mode Défilement série
        Échap           Retour mode normal (+ déselect mesure)
        R               Réinitialiser la vue
        C               Dialog Contraste
        L               Dialog Luminosité
        + ou =          Vitesse lecture ×1.25
        -               Vitesse lecture ×0.80
        B               Toggle boucle
        Cmd/Ctrl + =    Zoom avant
        Cmd/Ctrl + -    Zoom arrière
        Cmd/Ctrl + 0    Réinitialiser zoom
        """
        kb = [
            ("<space>",         lambda e: self._kb_do(self._toggle_play)),
            ("<Left>",          lambda e: self._kb_do(self._prev_frame)),
            ("<Right>",         lambda e: self._kb_do(self._next_frame)),
            ("<Shift-Left>",    lambda e: self._kb_do(lambda: self._kb_jump(-10))),
            ("<Shift-Right>",   lambda e: self._kb_do(lambda: self._kb_jump(+10))),
            ("<Home>",          lambda e: self._kb_do(self._kb_first_frame)),
            ("<End>",           lambda e: self._kb_do(self._kb_last_frame)),
            ("<Control-Tab>",   lambda e: self._kb_do(self._kb_next_tab)),
            ("<Control-Shift-Tab>", lambda e: self._kb_do(self._kb_prev_tab)),
            ("<Control-w>",     lambda e: self._kb_do(lambda: self._close_tab(self._active_tab))),
            ("p",               lambda e: self._kb_do(self._toggle_pan_zoom)),
            ("m",               lambda e: self._kb_do(self._toggle_measure)),
            ("s",               lambda e: self._kb_do(self._toggle_series_scroll)),
            ("<Escape>",        lambda e: self._kb_do(self._kb_escape)),
            ("r",               lambda e: self._kb_do(self._reset_view)),
            ("c",               lambda e: self._kb_do(self._open_contrast_dialog)),
            ("l",               lambda e: self._kb_do(self._open_brightness_dialog)),
            ("<plus>",          lambda e: self._kb_do(lambda: self._kb_speed(1.25))),
            ("<equal>",         lambda e: self._kb_do(lambda: self._kb_speed(1.25))),
            ("<minus>",         lambda e: self._kb_do(lambda: self._kb_speed(0.80))),
            ("b",               lambda e: self._kb_do(self._kb_toggle_loop)),
            # Zoom via Cmd+=/- (macOS) et Ctrl+=/- (Win/Linux)
            ("<Command-equal>",  lambda e: self._kb_do(self._zoom_in)),
            ("<Command-minus>",  lambda e: self._kb_do(self._zoom_out)),
            ("<Command-0>",      lambda e: self._kb_do(self._zoom_reset)),
            ("<Control-equal>",  lambda e: self._kb_do(self._zoom_in)),
            ("<Control-minus>",  lambda e: self._kb_do(self._zoom_out)),
            ("<Control-0>",      lambda e: self._kb_do(self._zoom_reset)),
        ]
        for seq, handler in kb:
            self.bind(seq, handler)

    def _kb_guard(self) -> bool:
        """Renvoie True si le focus est dans un champ de texte éditable."""
        w = self.focus_get()
        if not isinstance(w, (tk.Entry, tk.Text, scrolledtext.ScrolledText)):
            return False
        # Ne pas bloquer les raccourcis si le widget texte est désactivé
        try:
            return str(w.cget("state")) == "normal"
        except Exception:
            return False

    def _kb_do(self, fn):
        """Exécute *fn* sauf si un widget de texte a le focus."""
        if not self._kb_guard():
            fn()

    # ── Helpers raccourcis ────────────────────────────────────────────────────

    def _kb_jump(self, delta: int):
        """Saute *delta* frames (négatif = reculer)."""
        if self._frames_raw is None:
            return
        if self._playing:
            self._toggle_play()
        n = len(self._frames_raw)
        self._frame_idx = max(0, min(n - 1, self._frame_idx + delta))
        self._update_frame_label()
        self._refresh_canvas()

    def _kb_first_frame(self):
        if self._frames_raw is None:
            return
        if self._playing:
            self._toggle_play()
        self._frame_idx = 0
        self._update_frame_label()
        self._refresh_canvas()

    def _kb_last_frame(self):
        if self._frames_raw is None:
            return
        if self._playing:
            self._toggle_play()
        self._frame_idx = len(self._frames_raw) - 1
        self._update_frame_label()
        self._refresh_canvas()

    def _kb_escape(self):
        """Échap : déselectionne la mesure courante s'il y en a une, sinon repasse en mode normal."""
        if self._view_mode == "measure" and self._measure_selected is not None:
            self._measure_selected = None
            self._redraw_measures()
        else:
            self._reset_view()

    def _kb_speed(self, factor: float):
        """Multiplie la vitesse de lecture par *factor*, clampée entre 0.25× et 3.0×."""
        new_val = max(0.25, min(3.0, self._speed_mult * factor))
        self._speed_var.set(new_val)
        self._on_speed_change()

    def _kb_toggle_loop(self):
        self._loop_var.set(not self._loop_var.get())

    # ── Zoom ──────────────────────────────────────────────────────────────────

    def _zoom_in(self):
        self._zoom = min(10.0, self._zoom * 1.25)
        self._refresh_canvas()

    def _zoom_out(self):
        self._zoom = max(0.1, self._zoom / 1.25)
        self._refresh_canvas()

    def _zoom_reset(self):
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._refresh_canvas()

    def _on_canvas_scroll(self, event):
        """Zoom centré sur le curseur souris à la molette.

        Fonctionne dans tous les modes.
        - Windows / macOS : <MouseWheel>, event.delta = ±120 (Win) ou ±1..5 (macOS)
        - Linux           : <Button-4> (scroll up) / <Button-5> (scroll down)

        La formule de recentrage garantit que le point image sous le curseur
        reste immobile après le changement de zoom :
          new_pan = pan * f + (1 - f) * (mouse_canvas - canvas_center / 2)
        où f = new_zoom / old_zoom.
        """
        if self._frames_raw is None:
            return "break"

        # Normalisation du delta selon la plateforme
        if event.num == 4:
            delta = 1
        elif event.num == 5:
            delta = -1
        else:
            delta = event.delta

        factor = 1.1 if delta > 0 else (1.0 / 1.1)
        new_zoom = max(0.1, min(10.0, self._zoom * factor))
        actual_factor = new_zoom / self._zoom

        cw = self._canvas.winfo_width()  or CANVAS_W
        ch = self._canvas.winfo_height() or CANVAS_H
        mx, my = event.x, event.y

        # Recentrage : le point image sous le curseur ne bouge pas
        self._pan_x = self._pan_x * actual_factor + (1.0 - actual_factor) * (mx - cw / 2.0)
        self._pan_y = self._pan_y * actual_factor + (1.0 - actual_factor) * (my - ch / 2.0)
        self._zoom  = new_zoom
        self._refresh_canvas()
        return "break"   # empêche la propagation vers le défilement de la sidebar

    # ── Conversion coordonnées écran ↔ image ─────────────────────────────────

    def _img_transform(self) -> tuple:
        """Renvoie (scale, off_x, off_y) pour convertir image → écran.

        screen_x = img_x * scale + off_x
        screen_y = img_y * scale + off_y
        """
        frames = (self._frames_cropped
                  if (self._crop_toggle.get() and self._frames_cropped is not None)
                  else self._frames_raw)
        if frames is None:
            return (1.0, 0.0, 0.0)
        cw = self._canvas.winfo_width()  or CANVAS_W
        ch = self._canvas.winfo_height() or CANVAS_H
        ih, iw = frames[0].shape[:2]
        fit_scale = min(cw / iw, ch / ih) if iw > 0 and ih > 0 else 1.0
        scale = fit_scale * self._zoom
        scaled_w = int(iw * scale)
        scaled_h = int(ih * scale)
        off_x = cw / 2 - scaled_w / 2 + self._pan_x
        off_y = ch / 2 - scaled_h / 2 + self._pan_y
        return (scale, off_x, off_y)

    def _screen_to_img(self, sx: float, sy: float) -> tuple:
        """Convertit coordonnées écran (canvas) → coordonnées image."""
        scale, off_x, off_y = self._img_transform()
        if scale == 0:
            return (sx, sy)
        return ((sx - off_x) / scale, (sy - off_y) / scale)

    def _img_to_screen(self, ix: float, iy: float) -> tuple:
        """Convertit coordonnées image → coordonnées écran (canvas)."""
        scale, off_x, off_y = self._img_transform()
        return (ix * scale + off_x, iy * scale + off_y)

    def _kb_next_tab(self):
        if self._patients and self._active_patient >= 0:
            patient = self._patients[self._active_patient]
            tabs = patient["tabs"]
            if not tabs:
                return
            try:
                pos = tabs.index(self._active_tab)
            except ValueError:
                pos = -1
            next_pos = (pos + 1) % len(tabs)
            self._switch_tab(tabs[next_pos])

    def _kb_prev_tab(self):
        if self._patients and self._active_patient >= 0:
            patient = self._patients[self._active_patient]
            tabs = patient["tabs"]
            if not tabs:
                return
            try:
                pos = tabs.index(self._active_tab)
            except ValueError:
                pos = 0
            prev_pos = (pos - 1) % len(tabs)
            self._switch_tab(tabs[prev_pos])

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self):        # ── Barre de titre MEDomics ─────────────────────────────────────────────
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
        self._sb_theme_btn = _make_btn(
            sb_footer, "🌙   Thème sombre", self._toggle_theme,
            bg="#000000", fg="#ffffff", font=FONT_SMALL, padx=14
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
            # macOS : delta = ±1..±5 ; Windows : delta = ±120
            d = event.delta if abs(event.delta) < 50 else event.delta // 120
            c.yview_scroll(int(-d), "units")

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

        # Variables internes (pré-traitement automatique, pas d'UI)
        self._prepus_bsc = tk.BooleanVar(value=True)
        self._crop_toggle = tk.BooleanVar(value=False)

        # ─── ANALYSE IA ──────────────────────────────────────────────────────
        _sh("Analyse IA")
        self._btn_pipeline = self._pbtn(sc, "🧠   Lancer l'analyse STARHE",
                                        self._on_run_pipeline)
        self._btn_pipeline.pack(fill="x", padx=10, pady=(8, 4))

        btn_reset = _make_btn(sc, "🗑   Réinitialiser l'analyse",
                                    self._on_reset_analysis,
                                    bg="#000000", fg="#ffffff",
                                    font=FONT_SMALL)
        btn_reset.pack(fill="x", padx=10, pady=(0, 6))

        # ─── RÉSULTATS ───────────────────────────────────────────────────────
        _sh("Résultats")
        mode_row = tk.Frame(sc, bg=SIDEBAR_BG)
        mode_row.pack(fill="x", padx=14, pady=(6, 1))
        tk.Label(mode_row, text="Mode :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL, anchor="w").pack(side="left")
        self._mode_lbl = tk.Label(mode_row, text="—", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                                   font=("Segoe UI", 9, "bold"), anchor="w")
        self._mode_lbl.pack(side="left", padx=(6, 0))

        risk_row = tk.Frame(sc, bg=SIDEBAR_BG)
        risk_row.pack(fill="x", padx=14, pady=(1, 1))
        tk.Label(risk_row, text="Risque CHC :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL, anchor="w").pack(side="left")
        self._risk_lbl = tk.Label(risk_row, text="—", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                                   font=("Segoe UI", 9, "bold"), anchor="w")
        self._risk_lbl.pack(side="left", padx=(6, 0))

        det_row = tk.Frame(sc, bg=SIDEBAR_BG)
        det_row.pack(fill="x", padx=14, pady=(1, 4))
        tk.Label(det_row, text="Lésions :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL, anchor="w").pack(side="left")
        self._det_lbl = tk.Label(det_row, text="—", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                                  font=("Segoe UI", 9, "bold"), anchor="w")
        self._det_lbl.pack(side="left", padx=(6, 0))

        # ─── FRAMES AVEC TUMEUR ──────────────────────────────────────────────
        tk.Label(sc, text="Frames avec tumeur :", bg=SIDEBAR_BG, fg=SBAR_MUTED,
                 font=FONT_SMALL, anchor="w").pack(fill="x", padx=14, pady=(4, 1))
        self._det_frames_widget = tk.Text(
            sc, height=4,
            bg="#1a0a0a", fg=WARN_FG,
            font=FONT_MONO, state="disabled", relief="flat",
            wrap="word", bd=0, cursor="arrow",
            selectbackground=SIDEBAR_HOV,
        )
        self._det_frames_widget.pack(fill="x", padx=10, pady=(0, 12))
        self._det_frames_widget.tag_configure("link", foreground="#60a5fa",
                                              underline=True)

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

        # Boutons zoom (compacts, dans l'en-tête de la carte)
        zoom_frame = tk.Frame(self._card_hdr, bg=CARD_BG)
        zoom_frame.pack(side="right", padx=(0, 8))
        _zoom_btn_kw = dict(bg=CARD_BG, fg=BLUE_TEXT,
                            font=("Segoe UI", 11, "bold"),
                            bd=0, padx=4, pady=0, cursor="hand2")
        self._btn_zoom_out = tk.Label(zoom_frame, text=" − ", **_zoom_btn_kw)
        self._btn_zoom_out.pack(side="left")
        self._btn_zoom_out.bind("<Button-1>", lambda e: self._zoom_out())
        self._zoom_pct_lbl = tk.Label(zoom_frame, text="100 %", bg=CARD_BG,
                                       fg=SBAR_MUTED, font=("Segoe UI", 8),
                                       width=6, anchor="center")
        self._zoom_pct_lbl.pack(side="left", padx=2)
        self._btn_zoom_in = tk.Label(zoom_frame, text=" + ", **_zoom_btn_kw)
        self._btn_zoom_in.pack(side="left")
        self._btn_zoom_in.bind("<Button-1>", lambda e: self._zoom_in())

        self._card_divider = tk.Frame(card, bg=BORDER, height=1)
        self._card_divider.pack(fill="x")

        # ── Barre d'onglets PATIENTS (en haut, juste sous le divider) ─────────
        _PTAB_BG = "#10141e"
        self._patient_bar_outer = tk.Frame(card, bg=_PTAB_BG, height=30)
        self._patient_bar_outer.pack(fill="x")
        self._patient_bar_outer.pack_propagate(False)
        self._patient_bar_scroll = tk.Canvas(self._patient_bar_outer, bg=_PTAB_BG,
                                              highlightthickness=0, height=30)
        self._patient_bar_scroll.pack(side="left", fill="both", expand=True)
        self._patient_bar_inner = tk.Frame(self._patient_bar_scroll, bg=_PTAB_BG)
        self._patient_bar_scroll.create_window((0, 0), window=self._patient_bar_inner, anchor="nw")
        self._patient_bar_inner.bind("<Configure>", lambda e: self._patient_bar_scroll.config(
            scrollregion=self._patient_bar_scroll.bbox("all")))
        self._patient_bar_scroll.bind("<MouseWheel>",
            lambda e: self._patient_bar_scroll.xview_scroll(
                int(-1 * (e.delta if abs(e.delta) < 50 else e.delta // 120)), "units"))

        # ── Barre d'onglets (bas de la carte, avant canvas pour side="bottom") ────
        _TAB_BG = "#0c1018"
        self._tab_bar_outer = tk.Frame(card, bg=_TAB_BG, height=32)
        self._tab_bar_outer.pack(side="bottom", fill="x")
        self._tab_bar_outer.pack_propagate(False)
        # Zone défilante pour les onglets
        self._tab_bar_scroll = tk.Canvas(self._tab_bar_outer, bg=_TAB_BG,
                                          highlightthickness=0, height=32)
        self._tab_bar_scroll.pack(side="left", fill="both", expand=True)
        # Bouton "+" pour ajouter d'autres fichiers
        _plus_btn = _make_btn(self._tab_bar_outer, "  +  ",
                                    self._on_load_dicom,
                                    bg="#000000", fg="#ffffff",
                                    font=("Segoe UI", 12, "bold"),
                                    padx=4, anchor="center")
        _plus_btn.pack(side="right", padx=2)
        self._tab_bar_inner = tk.Frame(self._tab_bar_scroll, bg=_TAB_BG)
        self._tab_bar_scroll.create_window((0, 0), window=self._tab_bar_inner, anchor="nw")
        self._tab_bar_inner.bind("<Configure>", lambda e: self._tab_bar_scroll.config(
            scrollregion=self._tab_bar_scroll.bbox("all")))
        self._tab_bar_scroll.bind("<MouseWheel>",
            lambda e: self._tab_bar_scroll.xview_scroll(
                int(-1 * (e.delta if abs(e.delta) < 50 else e.delta // 120)), "units"))

        # Canvas DICOM (fond sombre à l'intérieur de la carte)
        canvas_wrap = tk.Frame(card, bg=CANVAS_BG)
        canvas_wrap.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(canvas_wrap, bg=CANVAS_BG,
                                 highlightthickness=0,
                                 width=CANVAS_W, height=CANVAS_H)
        self._canvas.pack(fill="both", expand=True)
        # Interactions pan / zoom / mesure / series (actives selon self._view_mode)
        self._canvas.bind("<ButtonPress-1>",   self._on_canvas_press)
        self._canvas.bind("<B1-Motion>",       self._on_canvas_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        # Clic droit maintenu → contraste (X) / luminosité (Y)
        self._canvas.bind("<ButtonPress-3>",   self._on_rclick_press)
        self._canvas.bind("<B3-Motion>",       self._on_rclick_drag)
        self._canvas.bind("<ButtonRelease-3>", self._on_rclick_release)
        # Suppression de mesure sélectionnée (le canvas doit avoir le focus)
        self._canvas.bind("<Delete>",          self._on_measure_delete)
        self._canvas.bind("<BackSpace>",       self._on_measure_delete)
        # Zoom molette (Windows/macOS: <MouseWheel> ; Linux: <Button-4>/<Button-5>)
        self._canvas.bind("<MouseWheel>",      self._on_canvas_scroll)
        self._canvas.bind("<Button-4>",        self._on_canvas_scroll)
        self._canvas.bind("<Button-5>",        self._on_canvas_scroll)
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

    def _sbtn(self, parent, text: str, command) -> tk.Frame:
        """Bouton secondaire sidebar (fond noir, texte blanc)."""
        return _make_btn(parent, text, command,
                         bg="#000000", fg="#ffffff", font=FONT_BTN)

    def _sibtn(self, parent, text: str, command) -> tk.Frame:
        """Petit bouton icône carré pour la navigation."""
        return _make_btn(parent, text, command,
                         bg="#000000", fg="#ffffff",
                         font=("Segoe UI", 10, "bold"),
                         width=4, pady=4, anchor="center")

    def _pbtn(self, parent, text: str, command) -> tk.Frame:
        """Bouton primaire (fond noir, texte blanc)."""
        return _make_btn(parent, text, command,
                         bg="#000000", fg="#ffffff",
                         font=FONT_BTN_P, pady=8)

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

    # ── Mode d'affichage courant (pour associer les détections au bon mode) ───

    def _current_display_mode(self) -> str:
        """Retourne le mode d'affichage actif : 'backscan' ou 'original'."""
        if self._crop_toggle.get() and self._frames_cropped is not None:
            return "backscan"
        return "original"

    def _active_detections(self) -> list[list[dict]]:
        """Retourne les détections correspondant au mode d'affichage courant."""
        return self._detections_by_mode.get(self._current_display_mode(), [])

    _MODE_LABELS = {"backscan": "Analyse STARHE", "original": "Original"}

    def _refresh_results_panel(self):
        """Met à jour la section Résultats selon le mode d'affichage courant."""
        mode = self._current_display_mode()
        res = self._results_by_mode.get(mode)
        if res:
            self._mode_lbl.config(text=self._MODE_LABELS.get(mode, mode), fg="#93c5fd")
            self._risk_lbl.config(text=res["risk_text"], fg=res["risk_fg"])
            self._det_lbl .config(text=res["det_text"],  fg=res["det_fg"])
        else:
            self._mode_lbl.config(text=self._MODE_LABELS.get(mode, mode), fg=SBAR_MUTED)
            self._risk_lbl.config(text="—", fg=SBAR_MUTED)
            self._det_lbl .config(text="—", fg=SBAR_MUTED)
        # Met à jour la liste des frames avec tumeur
        _dets = self._active_detections()
        det_idxs = [i for i, d in enumerate(_dets) if d]
        self._populate_det_frames(det_idxs)

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
        """Ouvre un ou plusieurs fichiers DICOM et crée un onglet pour chacun."""
        import platform
        kwargs = dict(
            title="Sélectionner un ou plusieurs fichiers DICOM",
            initialdir=DATA_DIR,
        )
        # "Tous fichiers" en premier = sélection par défaut sur toutes les plateformes.
        # Les fichiers DICOM n'ont pas toujours l'extension .dcm (ex: A0000, IM-0001…).
        # Sur macOS, NSOpenPanel masque les fichiers sans extension si un filtre UTI
        # est actif — on garde donc "Tous fichiers" comme première option partout.
        if platform.system() == "Darwin":
            # Pas de filetypes : NSOpenPanel affiche tout sans filtrer par UTI
            pass
        else:
            kwargs["filetypes"] = [
                ("Tous fichiers", "*"),
                ("Fichiers DICOM", "*.dcm"),
            ]
        paths = filedialog.askopenfilenames(**kwargs)
        if not paths:
            return
        self._save_tab_state()
        first_new = len(self._tabs)
        for path in paths:
            self._load_one_dicom(path)
        target = first_new if first_new < len(self._tabs) else max(0, len(self._tabs) - 1)
        self._switch_tab(target)

    def _load_one_dicom(self, path: str):
        """Charge un fichier DICOM individuel et crée son onglet."""
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
            self._prepus_info      = None
            self._roi              = None
            self._frame_idx             = 0
            self._detections_by_mode    = {}
            self._results_by_mode       = {}
            self._dicom_path            = path
            self._crop_toggle.set(False)
            # Vide le widget frames avec tumeur
            self._det_frames_widget.config(state="normal")
            self._det_frames_widget.delete("1.0", "end")
            self._det_frames_widget.config(state="disabled")
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

            # ── Création de l'onglet ────────────────────────────────────────────
            _study_date = next(
                (v for n, v in original_sensitive if n == "StudyDate" and v != "— absent"),
                ""
            )
            _patient_name = next(
                (v for n, v in original_sensitive if n == "PatientName" and v != "— absent"),
                "Patient inconnu"
            )
            # Normalise le nom : remplace ^ par espace, titre
            _patient_name = _patient_name.replace("^", " ").strip() or "Patient inconnu"

            tab_state = self._capture_tab_state(
                self._make_tab_label(_study_date, path),
                patient_name=_patient_name,
            )
            self._tabs.append(tab_state)
            new_tab_idx = len(self._tabs) - 1

            # ── Groupement par patient ──────────────────────────────────────────
            patient_idx = None
            for pi, p in enumerate(self._patients):
                if p["name"] == _patient_name:
                    patient_idx = pi
                    break
            if patient_idx is None:
                # Nouveau patient
                self._patients.append({"name": _patient_name, "tabs": [new_tab_idx]})
                patient_idx = len(self._patients) - 1
            else:
                self._patients[patient_idx]["tabs"].append(new_tab_idx)

            self._active_patient = patient_idx
            self._active_tab = new_tab_idx

        except Exception as exc:
            messagebox.showerror("Erreur de chargement", str(exc))
            self._log(f"ERREUR : {exc}", level="error")

    # ── Gestion des onglets multi-fichiers ───────────────────────────────────

    @staticmethod
    def _make_tab_label(study_date: str, path: str) -> str:
        """Génère le label d'onglet depuis la date DICOM ou le nom de fichier."""
        sd = study_date.strip()
        if len(sd) == 8 and sd.isdigit():
            return f"{sd[6:8]}/{sd[4:6]}/{sd[0:4]}"
        if sd and sd not in ("", "— absent"):
            return sd[:14]
        base = os.path.splitext(os.path.basename(path))[0]
        return base[:14] if len(base) > 14 else base

    def _capture_tab_state(self, label: str, patient_name: str = "") -> dict:
        """Prend un instantané de l'état courant pour le stocker dans un onglet."""
        return {
            "label":                label,
            "patient_name":         patient_name,
            "frames_raw":           self._frames_raw,
            "frames_cropped":       self._frames_cropped,
            "frames_backscan":      self._frames_backscan,
            "frames_crop_only":     self._frames_crop_only,
            "prepus_info":          self._prepus_info,
            "roi":                  self._roi,
            "frame_idx":            self._frame_idx,
            "detections_by_mode":   {k: list(v) for k, v in self._detections_by_mode.items()},
            "results_by_mode":     dict(self._results_by_mode),
            "dicom_path":           self._dicom_path,
            "pixel_spacing":        self._pixel_spacing,
            "base_fps":             self._base_fps,
            "original_sensitive":   list(self._original_sensitive),
            "kept_metadata":        list(self._kept_metadata),
            "measures_by_frame":    {f: [{"pts": list(s["pts"])} for s in segs] for f, segs in self._measures_by_frame.items()},
            "measure_selected":     self._measure_selected,
            "zoom":                 self._zoom,
            "pan_x":               self._pan_x,
            "pan_y":               self._pan_y,
            "contrast":             self._contrast,
            "brightness":           self._brightness,
            "view_mode":            self._view_mode,
            "crop_toggle_val":      self._crop_toggle.get(),
            "prepus_bsc_val":       self._prepus_bsc.get(),
            "speed_mult":           self._speed_mult,
            "info_val":             self._info_var.get(),
            "label_file_text":      self._label_file.cget("text"),
            "label_file_fg":        self._label_file.cget("fg"),
        }

    def _save_tab_state(self):
        """Met à jour le dict de l'onglet actif avec l'état courant."""
        if self._active_tab < 0 or self._active_tab >= len(self._tabs):
            return
        s = self._tabs[self._active_tab]
        s["frames_raw"]            = self._frames_raw
        s["frames_cropped"]        = self._frames_cropped
        s["frames_backscan"]       = self._frames_backscan
        s["frames_crop_only"]      = self._frames_crop_only
        s["prepus_info"]           = self._prepus_info
        s["roi"]                   = self._roi
        s["frame_idx"]             = self._frame_idx
        s["detections_by_mode"]    = {k: list(v) for k, v in self._detections_by_mode.items()}
        s["results_by_mode"]       = dict(self._results_by_mode)
        s["dicom_path"]            = self._dicom_path
        s["pixel_spacing"]         = self._pixel_spacing
        s["base_fps"]              = self._base_fps
        s["original_sensitive"]    = list(self._original_sensitive)
        s["kept_metadata"]         = list(self._kept_metadata)
        s["measures_by_frame"]     = {f: [{"pts": list(seg["pts"])} for seg in segs] for f, segs in self._measures_by_frame.items()}
        s["measure_selected"]      = self._measure_selected
        s["zoom"]                  = self._zoom
        s["pan_x"]                 = self._pan_x
        s["pan_y"]                 = self._pan_y
        s["contrast"]              = self._contrast
        s["brightness"]            = self._brightness
        s["view_mode"]             = self._view_mode
        s["crop_toggle_val"]       = self._crop_toggle.get()
        s["prepus_bsc_val"]        = self._prepus_bsc.get()
        s["speed_mult"]            = self._speed_mult
        s["info_val"]              = self._info_var.get()
        s["label_file_text"]       = self._label_file.cget("text")
        s["label_file_fg"]         = self._label_file.cget("fg")

    def _restore_tab_state(self, idx: int):
        """Restaure l'état d'un onglet dans les variables d'instance et l'UI."""
        s = self._tabs[idx]
        self._frames_raw            = s.get("frames_raw")
        self._frames_cropped        = s.get("frames_cropped")
        self._frames_backscan       = s.get("frames_backscan")
        self._frames_crop_only      = s.get("frames_crop_only")
        self._prepus_info           = s.get("prepus_info")
        self._roi                   = s.get("roi")
        self._frame_idx             = s.get("frame_idx", 0)
        self._detections_by_mode    = {k: list(v) for k, v in s.get("detections_by_mode", {}).items()}
        self._results_by_mode       = dict(s.get("results_by_mode", {}))
        self._dicom_path            = s.get("dicom_path")
        self._pixel_spacing         = s.get("pixel_spacing")
        self._base_fps              = s.get("base_fps", 22.0)
        self._original_sensitive    = list(s.get("original_sensitive", []))
        self._kept_metadata         = list(s.get("kept_metadata", []))
        # Mesures : items canvas seront recréés par _redraw_measures / _refresh_canvas
        self._measures_by_frame     = {f: [{"pts": list(seg["pts"]), "items": []}
                                           for seg in segs]
                                       for f, segs in s.get("measures_by_frame", {}).items()}
        self._measure_drawing       = []
        self._measure_preview_items = []
        self._measure_selected      = s.get("measure_selected")
        self._measure_edit          = None
        self._zoom       = s.get("zoom",       1.0)
        self._pan_x      = s.get("pan_x",      0.0)
        self._pan_y      = s.get("pan_y",      0.0)
        self._contrast   = s.get("contrast",   1.0)
        self._brightness = s.get("brightness", 0.0)
        self._view_mode  = s.get("view_mode",  "normal")
        vm_cursor = {"pan": "fleur", "measure": "crosshair",
                     "series": "sb_v_double_arrow"}.get(self._view_mode, "")
        self._canvas.config(cursor=vm_cursor)
        self._crop_toggle.set(s.get("crop_toggle_val", False))
        self._prepus_bsc.set(s.get("prepus_bsc_val", True))
        speed = s.get("speed_mult", 1.0)
        self._speed_mult = speed
        self._speed_var.set(speed)
        self._play_fps   = self._base_fps * speed
        self._speed_label.config(text=f"×{speed:.2f}")
        if self._frames_raw is not None:
            n = len(self._frames_raw)
            self._frame_scale.configure(to=max(1, n - 1))
            self._frame_scale.set(self._frame_idx)
            self._frame_label.config(text=f"{self._frame_idx + 1} / {n}")
        else:
            self._frame_scale.configure(to=1)
            self._frame_scale.set(0)
            self._frame_label.config(text="— / —")
        self._refresh_results_panel()
        self._info_var.set(s.get("info_val", ""))
        self._label_file.config(
            text=s.get("label_file_text", "Aucun fichier sélectionné"),
            fg=s.get("label_file_fg", SBAR_MUTED))
        _active_dets = self._active_detections()
        det_idxs = [i for i, d in enumerate(_active_dets) if d]
        self._populate_det_frames(det_idxs)
        self._update_meta_widgets()

    def _switch_tab(self, idx: int):
        """Bascule vers l'onglet global *idx* : sauvegarde l'état courant puis restaure."""
        if not (0 <= idx < len(self._tabs)):
            self._rebuild_patient_bar()
            self._rebuild_tab_bar()
            return
        if idx == self._active_tab:
            self._rebuild_patient_bar()
            self._rebuild_tab_bar()
            return
        if self._playing:
            self._toggle_play()
        # Supprime les items canvas de mesure (seront recréés sur le nouvel onglet)
        for segs in self._measures_by_frame.values():
            for seg in segs:
                for item in seg["items"]:
                    self._canvas.delete(item)
        for item in self._measure_preview_items:
            self._canvas.delete(item)
        self._save_tab_state()
        self._active_tab = idx
        # Met à jour le patient actif si nécessaire
        for pi, p in enumerate(self._patients):
            if idx in p["tabs"]:
                self._active_patient = pi
                break
        self._restore_tab_state(idx)
        self._rebuild_patient_bar()
        self._rebuild_tab_bar()
        self._refresh_canvas()

    def _switch_patient(self, patient_idx: int):
        """Bascule vers un patient : active le premier onglet de ce patient."""
        if not (0 <= patient_idx < len(self._patients)):
            return
        if patient_idx == self._active_patient:
            return
        patient = self._patients[patient_idx]
        if not patient["tabs"]:
            return
        # Bascule vers le premier fichier de ce patient
        first_tab = patient["tabs"][0]
        self._switch_tab(first_tab)

    def _close_tab(self, idx: int):
        """Ferme l'onglet global *idx* et met à jour la structure patients."""
        if not self._tabs:
            return
        if len(self._tabs) == 1:
            # Dernier onglet : réinitialise tout
            self._tabs.clear()
            self._patients.clear()
            self._active_tab = -1
            self._active_patient = -1
            self._frames_raw = self._frames_cropped = None
            self._frames_backscan = self._frames_crop_only = None
            self._prepus_info = None
            self._detections_by_mode = {}
            self._results_by_mode = {}
            self._dicom_path = None
            self._pixel_spacing = None
            self._clear_measure()
            self._zoom = 1.0; self._pan_x = 0.0; self._pan_y = 0.0
            self._contrast = 1.0; self._brightness = 0.0
            self._view_mode = "normal"; self._canvas.config(cursor="")
            self._info_var.set("")
            self._label_file.config(text="Aucun fichier sélectionné", fg=SBAR_MUTED)
            self._risk_lbl.config(text="—", fg=SBAR_MUTED)
            self._det_lbl .config(text="—", fg=SBAR_MUTED)
            self._mode_lbl.config(text="—", fg=SBAR_MUTED)
            self._populate_det_frames([])
            self._update_meta_widgets()
            self._rebuild_patient_bar()
            self._rebuild_tab_bar()
            self._canvas.delete("all")
            self._canvas.create_text(
                CANVAS_W // 2, CANVAS_H // 2,
                text="Aucun DICOM chargé\n\nUtilisez  « Charger un fichier DICOM »  dans le panneau latéral",
                fill="#2a2a3e", font=("Segoe UI", 12), justify="center")
            return

        was_active = (idx == self._active_tab)

        # Retire l'index de la liste des patients et renumérise
        self._tabs.pop(idx)
        for p in self._patients:
            p["tabs"] = [t - 1 if t > idx else t
                         for t in p["tabs"] if t != idx]
        # Supprime les patients sans onglets
        self._patients = [p for p in self._patients if p["tabs"]]

        if was_active:
            # Trouver un onglet de remplacement dans le même patient
            old_patient_name = None
            for p in self._patients:
                if any(t == max(0, idx - 1) for t in p["tabs"]) or p["tabs"]:
                    old_patient_name = p["name"]
                    break
            new_idx = max(0, idx - 1) if idx > 0 else 0
            new_idx = min(new_idx, len(self._tabs) - 1)
            self._active_tab = new_idx
            # Mettre à jour le patient actif
            for pi, p in enumerate(self._patients):
                if new_idx in p["tabs"]:
                    self._active_patient = pi
                    break
            self._restore_tab_state(new_idx)
            self._rebuild_patient_bar()
            self._rebuild_tab_bar()
            self._refresh_canvas()
        else:
            if self._active_tab > idx:
                self._active_tab -= 1
            # Mettre à jour le patient actif
            for pi, p in enumerate(self._patients):
                if self._active_tab in p["tabs"]:
                    self._active_patient = pi
                    break
            self._rebuild_patient_bar()
            self._rebuild_tab_bar()

    def _rebuild_tab_bar(self):
        """Redessine la barre d'onglets des fichiers (dates) du patient actif."""
        for w in self._tab_bar_inner.winfo_children():
            w.destroy()
        _TAB_BG     = "#0c1018"
        _TAB_ACT_BG = "#131c2e"
        if self._active_patient < 0 or self._active_patient >= len(self._patients):
            self._tab_bar_inner.update_idletasks()
            self._tab_bar_scroll.config(scrollregion=self._tab_bar_scroll.bbox("all"))
            return
        patient = self._patients[self._active_patient]
        for tab_global_idx in patient["tabs"]:
            if tab_global_idx >= len(self._tabs):
                continue
            tab = self._tabs[tab_global_idx]
            is_active = (tab_global_idx == self._active_tab)
            bg  = _TAB_ACT_BG if is_active else _TAB_BG
            fg  = "#e5e7eb"   if is_active else "#6b7280"
            frm = tk.Frame(self._tab_bar_inner, bg=bg, cursor="hand2")
            frm.pack(side="left", padx=(0, 1), fill="y")
            # Barre bleue en haut de l'onglet actif
            tk.Frame(frm, bg=BLUE if is_active else _TAB_BG, height=2).pack(fill="x")
            inner = tk.Frame(frm, bg=bg)
            inner.pack(fill="both", expand=True)
            lbl = tk.Label(inner, text=tab["label"],
                           bg=bg, fg=fg, font=("Segoe UI", 8),
                           padx=8, pady=3, cursor="hand2")
            lbl.pack(side="left")
            close_lbl = tk.Label(
                inner, text="×",
                bg="#000000", fg="#ffffff", cursor="hand2",
                font=("Segoe UI", 9), padx=3, pady=1)
            close_lbl.pack(side="left", pady=2)
            _gi = tab_global_idx
            close_lbl.bind("<Button-1>", lambda e, ci=_gi: self._close_tab(ci))
            close_lbl.bind("<Enter>", lambda e, l=close_lbl: l.configure(fg="#ff4444"))
            close_lbl.bind("<Leave>", lambda e, l=close_lbl: l.configure(fg="#ffffff"))
            for w in (frm, inner, lbl):
                w.bind("<Button-1>", lambda e, ci=_gi: self._switch_tab(ci))
        self._tab_bar_inner.update_idletasks()
        self._tab_bar_scroll.config(scrollregion=self._tab_bar_scroll.bbox("all"))

    def _rebuild_patient_bar(self):
        """Redessine la barre d'onglets patients (en haut du viewer)."""
        for w in self._patient_bar_inner.winfo_children():
            w.destroy()
        _PTAB_BG     = "#10141e"
        _PTAB_ACT_BG = "#1a2238"
        for pi, patient in enumerate(self._patients):
            is_active = (pi == self._active_patient)
            bg  = _PTAB_ACT_BG if is_active else _PTAB_BG
            fg  = "#e5e7eb"    if is_active else "#6b7280"
            frm = tk.Frame(self._patient_bar_inner, bg=bg, cursor="hand2")
            frm.pack(side="left", padx=(0, 1), fill="y")
            # Barre bleue en bas de l'onglet patient actif
            inner = tk.Frame(frm, bg=bg)
            inner.pack(fill="both", expand=True)
            lbl = tk.Label(inner, text=patient["name"],
                           bg=bg, fg=fg, font=("Segoe UI", 8, "bold"),
                           padx=10, pady=4, cursor="hand2")
            lbl.pack(side="left")
            tk.Frame(frm, bg=BLUE if is_active else _PTAB_BG, height=2).pack(fill="x", side="bottom")
            for w in (frm, inner, lbl):
                w.bind("<Button-1>", lambda e, idx=pi: self._switch_patient(idx))
        self._patient_bar_inner.update_idletasks()
        self._patient_bar_scroll.config(scrollregion=self._patient_bar_scroll.bbox("all"))

    def _run_prepus_internal(self):
        """Exécute le pré-traitement prepUS (backscan 512×512) sans interaction UI."""
        import numpy as _np
        self._log("  → Pré-traitement prepUS (backscan 512×512) en cours…")
        backscan_arr, crop_only_arr, info = preprocess_with_prepus(
            self._frames_raw,
            fps=22.0,
            thresh=-1.0,
            back_scan_conversion=True,
            backscan_width=512,
            backscan_height=512,
        )

        def _rgb(a):
            return _np.stack([a, a, a], axis=-1)

        self._frames_backscan  = _rgb(backscan_arr)
        self._frames_crop_only = _rgb(crop_only_arr) if crop_only_arr is not None \
                                 else self._frames_backscan
        self._frames_cropped = self._frames_backscan
        self._prepus_info = info
        self._roi = None

        shape_str = f"{backscan_arr.shape[2]}×{backscan_arr.shape[1]}"
        msg = f"  → Pré-traitement OK — {backscan_arr.shape[0]} frames, {shape_str} px"
        if info and "crop" in info:
            c = info["crop"]
            msg += f" | crop y=[{c['ymin']},{c['ymax']}] x=[{c['xmin']},{c['xmax']}]"
        self._log(msg, level="success")

    def _on_reset_analysis(self):
        """Supprime le cache MongoDB pour le fichier actuel et réinitialise l'affichage."""
        if not getattr(self, "_dicom_path", None):
            messagebox.showwarning("Aucun DICOM", "Chargez d'abord un fichier DICOM.")
            return
        if not messagebox.askyesno(
            "Réinitialiser l'analyse",
            f"Supprimer les résultats STARHE en cache pour :\n{self._dicom_path} ?"
        ):
            return
        from starhe_plugin.db.mongo_client import delete_result
        ok = delete_result(self._dicom_path)
        if ok:
            self._log("✓  Résultat MongoDB supprimé.")
        else:
            self._log("⚠  Aucun résultat en cache à supprimer.")
        # Réinitialise l'affichage
        self._crop_toggle.set(False)
        self._detections_by_mode = {}
        self._results_by_mode = {}
        self._risk_lbl.config(text="—", fg=SBAR_MUTED)
        self._det_lbl.config(text="—", fg=SBAR_MUTED)
        if hasattr(self, "_mode_lbl"):
            self._mode_lbl.config(text="—", fg=SBAR_MUTED)
        if hasattr(self, "_det_frames_widget"):
            self._det_frames_widget.config(state="normal")
            self._det_frames_widget.delete("1.0", "end")
            self._det_frames_widget.config(state="disabled")
        self._refresh_canvas()

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
        """Exécutée dans un thread secondaire — pré-traitement + détection."""
        def _re_enable():
            btn = getattr(self, "_btn_pipeline", None)
            if btn:
                btn.config(state="normal")

        try:
            _analysis_mode = "backscan"
            n = len(self._frames_raw)

            # ─── VÉRIFICATION CACHE MONGODB ────────────────────────────────────────
            if self._dicom_path:
                try:
                    from starhe_plugin.db.mongo_client import find_by_file, save_result
                    cached = find_by_file(self._dicom_path, analysis_mode=_analysis_mode)
                    if cached:
                        self._log(
                            f"  → Résultat en cache (MongoDB, mode=Backscan, {cached['processed_at'][:10]}).",
                            level="success"
                        )
                        per_frame    = cached.get("detections_per_frame", [[] for _ in range(n)])
                        risk_cached  = cached.get("risk", {})
                        score = risk_cached.get("score", 0.0)
                        label = risk_cached.get("label", "Inconnu")
                        risk_fg = RISK_HIGH_FG if any(
                            w in label.lower() for w in ("élevé", "high")
                        ) else RISK_LOW_FG
                        n_frames_with_det = sum(1 for d in per_frame if d)
                        det_fg = WARN_FG if n_frames_with_det > 0 else SUCCESS_FG
                        # Les détections en cache sont DÉJÀ en espace original
                        # (remappées lors de la première analyse avant sauvegarde)
                        self._detections_by_mode["original"] = per_frame
                        self._results_by_mode["original"] = {
                            "risk_text": f"{label}  ({score:.1%})",
                            "risk_fg":   risk_fg,
                            "det_text":  f"{n_frames_with_det}/{n} frames avec lésion(s)",
                            "det_fg":    det_fg,
                        }
                        self.after(0, self._refresh_results_panel)
                        self.after(0, self._refresh_canvas)
                        return
                except Exception as exc:
                    self._log(f"  MongoDB cache inaccessible : {exc} — analyse en cours…",
                              level="error")

            # ─── PRÉ-TRAITEMENT (prepUS backscan) ─────────────────────────────────
            self.after(0, lambda: self._det_lbl.config(
                text="Pré-traitement en cours…", fg=SBAR_MUTED))
            self._run_prepus_internal()
            frames = self._frames_cropped
            n = len(frames)

            # ─── STARHE-RISK ───────────────────────────────────────────────────
            self._log("  → STARHE-RISK (C3D) en cours…")
            from starhe_plugin.ai.starhe_risk import STARHERiskModel
            risk_result = STARHERiskModel().predict(frames)
            score = risk_result["risk_score"]
            label = risk_result["risk_label"]
            risk_fg = RISK_HIGH_FG if any(
                w in label.lower() for w in ("élevé", "high")
            ) else RISK_LOW_FG
            _risk_text = f"{label}  ({score:.1%})"
            self.after(0, lambda rt=_risk_text, c=risk_fg:
                       self._risk_lbl.config(text=rt, fg=c))
            self._log(f"  → RISK : {label} | score={score:.3f}", level="success")

            # STARHE-DETECT — inférence par lots (batch inference)
            from starhe_plugin.ai.starhe_detect import STARHEDetectModel
            from starhe_plugin.config import DETECT_EVERY_N, DETECT_BATCH_SIZE
            stride     = max(1, DETECT_EVERY_N)
            batch_size = max(1, DETECT_BATCH_SIZE)
            # Indices des frames à analyser (echantillonnage temporel)
            sampled = list(range(0, n, stride))
            n_sampled = len(sampled)
            self._log(f"  → STARHE-DETECT : {n_sampled}/{n} frames (stride={stride}, batch={batch_size})…")

            per_frame: list[list[dict]] = [[] for _ in range(n)]

            with STARHEDetectModel() as detect_model:
                for batch_start in range(0, n_sampled, batch_size):
                    batch_indices = sampled[batch_start: batch_start + batch_size]
                    batch_frames  = [frames[i] for i in batch_indices]

                    # Inférence sur tout le lot en une seule passe réseau
                    batch_dets = detect_model.predict_batch(batch_frames)

                    for i, dets in zip(batch_indices, batch_dets):
                        # Propagation aux frames intermédiaires
                        for j in range(i, min(i + stride, n)):
                            per_frame[j] = dets

                    # Mise à jour progressive de l'UI tous les batches
                    frames_done = min(batch_start + batch_size, n_sampled)
                    n_det = sum(1 for d in per_frame if d)
                    self.after(0, lambda fd=frames_done, nd=n_det:
                               self._det_lbl.config(
                                   text=f"Analyse… {fd}/{n_sampled} lots  ({nd} frames)",
                                   fg=SBAR_MUTED))

            # ── Remappage backscan → original ──────────────────────────────────
            if self._prepus_info and "backscan" in self._prepus_info:
                per_frame = _map_all_detections_to_original(per_frame, self._prepus_info)
                self._log("  → Détections remappées vers l'espace original.")

            # Résultat final — stocké sous le mode "original"
            self._detections_by_mode["original"] = per_frame
            n_frames_with_det = sum(1 for d in per_frame if d)
            det_fg = WARN_FG if n_frames_with_det > 0 else SUCCESS_FG
            _det_text = f"{n_frames_with_det}/{n} frames avec lésion(s)"
            self._results_by_mode["original"] = {
                "risk_text": _risk_text,
                "risk_fg":   risk_fg,
                "det_text":  _det_text,
                "det_fg":    det_fg,
            }
            self.after(0, self._refresh_results_panel)
            self._log(
                f"  → DETECT terminé : {n_frames_with_det}/{n} frames avec lésion(s).",
                level="success"
            )

            # Liste des numéros de frames (1-based) avec au moins une détection
            detected_indices = [i for i, d in enumerate(per_frame) if d]
            self.after(0, lambda idxs=detected_indices:
                       self._populate_det_frames(idxs))

            # Afficher l'image originale avec les bboxes remappées
            self.after(0, self._refresh_canvas)

            # ─── SAUVEGARDE MONGODB ────────────────────────────────────────────────
            if self._dicom_path:
                try:
                    from starhe_plugin.db.mongo_client import save_result
                    save_result(
                        file_path=self._dicom_path,
                        num_frames=n,
                        roi=list(self._roi) if self._roi else [],
                        risk={"score": float(score), "label": label},
                        detections_per_frame=per_frame,
                        analysis_mode=_analysis_mode,
                    )
                    self._log("  → Résultats sauvegardés dans MongoDB.", level="success")
                except Exception as exc:
                    self._log(f"  MongoDB : sauvegarde échouée ({exc})", level="error")

        except Exception as exc:
            self._log(f"ERREUR IA : {exc}", level="error")
        finally:
            self.after(0, _re_enable)

    # ── Résultats détection ───────────────────────────────────────────────────

    def _populate_det_frames(self, indices: list[int]):
        """Remplit le widget 'Frames avec tumeur' avec des numéros cliquables."""
        w = self._det_frames_widget
        w.config(state="normal")
        w.delete("1.0", "end")
        if not indices:
            w.insert("end", "Aucune tumeur détectée", "")
        else:
            for pos, idx in enumerate(indices):
                label = str(idx + 1)   # 1-based
                tag = f"fr_{idx}"
                w.insert("end", label, ("link", tag))
                if pos < len(indices) - 1:
                    w.insert("end", "  ")
                # Clic → navigation vers ce frame
                w.tag_bind(tag, "<Button-1>",
                           lambda e, i=idx: self._goto_frame(i))
                w.tag_bind(tag, "<Enter>",
                           lambda e: w.config(cursor="hand2"))
                w.tag_bind(tag, "<Leave>",
                           lambda e: w.config(cursor="arrow"))
        w.config(state="disabled")
        self._canvas.focus_set()

    def _goto_frame(self, idx: int):
        """Navigue vers le frame idx (0-based) et rafraîchit l'affichage."""
        frames = (self._frames_cropped
                  if self._crop_toggle.get() and self._frames_cropped is not None
                  else self._frames_raw)
        if frames is None:
            return
        self._frame_idx = max(0, min(len(frames) - 1, idx))
        self._refresh_canvas()
        self._canvas.focus_set()

    # ── Affichage canvas ──────────────────────────────────────────────────────

    def _refresh_canvas(self):
        if self._frames_raw is None:
            return

        use_cropped = (self._crop_toggle.get()
                       and self._frames_cropped is not None)
        frames = self._frames_cropped if use_cropped else self._frames_raw
        idx    = min(self._frame_idx, len(frames) - 1)
        frame  = frames[idx].copy()

        # Superpose les détections du frame courant (uniquement pour le mode analysé)
        _dets_for_mode = self._active_detections()
        if _dets_for_mode and idx < len(_dets_for_mode):
            frame_dets = _dets_for_mode[idx]
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
        has_dets = bool(self._detections_by_mode.get("original"))
        if has_dets:
            mode_txt = "ANALYSE STARHE"
        else:
            mode_txt = "ORIGINAL"
        if hasattr(self, "_mode_badge"):
            self._mode_badge.config(text=mode_txt)
        if hasattr(self, "_zoom_pct_lbl"):
            self._zoom_pct_lbl.config(text=f"{self._zoom * 100:.0f} %")

        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=photo)

        # Redessine les mesures par-dessus l'image (tout mode confondu)
        if self._measures_by_frame.get(self._frame_idx):
            self._redraw_measures()

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
            self._canvas.focus_set()
            hit = self._measure_hit(event.x, event.y)
            if hit is not None:
                seg_idx, part = hit
                self._measure_selected = seg_idx
                img_pt = self._screen_to_img(event.x, event.y)
                self._measure_edit = {
                    "seg_idx": seg_idx,
                    "part": part,
                    "start_img": img_pt,
                    "orig_pts": list(self._measures_by_frame.get(self._frame_idx, [])[seg_idx]["pts"]),
                }
                self._measure_drawing = []
                self._redraw_measures()
            else:
                self._measure_selected = None
                self._measure_edit = None
                self._measure_drawing = [self._screen_to_img(event.x, event.y)]
                self._redraw_measures()
        elif self._view_mode == "normal":
            self._drag_start = (event.x, event.y, self._frame_idx)

    def _on_canvas_drag(self, event):
        if self._view_mode == "pan" and self._drag_start:
            dx = event.x - self._drag_start[0]
            dy = event.y - self._drag_start[1]
            self._pan_x = self._drag_start[2] + dx
            self._pan_y = self._drag_start[3] + dy
            self._refresh_canvas()
        elif self._view_mode == "normal" and self._drag_start and self._frames_raw is not None:
            # Glisser vertical → défilement de frames
            dy = event.y - self._drag_start[1]
            # 1 frame tous les 8 pixels de déplacement
            step = int(dy / 8)
            n = len(self._frames_raw)
            new_idx = max(0, min(n - 1, self._drag_start[2] + step))
            if new_idx != self._frame_idx:
                self._frame_idx = new_idx
                self._update_frame_label()
                self._refresh_canvas()
        elif self._view_mode == "measure":
            if self._measure_edit is not None:
                ed = self._measure_edit
                seg = self._measures_by_frame.get(self._frame_idx, [])[ed["seg_idx"]]
                cur_img = self._screen_to_img(event.x, event.y)
                dix = cur_img[0] - ed["start_img"][0]
                diy = cur_img[1] - ed["start_img"][1]
                ox1, oy1 = ed["orig_pts"][0]
                ox2, oy2 = ed["orig_pts"][1]
                if ed["part"] == "p1":
                    seg["pts"] = [(ox1 + dix, oy1 + diy), (ox2, oy2)]
                elif ed["part"] == "p2":
                    seg["pts"] = [(ox1, oy1), (ox2 + dix, oy2 + diy)]
                else:  # "seg" — déplace tout le segment
                    seg["pts"] = [(ox1 + dix, oy1 + diy), (ox2 + dix, oy2 + diy)]
                self._redraw_measures()
            elif self._measure_drawing:
                self._redraw_measures(
                    preview=(self._measure_drawing[0],
                             self._screen_to_img(event.x, event.y))
                )

    def _on_canvas_release(self, event):
        if self._view_mode in ("pan", "normal"):
            self._drag_start = None
        elif self._view_mode == "measure":
            if self._measure_edit is not None:
                self._measure_edit = None
            elif self._measure_drawing:
                p1_img = self._measure_drawing[0]
                p2_img = self._screen_to_img(event.x, event.y)
                # Vérifie distance minimale en écran
                p1_scr = self._img_to_screen(*p1_img)
                p2_scr = (event.x, event.y)
                if math.hypot(p2_scr[0] - p1_scr[0], p2_scr[1] - p1_scr[1]) > 5:
                    self._measures_by_frame.setdefault(self._frame_idx, []).append({"pts": [p1_img, p2_img], "items": []})
                self._measure_drawing = []
                self._redraw_measures()

    # ── Clic droit maintenu : contraste (X) / luminosité (Y) ─────────────────

    def _on_rclick_press(self, event):
        self._press_time = time.time()
        self._press_pos  = (event.x, event.y)
        self._drag_start = (event.x, event.y, self._contrast, self._brightness)

    def _on_rclick_drag(self, event):
        if not self._drag_start:
            return
        dx = event.x - self._drag_start[0]   # droite → contraste +
        dy = event.y - self._drag_start[1]   # bas    → luminosité +
        self._contrast   = max(0.1, min(3.0,   self._drag_start[2] + dx * 0.008))
        self._brightness = max(-100, min(100,  self._drag_start[3] + dy * 0.5))
        self._refresh_canvas()

    def _on_rclick_release(self, event):
        self._drag_start = None
        # Clic bref sans déplacement → menu contextuel
        dt = time.time() - self._press_time
        dx = abs(event.x - self._press_pos[0])
        dy = abs(event.y - self._press_pos[1])
        if dt < 0.25 and dx < 5 and dy < 5:
            self._show_context_menu(event)

    # ── Overlay de mesure ─────────────────────────────────────────────────────

    def _draw_measure_overlay(self, p1: tuple, p2: tuple,
                               selected: bool = False,
                               target: list | None = None):
        """Dessine un segment de mesure sur le canvas (coordonnées image).

        *p1* et *p2* sont en coordonnées **image** (pixels de l'image d'origine).
        La méthode les convertit en coordonnées écran via _img_to_screen.

        La distance est affichée en mm si le PixelSpacing DICOM est disponible,
        sinon en pixels image.

        Les IDs canvas créés sont ajoutés à *target* si fourni,
        sinon à self._measure_preview_items (segment temporaire).
        selected=True → couleur orange ; False → jaune.
        """
        # Conversion image → écran
        sx1, sy1 = self._img_to_screen(*p1)
        sx2, sy2 = self._img_to_screen(*p2)
        r    = 3
        mx, my = (sx1 + sx2) / 2, (sy1 + sy2) / 2
        color = "#ff9900" if selected else "#ffff00"

        # ── Calcul distance réelle (directement en coords image) ─────────────
        ix1, iy1 = p1;  ix2, iy2 = p2
        dx_img = abs(ix2 - ix1)
        dy_img = abs(iy2 - iy1)

        if self._pixel_spacing is not None:
            dist_mm = math.hypot(dx_img * self._pixel_spacing[1],
                                  dy_img * self._pixel_spacing[0])
            dist_label = f"{dist_mm:.1f} mm"
        else:
            dist_img_px = math.hypot(dx_img, dy_img)
            dist_label = f"{dist_img_px:.1f} px (pas de calibration)"

        line   = self._canvas.create_line(sx1, sy1, sx2, sy2,
                                           fill=color, width=2, dash=(5, 3))
        dot1   = self._canvas.create_oval(sx1-r, sy1-r, sx1+r, sy1+r,
                                           fill=color, outline="")
        dot2   = self._canvas.create_oval(sx2-r, sy2-r, sx2+r, sy2+r,
                                           fill=color, outline="")
        label_y = my - 15
        shadow = self._canvas.create_text(mx+1, label_y+1,
                                           text=dist_label,
                                           fill="#000000", font=FONT_MEASURE)
        label  = self._canvas.create_text(mx, label_y,
                                           text=dist_label,
                                           fill=color, font=FONT_MEASURE)
        items = [line, dot1, dot2, shadow, label]
        if target is not None:
            target.extend(items)
        else:
            self._measure_preview_items.extend(items)

    def _clear_measure(self):
        for segs in self._measures_by_frame.values():
            for seg in segs:
                for item in seg["items"]:
                    self._canvas.delete(item)
        self._measures_by_frame.clear()
        self._measure_drawing.clear()
        for item in self._measure_preview_items:
            self._canvas.delete(item)
        self._measure_preview_items.clear()
        self._measure_selected = None
        self._measure_edit = None

    def _redraw_measures(self, preview: tuple | None = None):
        """Redessine tous les segments finalisés + éventuellement un segment en cours."""
        # Supprime les items canvas de chaque segment puis les recrée
        for i, seg in enumerate(self._measures_by_frame.get(self._frame_idx, [])):
            for item in seg["items"]:
                self._canvas.delete(item)
            seg["items"].clear()
            self._draw_measure_overlay(
                seg["pts"][0], seg["pts"][1],
                selected=(i == self._measure_selected),
                target=seg["items"],
            )
        # Preview (segment en cours de dessin)
        for item in self._measure_preview_items:
            self._canvas.delete(item)
        self._measure_preview_items.clear()
        if preview is not None:
            self._draw_measure_overlay(preview[0], preview[1],
                                        selected=False, target=None)

    # ── Hit-test mesures ──────────────────────────────────────────────────────

    def _measure_hit(self, x: int, y: int) -> tuple | None:
        """Renvoie (seg_idx, 'p1'|'p2'|'seg') pour le premier segment touché, ou None.

        *x, y* sont en coordonnées écran ; les pts stockés sont en coords image.
        """
        ENDPOINT_R = 8
        LINE_DIST  = 6
        for i, seg in enumerate(self._measures_by_frame.get(self._frame_idx, [])):
            # Convertir les coords image en écran pour le hit-test
            sx1, sy1 = self._img_to_screen(*seg["pts"][0])
            sx2, sy2 = self._img_to_screen(*seg["pts"][1])
            if math.hypot(x - sx1, y - sy1) <= ENDPOINT_R:
                return (i, "p1")
            if math.hypot(x - sx2, y - sy2) <= ENDPOINT_R:
                return (i, "p2")
            if self._dist_to_segment(x, y, sx1, sy1, sx2, sy2) <= LINE_DIST:
                return (i, "seg")
        return None

    @staticmethod
    def _dist_to_segment(px: float, py: float,
                          x1: float, y1: float,
                          x2: float, y2: float) -> float:
        """Distance d'un point (px,py) au segment [(x1,y1)-(x2,y2)]."""
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    def _on_measure_delete(self, event=None):
        """Supprime le segment de mesure sélectionné (touche Delete/BackSpace)."""
        if self._view_mode != "measure" or self._measure_selected is None:
            return
        frame_measures = self._measures_by_frame.get(self._frame_idx, [])
        if self._measure_selected >= len(frame_measures):
            return
        seg = frame_measures.pop(self._measure_selected)
        for item in seg["items"]:
            self._canvas.delete(item)
        self._measure_selected = None

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

    def _toggle_measure(self):
        if self._view_mode == "measure":
            self._view_mode = "normal"
            self._canvas.config(cursor="")
        else:
            self._view_mode = "measure"
            self._canvas.config(cursor="crosshair")

    def _toggle_cl_drag(self):
        if self._view_mode == "cl_drag":
            self._view_mode = "normal"
            self._canvas.config(cursor="")
        else:
            self._view_mode = "cl_drag"
            self._canvas.config(cursor="fleur")
            self._drag_start = None

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
        import json, sys
        # Miroir go_print (thread-safe, pas de Tk)
        print(f"GO_PRINT|{level}|" + json.dumps({"level": level, "message": message}),
              flush=True)
        # Toutes les opérations Tk doivent passer par le thread principal
        self.after(0, self._log_to_widget, message, level)

    def _log_to_widget(self, message: str, level: str):
        """Écrit dans le widget console (appelée dans le thread principal)."""
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


# ── Point d'entrée ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = STARHEApp()
    app.mainloop()
