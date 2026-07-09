# -*- mode: python ; coding: utf-8 -*-
# starhe_worker.spec — PyInstaller config to bundle the STARHE Python worker
#
# Build :
#   cd pythonCode/modules
#   pyinstaller ../../scripts/starhe_worker.spec --noconfirm \
#               --distpath ../../renderer/build-resources
# Output: renderer/build-resources/starhe_worker/
#
# Mode --onedir (et non --onefile) :
#   - ~5× faster startup (no decompression on each call)
#   - Bundle inspectable (debug plus facile)
#   - .pth models can be added alongside without a rebuild
#
# hiddenimports strategy:
#   mmdet / mmcv-lite / mmengine do many dynamic imports via the Registry.
#   We explicitly force the modules we need at runtime.
#   `collect_submodules` is avoided for mmdet/mmcv: these packages fail to
#   the import during PyInstaller analysis (mmcv-lite has no `mmcv._ext`,
#   which is only needed at runtime for certain GPU ops not used here).

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Root path = pythonCode/modules/ (the spec is in scripts/, go up one level)
SRC_ROOT = os.path.abspath(os.path.join(SPECPATH, '..', 'pythonCode', 'modules'))
ENTRY = os.path.join(SRC_ROOT, 'starhe_plugin', 'starhe_worker.py')

# Injection into sys.path BEFORE collect_submodules: otherwise importlib
# cannot find starhe_plugin (which is not installed as a package in the venv).
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

# ── Hidden imports (loaded dynamically by mm* / pylibjpeg / etc.) ─────────────
# Note: no collect_submodules('mmdet.*') / mmcv.ops because they crash during
# analysis with mmcv-lite. We manually list what we need.
hiddenimports = [
    # mmengine
    'mmengine', 'mmengine.config', 'mmengine.registry', 'mmengine.runner',
    'mmengine.model', 'mmengine.dataset', 'mmengine.hooks', 'mmengine.logging',
    # mmcv-lite (subset Python pur uniquement)
    'mmcv', 'mmcv.cnn', 'mmcv.cnn.bricks', 'mmcv.transforms', 'mmcv.image',
    'mmcv.utils', 'mmcv.video',
    # mmdet (loaded via the Registry at runtime)
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
    # prepUS (vendored)
    'sonocrop', 'prepUS', 'prepUS.backscan', 'prepUS.cli', 'prepUS.utils',
    # starhe_plugin submodules loaded dynamically
    'starhe_plugin.ai.models.c3d',
    'starhe_plugin.ai.models.rtmdet',
    'starhe_plugin.ai.models.dino',
    'starhe_plugin.ai.models._dino_runner',
    'starhe_plugin.ai.models._rtmdet_runner',
]

# Safe dynamic submodules (non-blocking during analysis)
hiddenimports += collect_submodules('pylibjpeg_openjpeg')
hiddenimports += collect_submodules('pylibjpeg_libjpeg')
# All starhe_plugin submodules (loaded via runpy.run_module by the dispatcher)
hiddenimports += collect_submodules('starhe_plugin')
hiddenimports += collect_submodules('prepUS')

# ── Embedded data (YAML configs, registries, etc.) ────────────────────────────
datas = []
datas += collect_data_files('mmdet', includes=['**/*.yml', '**/*.json'])
datas += collect_data_files('mmengine', includes=['**/*.yml', '**/*.json'])
datas += collect_data_files('mmcv', includes=['**/*.yml', '**/*.json'])
# The plugin's mmdet configs (rtmdet_starhe.py — loaded dynamically by mmengine.Config.fromfile)
datas += [
    (os.path.join(SRC_ROOT, 'starhe_plugin/models/rtmdet_starhe.py'), 'starhe_plugin/models/'),
]

# ── Exclusions (lighten the bundle by ~150 MB) ────────────────────────────────
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
    upx=False,  # disabled: UPX sometimes breaks libtorch on macOS
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
