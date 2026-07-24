"""
starhe_worker.py — Single entry point of the PyInstaller bundle
==============================================================

Dispatches to the 3 CLI modules of the STARHE plugin based on the `--module` argument.
Allows bundling **a single** executable (~350 MB) instead of three.

Usage (direct equivalent of the Go server's `python -m starhe_plugin.X` calls):

    starhe_worker --module pipeline /path/file.dcm --anon_mode hash ...
    starhe_worker --module ai.run_live ...
    starhe_worker --module dicom.loader_cli /path/file.dcm

The dispatcher consumes `--module X` then replays the remaining args in
`sys.argv` and runs the module with `runpy.run_module(..., run_name='__main__')`
— so that each module's `if __name__ == "__main__":` block
runs exactly as with `python -m`.

No module code is duplicated.
"""
import os
import runpy
import sys

# In the frozen bundle, starhe_risk.py / starhe_detect.py spawn their model
# runners with [sys.executable, "<...>/_rtmdet_runner.py", <args>]. But
# sys.executable is THIS worker (not a python interpreter) and the runner .py
# source is not on disk (it lives in the PYZ). So detect the runner by filename
# and dispatch to its module — leaving the model spawn code untouched.
_RUNNERS = {
    "_rtmdet_runner.py": "starhe_plugin.ai.models._rtmdet_runner",
    "_c3d_runner.py":    "starhe_plugin.ai.models._c3d_runner",
    "_dino_runner.py":   "starhe_plugin.ai.models._dino_runner",
}

_ALLOWED = {
    "pipeline":              "starhe_plugin.pipeline",
    "ai.run_live":           "starhe_plugin.ai.run_live",
    "dicom.loader_cli":      "starhe_plugin.dicom.loader_cli",
}


def _usage_and_exit(code: int = 2) -> None:
    sys.stderr.write(
        "starhe_worker — PyInstaller dispatcher\n"
        "Usage: starhe_worker --module <name> [args...]\n"
        f"Available modules: {', '.join(sorted(_ALLOWED))}\n"
    )
    sys.exit(code)


def main() -> None:
    argv = sys.argv[1:]

    # Frozen-mode model runner: spawned as [worker, "<...>/_rtmdet_runner.py", args].
    if argv and os.path.basename(argv[0]) in _RUNNERS:
        module = _RUNNERS[os.path.basename(argv[0])]
        sys.argv = argv  # [runner.py, <args>] — runner's argparse ignores argv[0]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
        return

    if len(argv) < 2 or argv[0] != "--module":
        _usage_and_exit()

    module_key = argv[1]
    if module_key not in _ALLOWED:
        sys.stderr.write(f"starhe_worker: unknown module '{module_key}'\n")
        _usage_and_exit()

    # Rebuild sys.argv as if we had run `python -m <fully.qualified.module> <args>`
    # PyInstaller: sys.argv[0] must remain the module name so that argparse displays
    # a consistent help message on error.
    sys.argv = [module_key] + argv[2:]
    runpy.run_module(_ALLOWED[module_key], run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
