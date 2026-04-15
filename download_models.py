#!/usr/bin/env python3
"""
download_models.py — Téléchargement des poids IA STARHE
=========================================================
Télécharge les checkpoints RTMDet et C3D depuis la Release GitHub STARHE_MODELS.
Les fichiers sont placés dans pythonCode/modules/starhe_plugin/models/.

Usage :
    python download_models.py            # télécharge uniquement les manquants
    python download_models.py --force    # re-télécharge même si déjà présents

Repo privé : définir la variable d'environnement GITHUB_TOKEN avec un Personal
Access Token GitHub (scope : repo ou read:packages) :
    export GITHUB_TOKEN=ghp_xxxxxxxxxxxx   # macOS/Linux
    $env:GITHUB_TOKEN="ghp_xxxxxxxxxxxx"   # Windows PowerShell
"""

import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
_REPO    = "https://github.com/cesthugo/PLUGIN1-MEDomics"
_TAG     = "STARHE_MODELS"
_BASE    = f"{_REPO}/releases/download/{_TAG}"

MODELS_DIR = Path(__file__).parent / "pythonCode" / "modules" / "starhe_plugin" / "models"

# (nom_fichier, sha256_hex_ou_None)  — sha256 optionnel, vérifie l'intégrité si renseigné
WEIGHTS = [
    ("best_acc_mean_cls_f1_epoch_14.pth",    None),
    ("best_coco_bbox_mAP_50_iter_2100.pth",  None),
]


# ── GitHub token (repo privé) ────────────────────────────────────────────────
_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_API_BASE     = "https://api.github.com/repos/cesthugo/PLUGIN1-MEDomics"


def _make_request(url: str) -> urllib.request.Request:
    """Construit une Request avec header Authorization si GITHUB_TOKEN est défini."""
    req = urllib.request.Request(url)
    if _GITHUB_TOKEN:
        req.add_header("Authorization", f"Bearer {_GITHUB_TOKEN}")
    req.add_header("Accept", "application/octet-stream")
    return req


def _resolve_asset_url(name: str) -> str:
    """
    Pour un repo privé, l'URL directe /releases/download/ renvoie 404 même avec token.
    Il faut passer par l'API GitHub pour obtenir l'URL de l'asset, puis la suivre.
    """
    if not _GITHUB_TOKEN:
        return f"{_BASE}/{name}"
    import json
    api_url = f"{_API_BASE}/releases/tags/{_TAG}"
    try:
        req = urllib.request.Request(api_url)
        req.add_header("Authorization", f"Bearer {_GITHUB_TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        with urllib.request.urlopen(req) as resp:
            release = json.loads(resp.read())
        for asset in release.get("assets", []):
            if asset["name"] == name:
                return asset["url"]  # URL API de l'asset (nécessite Accept: octet-stream)
    except Exception:
        pass
    return f"{_BASE}/{name}"  # fallback


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class _Progress:
    def __init__(self, name: str):
        self._name = name

    def __call__(self, block_num: int, block_size: int, total_size: int):
        if total_size <= 0:
            return
        downloaded = min(block_num * block_size, total_size)
        pct = downloaded / total_size * 100
        bar_len = 40
        filled = int(bar_len * downloaded / total_size)
        bar = "█" * filled + "░" * (bar_len - filled)
        mb_done  = downloaded / 1024 ** 2
        mb_total = total_size  / 1024 ** 2
        print(f"\r  {bar} {pct:5.1f}%  {mb_done:.0f}/{mb_total:.0f} MB",
              end="", flush=True)
        if downloaded >= total_size:
            print()


def _download(name: str, expected_sha256: "str | None", force: bool) -> bool:
    dest = MODELS_DIR / name

    if dest.exists() and not force:
        if expected_sha256 is None:
            print(f"  ✓  {name} — déjà présent.")
            return True
        if _sha256(dest) == expected_sha256:
            print(f"  ✓  {name} — déjà présent (SHA-256 OK).")
            return True
        print(f"  ⚠  {name} — présent mais SHA-256 incorrect, re-téléchargement…")

    asset_url = _resolve_asset_url(name)
    print(f"  ↓  {name}")
    print(f"     URL : {asset_url}")
    progress = _Progress(name)
    try:
        req = _make_request(asset_url)
        with urllib.request.urlopen(req) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            block = 65536
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(block)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress(downloaded // block, block, total)
        progress(total // block + 1, block, total)  # force 100%
    except urllib.error.HTTPError as exc:
        print(f"\n  ✗  Erreur HTTP {exc.code}")
        if exc.code == 404:
            print(f"     Vérifiez que la Release {_TAG} existe et que '{name}' y est attaché.")
        elif exc.code == 401:
            print(f"     Authentification échouée — vérifiez GITHUB_TOKEN.")
        dest.unlink(missing_ok=True)
        return False
    except Exception as exc:
        print(f"\n  ✗  Échec : {exc}")
        dest.unlink(missing_ok=True)
        return False

    if expected_sha256 and _sha256(dest) != expected_sha256:
        print(f"  ✗  SHA-256 incorrect après téléchargement — fichier supprimé.")
        dest.unlink()
        return False

    size_mb = dest.stat().st_size / 1024 ** 2
    print(f"  ✓  {name} ({size_mb:.0f} MB) — téléchargé avec succès.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Télécharge les poids IA STARHE")
    parser.add_argument("--force", action="store_true",
                        help="Re-télécharge même si le fichier est déjà présent")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Dossier poids : {MODELS_DIR}")
    print(f"Release       : {_REPO}/releases/tag/{_TAG}")
    print()

    ok = True
    for name, sha256 in WEIGHTS:
        ok &= _download(name, sha256, force=args.force)

    print()
    if ok:
        print("Tous les poids sont disponibles.")
    else:
        print("Certains téléchargements ont échoué.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
