"""
run_starhe.py — Point d'entrée MEDomics pour le plugin STARHE
==============================================================
Ce script sert de **pont** entre la plateforme MEDomics et le pipeline
STARHE qui tourne dans son propre venv (torch, mmdet, etc.).

Protocole :
  1. MEDomics Go appelle :  condaEnv -u run_starhe.py --json-param <json> --id <id>
  2. Ce script lance le pipeline STARHE dans un subprocess (venv dédié)
  3. Il traduit les lignes GO_PRINT|…  → protocol MEDomics (progress*_*, response-ready*_*)
  4. Le résultat est renvoyé à MEDomics via GoExecutionScript.send_response()

json_param attendu :
{
    "dicom_path"           : str,     ← obligatoire
    "anon_mode"            : str,     ← "hash" | "remove" | "none" (défaut: "hash")
    "run_detection"        : bool,    ← défaut: true
    "back_scan_conversion" : bool,    ← défaut: true
    "backscan_width"       : int,     ← défaut: 512
    "backscan_height"      : int,     ← défaut: 512
    "patient_id"           : str      ← optionnel, pour tagging MongoDB
}
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Accès aux libs MEDomics ──────────────────────────────────────────────────
# Ce script tourne dans l'env Python de MEDomics (conda/venv MEDomics),
# PAS dans le venv STARHE. On a donc accès à med_libs/ via sys.path.
sys.path.append(
    str(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent))

from med_libs.GoExecutionScript import GoExecutionScript, parse_arguments
from med_libs.server_utils import go_print

json_params_dict, id_ = parse_arguments()
go_print("running run_starhe.py:" + id_)


# ── Détection du plugin STARHE ───────────────────────────────────────────────

def _find_starhe_paths() -> tuple[Path, Path, Path]:
    """
    Localise le répertoire du plugin STARHE, son venv Python, et le
    dossier modules/ parent.

    Ordre de recherche :
      1. Variable d'environnement STARHE_PLUGIN_DIR
      2. Dossier frère starhe_plugin/ (même parent que ce script)

    Returns:
        (plugin_root, venv_python, modules_dir)
    """
    if "STARHE_PLUGIN_DIR" in os.environ:
        root = Path(os.environ["STARHE_PLUGIN_DIR"])
    else:
        # starhe/ et starhe_plugin/ sont frères sous modules/
        root = Path(__file__).resolve().parent.parent / "starhe_plugin"

    if not root.is_dir():
        raise FileNotFoundError(
            f"Répertoire starhe_plugin introuvable : {root}\n"
            f"Définissez STARHE_PLUGIN_DIR ou placez le plugin à côté de ce script."
        )

    if sys.platform == "win32":
        py = root / ".venv" / "Scripts" / "python.exe"
    else:
        py = root / ".venv" / "bin" / "python"

    if not py.exists():
        raise FileNotFoundError(
            f"Venv STARHE introuvable : {py}\n"
            f"Exécutez d'abord le script de setup (setup.sh ou setup.ps1)."
        )

    modules_dir = root.parent  # pythonCode/modules/
    return root, py, modules_dir


# ── Script MEDomics ──────────────────────────────────────────────────────────

class GoExecScriptSTARHE(GoExecutionScript):
    """
    Adapter MEDomics → STARHE.

    Lance le pipeline STARHE en subprocess (venv dédié) et traduit
    le protocole GO_PRINT vers le protocole MEDomics (progress / response).
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

        # ── Localisation du venv STARHE ───────────────────────────────────
        plugin_root, starhe_python, modules_dir = _find_starhe_paths()

        # ── Construction de la commande subprocess ────────────────────────
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

        # ── Exécution + traduction du protocole ──────────────────────────
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
