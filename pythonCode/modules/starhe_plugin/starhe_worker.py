"""
starhe_worker.py — Point d'entrée unique du bundle PyInstaller
==============================================================

Dispatch vers les 5 modules CLI du plugin STARHE selon l'argument `--module`.
Permet de bundler **un seul** exécutable (~350 MB) au lieu de cinq.

Usage (équivalent direct des appels `python -m starhe_plugin.X` du Go server) :

    starhe_worker --module pipeline /path/file.dcm --anon_mode hash ...
    starhe_worker --module pipeline_mp4 /path/file.mp4 ...
    starhe_worker --module ai.run_live ...
    starhe_worker --module dicom.loader_cli /path/file.dcm
    starhe_worker --module dicom.loader_mp4_cli /path/file.mp4

Le dispatcher consomme `--module X` puis rejoue les args restants dans
`sys.argv` et exécute le module avec `runpy.run_module(..., run_name='__main__')`
— de sorte que le bloc `if __name__ == "__main__":` de chaque module
s'exécute exactement comme avec `python -m`.

Aucun code des modules n'est dupliqué.
"""
import runpy
import sys

_ALLOWED = {
    "pipeline":              "starhe_plugin.pipeline",
    "pipeline_mp4":          "starhe_plugin.pipeline_mp4",
    "ai.run_live":           "starhe_plugin.ai.run_live",
    "dicom.loader_cli":      "starhe_plugin.dicom.loader_cli",
    "dicom.loader_mp4_cli":  "starhe_plugin.dicom.loader_mp4_cli",
}


def _usage_and_exit(code: int = 2) -> None:
    sys.stderr.write(
        "starhe_worker — dispatcher PyInstaller\n"
        "Usage: starhe_worker --module <name> [args...]\n"
        f"Modules disponibles : {', '.join(sorted(_ALLOWED))}\n"
    )
    sys.exit(code)


def main() -> None:
    argv = sys.argv[1:]
    if len(argv) < 2 or argv[0] != "--module":
        _usage_and_exit()

    module_key = argv[1]
    if module_key not in _ALLOWED:
        sys.stderr.write(f"starhe_worker: module inconnu '{module_key}'\n")
        _usage_and_exit()

    # Reconstruit sys.argv comme si on avait fait `python -m <fully.qualified.module> <args>`
    # PyInstaller : sys.argv[0] doit rester le nom du module pour que argparse affiche
    # une aide cohérente en cas d'erreur.
    sys.argv = [module_key] + argv[2:]
    runpy.run_module(_ALLOWED[module_key], run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
