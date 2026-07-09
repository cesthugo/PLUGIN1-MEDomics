# run_tkinter.ps1 - Standalone launcher for the STARHE Tkinter prototype (Windows)
# Standalone script: detects Python 3.13, creates the venv if missing,
# installs the dependencies and prepUS, then launches the interface.
# No manual configuration required after installing Python 3.13.

$ROOT          = Split-Path -Parent $PSScriptRoot
$VENV_DIR     = "$ROOT\pythonCode\modules\starhe_plugin\.venv"
$PYTHON       = "$VENV_DIR\Scripts\python.exe"
$MODULES      = "$ROOT\pythonCode\modules"
$PREPUS       = "$ROOT\third_party\prepUS"
$REQUIREMENTS = "$ROOT\pythonCode\modules\starhe_plugin\requirements.txt"

# -- 1. Find Python 3.13 on the system ----------------------------------------
# We store the executable and its arguments separately to avoid the problems
# of array splitting and splatting in PowerShell.
$PYTHON_SYS_EXE  = $null
$PYTHON_SYS_ARGS = @()

$candidates = @(
    @{ Exe = "py";         Args = @("-3.13") },
    @{ Exe = "python3.13"; Args = @() },
    @{ Exe = "python";     Args = @() }
)

foreach ($c in $candidates) {
    try {
        $ver = & $c.Exe @($c.Args) --version 2>&1
        if ($ver -match '3\.13\.\d+') {
            $PYTHON_SYS_EXE  = $c.Exe
            $PYTHON_SYS_ARGS = $c.Args
            break
        }
    } catch { }
}

if (-not $PYTHON_SYS_EXE) {
    Write-Error "Python 3.13 introuvable sur le systeme."
    Write-Host ""
    Write-Host "Installe Python 3.13 depuis : https://www.python.org/downloads/"
    Write-Host "Coche 'Add Python to PATH' lors de l installation."
    exit 1
}

$sysLabel = "$PYTHON_SYS_EXE $($PYTHON_SYS_ARGS -join ' ')".Trim()
Write-Host "Python 3.13 systeme trouve : $sysLabel"

# -- 2. Verifier que tkinter est disponible -----------------------------------
& $PYTHON_SYS_EXE @($PYTHON_SYS_ARGS) -c "import _tkinter" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "tkinter n est pas disponible dans cette installation Python 3.13."
    Write-Host "Reinstalle Python 3.13 depuis python.org (tcl/tk doit etre inclus)."
    exit 1
}

# -- 3. Create the venv if missing --------------------------------------------
if (-not (Test-Path $PYTHON)) {
    Write-Host "Venv introuvable - creation avec $sysLabel..."
    & $PYTHON_SYS_EXE @($PYTHON_SYS_ARGS) -m venv "$VENV_DIR"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de la creation du venv."
        exit 1
    }
    Write-Host "Installation des dependances (cela peut prendre quelques minutes)..."
    & $PYTHON -m pip install --upgrade pip --quiet
    & $PYTHON -m pip install -r "$REQUIREMENTS" --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de l installation des dependances."
        exit 1
    }
    Write-Host "Venv cree et dependances installees."
}

# -- 3b. Ensure pip is available in the venv ---------------------------------
& $PYTHON -m pip --version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip absent du venv - bootstrap via ensurepip..."
    & $PYTHON -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec du bootstrap pip (ensurepip)."
        exit 1
    }
    & $PYTHON -m pip install --upgrade pip --quiet
    Write-Host "Installation des dependances (cela peut prendre quelques minutes)..."
    & $PYTHON -m pip install -r "$REQUIREMENTS" --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de l installation des dependances."
        exit 1
    }
    Write-Host "pip et dependances installes avec succes."
}

# -- 3c. Install the dependencies if missing ----------------------------------
& $PYTHON -c "import numpy" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Dependances absentes - installation depuis requirements.txt..."
    & $PYTHON -m pip install -r "$REQUIREMENTS" --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de l installation des dependances."
        exit 1
    }
    Write-Host "Dependances installees avec succes."
}

# -- 4. Install prepUS if missing ---------------------------------------------
& $PYTHON -c "import prepUS" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "prepUS absent du venv - installation depuis third_party/prepUS..."
    & $PYTHON -m pip install sonocrop --no-deps --quiet
    & $PYTHON -m pip install "$PREPUS" --no-deps --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de l installation de prepUS depuis $PREPUS"
        exit 1
    }
    Write-Host "prepUS installe avec succes."
}

# -- 5. Download the AI weights if missing ------------------------------------
$MODELS_DIR = "$ROOT\pythonCode\modules\starhe_plugin\models"
$RISK_PTH   = "$MODELS_DIR\best_acc_mean_cls_f1_epoch_14.pth"
$DET_PTH    = "$MODELS_DIR\best_coco_bbox_mAP_50_iter_2100.pth"
if (-not (Test-Path $RISK_PTH) -or -not (Test-Path $DET_PTH)) {
    Write-Host "Poids IA manquants - telechargement depuis GitHub Releases..."
    & $PYTHON "$ROOT\download_models.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec du telechargement des poids IA."
        exit 1
    }
}

# -- 6. Launch the interface --------------------------------------------------
$pythonVer = & $PYTHON --version 2>&1
Write-Host "Lancement STARHE Tkinter ($pythonVer)..."
Set-Location $MODULES
& $PYTHON -m starhe_plugin.ui.prototype_tkinter
