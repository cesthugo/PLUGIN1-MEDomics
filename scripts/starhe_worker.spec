# -*- mode: python ; coding: utf-8 -*-
# starhe_worker.spec — PyInstaller config pour bundler le worker Python STARHE
#
# Build :
#   cd pythonCode/modules
#   pyinstaller ../../scripts/starhe_worker.spec --noconfirm \
#               --distpath ../../renderer/build-resources
# Sortie : renderer/build-resources/starhe_worker/
#
# Mode --onedir (et non --onefile) :
#   - Démarrage ~5× plus rapide (pas de décompression à chaque appel)
#   - Bundle inspectable (debug plus facile)
#   - Modèles .pth peuvent être ajoutés à côté sans rebuild
#
# Stratégie hiddenimports :
#   mmdet / mmcv-lite / mmengine font beaucoup d'imports dynamiques via Registry.
#   On force explicitement les modules dont on a besoin au runtime.
#   `collect_submodules` est évité pour mmdet/mmcv : ces packages échouent à
#   l'import au moment de l'analyse PyInstaller (mmcv-lite n'a pas `mmcv._ext`,
#   qui n'est requis qu'à l'exécution pour certaines ops GPU non utilisées ici).

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Chemin racine = pythonCode/modules/ (le spec est dans scripts/, on remonte de 1)
SRC_ROOT = os.path.abspath(os.path.join(SPECPATH, '..', 'pythonCode', 'modules'))
ENTRY = os.path.join(SRC_ROOT, 'starhe_plugin', 'starhe_worker.py')

# Injection dans sys.path AVANT collect_submodules : sinon importlib ne
# trouve pas starhe_plugin (qui n'est pas installé comme package dans le venv).
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

# ── Imports cachés (chargés dynamiquement par mm* / pylibjpeg / etc.) ─────────
# Note : pas de collect_submodules('mmdet.*') / mmcv.ops car ils plantent à
# l'analyse avec mmcv-lite. On liste manuellement ce dont on a besoin.
hiddenimports = [
    # mmengine
    'mmengine', 'mmengine.config', 'mmengine.registry', 'mmengine.runner',
    'mmengine.model', 'mmengine.dataset', 'mmengine.hooks', 'mmengine.logging',
    # mmcv-lite (subset Python pur uniquement)
    'mmcv', 'mmcv.cnn', 'mmcv.cnn.bricks', 'mmcv.transforms', 'mmcv.image',
    'mmcv.utils', 'mmcv.video',
    # mmdet (chargé via Registry au runtime)
    'mmdet', 'mmdet.models', 'mmdet.models.detectors', 'mmdet.models.backbones',
    'mmdet.models.necks', 'mmdet.models.dense_heads', 'mmdet.models.roi_heads',
    'mmdet.models.task_modules', 'mmdet.models.losses', 'mmdet.models.layers',
    'mmdet.datasets', 'mmdet.datasets.transforms',
    'mmdet.engine', 'mmdet.engine.hooks', 'mmdet.engine.runner',
    'mmdet.evaluation', 'mmdet.structures', 'mmdet.utils',
    # pydicom / pylibjpeg
    'pydicom.encoders.gdcm',
    'pydicom.encoders.pylibjpeg',
    'pydicom.encoders.native',
    'pylibjpeg', 'pylibjpeg_openjpeg', 'pylibjpeg_libjpeg',
    # prepUS (vendorisé)
    'sonocrop', 'prepUS', 'prepUS.backscan', 'prepUS.cli', 'prepUS.utils',
    # Sous-modules starhe_plugin chargés dynamiquement
    'starhe_plugin.ai.models.c3d',
    'starhe_plugin.ai.models.rtmdet',
    'starhe_plugin.ai.models.dino',
    'starhe_plugin.ai.models._dino_runner',
    'starhe_plugin.ai.models._rtmdet_runner',
]

# Sous-modules dynamiques sûrs (non bloquants à l'analyse)
hiddenimports += collect_submodules('pylibjpeg_openjpeg')
hiddenimports += collect_submodules('pylibjpeg_libjpeg')
# Tous les sous-modules de starhe_plugin (chargés via runpy.run_module par le dispatcher)
hiddenimports += collect_submodules('starhe_plugin')
hiddenimports += collect_submodules('prepUS')

# ── Données embarquées (configs YAML, registres, etc.) ────────────────────────
datas = []
datas += collect_data_files('mmdet', includes=['**/*.yml', '**/*.json'])
datas += collect_data_files('mmengine', includes=['**/*.yml', '**/*.json'])
datas += collect_data_files('mmcv', includes=['**/*.yml', '**/*.json'])
# Configs mmdet du plugin (rtmdet_starhe.py — chargé dynamiquement par mmengine.Config.fromfile)
datas += [
    (os.path.join(SRC_ROOT, 'starhe_plugin/models/rtmdet_starhe.py'), 'starhe_plugin/models/'),
]

# ── Exclusions (allègent le bundle de ~150 MB) ────────────────────────────────
excludes = [
    'tkinter',
    'matplotlib',
    'IPython',
    'jupyter',
    'pytest',
    'sphinx',
    'tornado',
    'notebook',
    'pandas',
    'sklearn',
    'sympy',
    'tensorboard',
]

a = Analysis(
    [ENTRY],
    pathex=[SRC_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='starhe_worker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # désactivé : UPX casse parfois libtorch sur macOS
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='starhe_worker',
)
