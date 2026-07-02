"""
weasis_bridge.py — Décodage DICOM via le CLI Java weasis-dcm2png
=================================================================

Reproduit la chaîne d'entraînement de Jérémy : DICOM → PNG (avec Modality LUT
+ VOI LUT appliquées comme dans Weasis) → numpy. La sortie est ensuite
injectée dans `prepus_bridge` (preprocess_with_prepus[_inmem]) à la place du
chemin pydicom direct.

Le JAR est vendorisé dans `third_party/weasis-dcm2png/dist/` ; les libs
natives OpenCV+DCM4CHE sont dans `dist/native/` (chargées via
`-Djava.library.path`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image

from starhe_plugin.config    import PROJECT_ROOT, TEMP_DIR
from starhe_plugin.utils.go_print import go_print


# ── Chemins des artefacts Weasis ─────────────────────────────────────────────
# En mode dev : pointe vers `third_party/weasis-dcm2png/dist/` du dépôt.
# En mode bundle Electron : `STARHE_WEASIS_DIR` est défini par main.ts et
# pointe vers `STARHE.app/Contents/Resources/weasis-dcm2png/` (extraResources),
# qui contient directement `weasis-dcm2png.jar` + `native/`.
_WEASIS_DIST_ENV = os.environ.get("STARHE_WEASIS_DIR")
if _WEASIS_DIST_ENV:
    WEASIS_DIST_DIR = Path(_WEASIS_DIST_ENV)
else:
    WEASIS_DIST_DIR = Path(PROJECT_ROOT) / "third_party" / "weasis-dcm2png" / "dist"

WEASIS_JAR         = WEASIS_DIST_DIR / "weasis-dcm2png.jar"
WEASIS_NATIVE_DIR  = WEASIS_DIST_DIR / "native"


def _java_bin() -> str | None:
    """Résout l'exécutable `java` à utiliser.

    Priorité :
    1. `STARHE_JAVA_BIN` (défini par Electron en mode packagé → JRE Temurin
       embarquée dans `STARHE.app/Contents/Resources/jre/bin/java`).
    2. JRE Temurin bundlé dans le dépôt (renderer/build-resources/jre-*/bin/java)
       — disponible après `scripts/fetch_jre.sh`. Évite la dépendance au PATH
       système (sur macOS, /usr/bin/java est un stub installeur, pas une JVM).
    3. `java` du PATH système (mode dev avec `brew install openjdk@17`).

    Retourne `None` si rien n'est trouvé ou si la JVM est un stub macOS.
    """
    env_bin = os.environ.get("STARHE_JAVA_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin

    # JRE bundlé dans le dépôt (plusieurs variantes possibles selon la plateforme)
    import platform
    arch = "arm64" if platform.machine() == "arm64" else "x64"
    os_name = "mac" if sys.platform == "darwin" else ("win" if sys.platform == "win32" else "linux")
    java_exe = "java.exe" if sys.platform == "win32" else "java"
    bundled = Path(PROJECT_ROOT) / "renderer" / "build-resources" / f"jre-{os_name}-{arch}" / "bin" / java_exe
    if bundled.is_file():
        try:
            r = subprocess.run([str(bundled), "-version"],
                               capture_output=True, timeout=5)
            if r.returncode == 0:
                return str(bundled)
        except (subprocess.TimeoutExpired, OSError):
            pass

    return shutil.which("java")


def weasis_available() -> bool:
    """True si le JAR + une JVM fonctionnelle sont disponibles.

    Sur macOS, `/usr/bin/java` est parfois un stub installeur qui ouvre une
    fenêtre au lieu de lancer la JVM → on vérifie avec `java -version`.
    """
    if not WEASIS_JAR.is_file():
        return False
    java = _java_bin()
    if java is None:
        return False
    try:
        res = subprocess.run(
            [java, "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return res.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def export_dicom_to_pngs_weasis(dicom_path: str | Path,
                                out_dir:    str | Path) -> Tuple[float, int]:
    """Lance le JAR weasis-dcm2png sur `dicom_path`, écrit les PNG dans `out_dir`.

    Returns (fps, n_frames). Raise RuntimeError si la JVM/JAR échoue
    (ex. transfer syntax JPEG 2000 non supportée par weasis).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    java = _java_bin()
    if java is None:
        raise RuntimeError("java introuvable (ni STARHE_JAVA_BIN ni PATH)")

    cmd = [
        java,
        f"-Djava.library.path={WEASIS_NATIVE_DIR}",
        "--enable-native-access=ALL-UNNAMED",
        "-jar", str(WEASIS_JAR),
        str(dicom_path),
        str(out_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(
            f"weasis-dcm2png exit={proc.returncode}\n"
            f"stdout={proc.stdout.strip()[:400]}\n"
            f"stderr={proc.stderr.strip()[:400]}"
        )

    # Parse `fps=…` et `frames=…` sur stdout
    fps:      float = 0.0
    n_frames: int   = 0
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("fps="):
            try:
                fps = float(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("frames="):
            try:
                n_frames = int(line.split("=", 1)[1])
            except ValueError:
                pass

    if n_frames == 0:
        # Fallback : compter les PNG produits
        n_frames = len(list(out_dir.glob("*.png")))
    if n_frames == 0:
        raise RuntimeError(f"weasis-dcm2png n'a produit aucun PNG dans {out_dir}")

    return fps, n_frames


def _pngs_to_numpy(png_dir: Path) -> np.ndarray:
    """Lit tous les PNG triés et retourne (T, H, W, 3) uint8 RGB."""
    paths = sorted(png_dir.glob("*.png"))
    if not paths:
        raise RuntimeError(f"Aucun PNG trouvé dans {png_dir}")

    frames = []
    for p in paths:
        with Image.open(p) as im:
            arr = np.asarray(im.convert("RGB"), dtype=np.uint8)
        frames.append(arr)
    return np.stack(frames, axis=0)


def frames_via_weasis(dicom_path: str | Path,
                      work_dir:   str | Path | None = None
                      ) -> Tuple[np.ndarray, float]:
    """DICOM → PNG (Weasis LUT) → numpy RGB (T, H, W, 3).

    Returns (frames_rgb_uint8, fps). Lève RuntimeError si la conversion
    échoue ; l'appelant doit alors retomber sur le chemin pydicom.

    Le dossier de travail temporaire est nettoyé automatiquement.
    """
    cleanup = False
    if work_dir is None:
        work_dir = tempfile.mkdtemp(prefix="weasis_", dir=TEMP_DIR)
        cleanup  = True
    work_dir = Path(work_dir)

    try:
        fps, n_frames = export_dicom_to_pngs_weasis(dicom_path, work_dir)
        frames_rgb    = _pngs_to_numpy(work_dir)
        go_print("info",
                 f"weasis-dcm2png: {frames_rgb.shape[0]} frames "
                 f"({frames_rgb.shape[2]}×{frames_rgb.shape[1]}) "
                 f"fps={fps:.2f}")
        return frames_rgb, fps
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)
