"""
run_starhe.py — MEDomics entry point for the STARHE plugin
==============================================================
This script serves as a **bridge** between the MEDomics platform and the
STARHE pipeline that runs in its own venv (torch, mmdet, etc.).

Protocol:
  1. MEDomics Go calls:  condaEnv -u run_starhe.py --json-param <json> --id <id>
  2. This script launches the STARHE pipeline in a subprocess (dedicated venv)
  3. It translates the GO_PRINT|… lines → MEDomics protocol (progress*_*, response-ready*_*)
  4. The result is returned to MEDomics via GoExecutionScript.send_response()

Expected json_param:
{
    "dicom_path"           : str,     ← required
    "anon_mode"            : str,     ← "hash" | "remove" | "none" (default: "hash")
    "run_detection"        : bool,    ← default: true
    "back_scan_conversion" : bool,    ← default: true
    "backscan_width"       : int,     ← default: 512
    "backscan_height"      : int,     ← default: 512
    "patient_id"           : str      ← optional, for MongoDB tagging
}
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Access to the MEDomics libs ──────────────────────────────────────────────
# This script runs in the MEDomics Python env (conda/venv MEDomics),
# NOT in the STARHE venv. We therefore have access to med_libs/ via sys.path.
sys.path.append(
    str(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent))

from med_libs.GoExecutionScript import GoExecutionScript, parse_arguments
from med_libs.server_utils import go_print

json_params_dict, id_ = parse_arguments()
go_print("running run_starhe.py:" + id_)


# ── STARHE plugin detection ──────────────────────────────────────────────────

def _find_starhe_paths() -> tuple[Path, Path, Path]:
    """
    Locates the STARHE plugin directory, its Python venv, and the
    parent modules/ directory.

    Search order:
      1. STARHE_PLUGIN_DIR environment variable
      2. Sibling starhe_plugin/ directory (same parent as this script)

    Returns:
        (plugin_root, venv_python, modules_dir)
    """
    if "STARHE_PLUGIN_DIR" in os.environ:
        root = Path(os.environ["STARHE_PLUGIN_DIR"])
    else:
        # starhe/ and starhe_plugin/ are siblings under modules/
        root = Path(__file__).resolve().parent.parent / "starhe_plugin"

    if not root.is_dir():
        raise FileNotFoundError(
            f"starhe_plugin directory not found: {root}\n"
            f"Set STARHE_PLUGIN_DIR or place the plugin next to this script."
        )

    if sys.platform == "win32":
        py = root / ".venv" / "Scripts" / "python.exe"
    else:
        py = root / ".venv" / "bin" / "python"

    if not py.exists():
        raise FileNotFoundError(
            f"STARHE venv not found: {py}\n"
            f"Run the setup script first (setup.sh or setup.ps1)."
        )

    modules_dir = root.parent  # pythonCode/modules/
    return root, py, modules_dir


# ── MEDomics script ───────────────────────────────────────────────────────────

class GoExecScriptSTARHE(GoExecutionScript):
    """
    MEDomics → STARHE adapter.

    Launches the STARHE pipeline as a subprocess (dedicated venv) and translates
    the GO_PRINT protocol to the MEDomics protocol (progress / response).
    """

    def __init__(self, json_params: dict, _id: str = None):
        super().__init__(json_params, _id)
        self.results = {}

    def _custom_process(self, json_config: dict) -> dict:
        # ── Validation ────────────────────────────────────────────────────
        dicom_path = json_config.get("dicom_path")
        if not dicom_path:
            return {"error": {"message": "dicom_path est requis dans json_param."}}

        dicom_path = str(Path(dicom_path).resolve())
        if not Path(dicom_path).exists():
            return {"error": {"message": f"Fichier DICOM introuvable : {dicom_path}"}}

        # ── Locate the STARHE venv ────────────────────────────────────────
        plugin_root, starhe_python, modules_dir = _find_starhe_paths()

        # ── Build the subprocess command ──────────────────────────────────
        anon_mode  = json_config.get("anon_mode", "hash")
        bs_width   = str(json_config.get("backscan_width", 512))
        bs_height  = str(json_config.get("backscan_height", 512))

        cmd = [
            str(starhe_python), "-u",
            "-m", "starhe_plugin.pipeline",
            dicom_path,
            "--anon_mode", anon_mode,
            "--backscan_width", bs_width,
            "--backscan_height", bs_height,
        ]
        if not json_config.get("run_detection", True):
            cmd.append("--no_detection")
        if not json_config.get("back_scan_conversion", True):
            cmd.append("--no_backscan")

        env = {**os.environ,
               "PYTHONPATH": str(modules_dir),
               "PYTHONUTF8": "1"}

        # ── Execution + protocol translation ──────────────────────────────
        self.set_progress(label="Lancement du pipeline STARHE…", now=0)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,               # line-buffered
            cwd=str(modules_dir),
            env=env,
        )

        result_data = {}

        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("GO_PRINT|"):
                continue

            parts = line.split("|", 2)
            if len(parts) < 3:
                continue

            level = parts[1]
            try:
                payload = json.loads(parts[2])
            except json.JSONDecodeError:
                continue

            if level == "progress":
                data = payload.get("data", {})
                pct   = data.get("percent", 0)
                label = payload.get("message", "")
                self.set_progress(label=label, now=pct)

            elif level == "result":
                result_data = payload.get("data", payload)

            elif level == "error":
                msg = payload.get("message", str(payload))
                go_print(f"[STARHE ERROR] {msg}")

        proc.wait()

        if proc.returncode != 0:
            stderr_tail = (proc.stderr.read() or "")[-1000:]
            return {"error": {
                "message": f"Pipeline STARHE échoué (code {proc.returncode})",
                "stack_trace": stderr_tail,
            }}

        self.set_progress(label="Traitement STARHE terminé.", now=100)
        return result_data


script = GoExecScriptSTARHE(json_params_dict, id_)
script.start()
