#!/usr/bin/env python3
"""
patch_mmaction.py — Apply the Python 3.13 / mmdet compatibility patches to the
installed mmaction2 package (same edits as scripts/setup.sh, but cross-platform
so CI can run it on macOS / Linux / Windows).

mmaction2 is installed `--no-deps` and needs three edits to import under Python
3.13 alongside mmdet:
  1. models/localizers/__init__.py : drop the DRN import (absent from wheel 1.2.0)
  2. models/roi_heads/__init__.py  : add AssertionError to the except clause
  3. models/task_modules/__init__.py: same AssertionError fix
"""
import importlib.util
import pathlib
import sys


def main() -> int:
    spec = importlib.util.find_spec("mmaction")
    if spec is None or not spec.submodule_search_locations:
        print("patch_mmaction: mmaction not importable — is it installed?", file=sys.stderr)
        return 1
    pkg = pathlib.Path(list(spec.submodule_search_locations)[0])

    def edit(rel: str, transform) -> None:
        p = pkg / rel
        if not p.exists():
            print(f"patch_mmaction: skip (absent) {rel}")
            return
        p.write_text(transform(p.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"patch_mmaction: patched {rel}")

    # 1. Remove the DRN import + its entry in __all__.
    def localizers(t: str) -> str:
        t = "\n".join(l for l in t.splitlines() if "from .drn.drn import DRN" not in l)
        t = t.replace(", 'DRN']", "]").replace("'DRN', ", "").replace("'DRN'", "")
        return t + "\n"
    edit("models/localizers/__init__.py", localizers)

    # 2 & 3. Tolerate AssertionError (mmdet ↔ mmengine registry conflict).
    def add_assertion(t: str) -> str:
        return t.replace(
            "except (ImportError, ModuleNotFoundError):",
            "except (ImportError, ModuleNotFoundError, AssertionError):",
        )
    edit("models/roi_heads/__init__.py", add_assertion)
    edit("models/task_modules/__init__.py", add_assertion)

    print(f"patch_mmaction: done ({pkg})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
