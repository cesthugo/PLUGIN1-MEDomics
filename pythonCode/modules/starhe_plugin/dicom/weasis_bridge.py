"""
weasis_bridge.py — DICOM decoding via the weasis-dcm2png Java CLI
=================================================================

Reproduces Jérémy's training chain: DICOM → PNG (with Modality LUT
+ VOI LUT applied as in Weasis) → numpy. The output is then
fed into `prepus_bridge` (preprocess_with_prepus[_inmem]) instead of the
direct pydicom path.

The JAR is vendored in `third_party/weasis-dcm2png/dist/`; the native
OpenCV+DCM4CHE libs are in `dist/native/` (loaded via
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


# ── Paths to the Weasis artifacts ────────────────────────────────────────────
# In dev mode: points to the repo's `third_party/weasis-dcm2png/dist/`.
# In Electron bundle mode: `STARHE_WEASIS_DIR` is set by main.ts and
# points to `STARHE.app/Contents/Resources/weasis-dcm2png/` (extraResources),
# which directly contains `weasis-dcm2png.jar` + `native/`.
_WEASIS_DIST_ENV = os.environ.get("STARHE_WEASIS_DIR")
if _WEASIS_DIST_ENV:
    WEASIS_DIST_DIR = Path(_WEASIS_DIST_ENV)
else:
    WEASIS_DIST_DIR = Path(PROJECT_ROOT) / "third_party" / "weasis-dcm2png" / "dist"

WEASIS_JAR         = WEASIS_DIST_DIR / "weasis-dcm2png.jar"
WEASIS_NATIVE_DIR  = WEASIS_DIST_DIR / "native"


def _java_bin() -> str | None:
    """Resolves the `java` executable to use.

    Priority:
    1. `STARHE_JAVA_BIN` (set by Electron in packaged mode → Temurin JRE
       embedded in `STARHE.app/Contents/Resources/jre/bin/java`).
    2. Temurin JRE bundled in the repo (renderer/build-resources/jre-*/bin/java)
       — available after `scripts/fetch_jre.sh`. Avoids the dependency on the
       system PATH (on macOS, /usr/bin/java is an installer stub, not a JVM).
    3. `java` from the system PATH (dev mode with `brew install openjdk@17`).

    Returns `None` if nothing is found or if the JVM is a macOS stub.
    """
    env_bin = os.environ.get("STARHE_JAVA_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin

    # JRE bundled in the repo (several variants possible depending on the platform)
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
    """True if the JAR + a working JVM are available.

    On macOS, `/usr/bin/java` is sometimes an installer stub that opens a
    window instead of launching the JVM → check with `java -version`.
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
    """Runs the weasis-dcm2png JAR on `dicom_path`, writes the PNGs to `out_dir`.

    Returns (fps, n_frames). Raises RuntimeError if the JVM/JAR fails
    (e.g. JPEG 2000 transfer syntax not supported by weasis).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    java = _java_bin()
    if java is None:
        raise RuntimeError("java not found (neither STARHE_JAVA_BIN nor PATH)")

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

    # Parse `fps=…` and `frames=…` from stdout
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
        # Fallback: count the produced PNGs
        n_frames = len(list(out_dir.glob("*.png")))
    if n_frames == 0:
        raise RuntimeError(f"weasis-dcm2png produced no PNG in {out_dir}")

    return fps, n_frames


def _pngs_to_numpy(png_dir: Path) -> np.ndarray:
    """Reads all sorted PNGs and returns (T, H, W, 3) uint8 RGB."""
    paths = sorted(png_dir.glob("*.png"))
    if not paths:
        raise RuntimeError(f"No PNG found in {png_dir}")

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

    Returns (frames_rgb_uint8, fps). Raises RuntimeError if the conversion
    fails; the caller must then fall back to the pydicom path.

    The temporary work directory is cleaned up automatically.
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
