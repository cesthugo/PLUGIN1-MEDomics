# run_tkinter.ps1 - Lanceur autonome du prototype STARHE Tkinter (Windows)
# Script autonome : detecte Python 3.13, cree le venv si absent,
# installe les dependances et prepUS, puis lance l interface.
# Aucune configuration manuelle requise apres avoir installe Python 3.13.

$VENV_DIR     = "$PSScriptRoot\pythonCode\modules\starhe_plugin\.venv"
$PYTHON       = "$VENV_DIR\Scripts\python.exe"
$PIP          = "$VENV_DIR\Scripts\pip.exe"
$MODULES      = "$PSScriptRoot\pythonCode\modules"
$PREPUS       = "$PSScriptRoot\third_party\prepUS"
$REQUIREMENTS = "$PSScriptRoot\pythonCode\modules\starhe_plugin\requirements.txt"

# -- 1. Trouver Python 3.13 sur le systeme ------------------------------------
# On stocke l executable et ses arguments separement pour eviter les problemes
# de decoupage de tableau et de splatting dans PowerShell.
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

# -- 3. Creer le venv si absent -----------------------------------------------
if (-not (Test-Path $PYTHON)) {
    Write-Host "Venv introuvable - creation avec $sysLabel..."
    & $PYTHON_SYS_EXE @($PYTHON_SYS_ARGS) -m venv "$VENV_DIR"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de la creation du venv."
        exit 1
    }
    Write-Host "Installation des dependances (cela peut prendre quelques minutes)..."
    & $PIP install --upgrade pip --quiet
    & $PIP install -r "$REQUIREMENTS" --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de l installation des dependances."
        exit 1
    }
    Write-Host "Venv cree et dependances installees."
}

# -- 4. Installer prepUS si absent --------------------------------------------
& $PYTHON -c "import prepUS" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "prepUS absent du venv - installation depuis third_party/prepUS..."
    & $PIP install sonocrop --no-deps --quiet
    & $PIP install "$PREPUS" --no-deps --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de l installation de prepUS depuis $PREPUS"
        exit 1
    }
    Write-Host "prepUS installe avec succes."
}

# -- 5. Lancer l interface ----------------------------------------------------
$pythonVer = & $PYTHON --version 2>&1
Write-Host "Lancement STARHE Tkinter ($pythonVer)..."
Set-Location $MODULES
& $PYTHON -m starhe_plugin.ui.prototype_tkinter
