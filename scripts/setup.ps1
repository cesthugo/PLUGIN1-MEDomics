# setup.ps1 — Installation automatique de l'environnement STARHE (Windows)
# Usage : .\setup.ps1
#
# Ce script :
#   1. Verifie que Python 3.13 est installe
#   2. Cree le venv si absent
#   3. Installe requirements.txt
#   4. Installe sonocrop + prepUS (third_party/)
#
# Aucune interface graphique n'est lancee (contrairement a run_tkinter.ps1).

$ErrorActionPreference = "Stop"

$ROOT         = Split-Path -Parent $PSScriptRoot
$VENV_DIR     = "$ROOT\pythonCode\modules\starhe_plugin\.venv"
$PYTHON       = "$VENV_DIR\Scripts\python.exe"
$PIP          = "$VENV_DIR\Scripts\pip.exe"
$REQUIREMENTS = "$ROOT\pythonCode\modules\starhe_plugin\requirements.txt"
$PREPUS       = "$ROOT\third_party\prepUS"

# -- 1. Trouver Python 3.13 ---------------------------------------------------
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
Write-Host "[OK] Python systeme : $sysLabel"

# -- 2. Creer le venv si absent -----------------------------------------------
if (-not (Test-Path $PYTHON)) {
    Write-Host "[..] Creation du venv dans $VENV_DIR ..."
    & $PYTHON_SYS_EXE @($PYTHON_SYS_ARGS) -m venv "$VENV_DIR"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de la creation du venv."
        exit 1
    }
    Write-Host "[OK] Venv cree."
} else {
    Write-Host "[OK] Venv existant : $VENV_DIR"
}

# -- 3. Installer les dependances ---------------------------------------------
Write-Host "[..] Installation des dependances (requirements.txt) ..."
& $PIP install --upgrade pip --quiet
& $PIP install -r "$REQUIREMENTS" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "Echec de l installation des dependances."
    exit 1
}
Write-Host "[OK] Dependances installees."

# -- 4. Installer prepUS + sonocrop -------------------------------------------
& $PYTHON -c "import prepUS" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[..] Installation de sonocrop + prepUS ..."
    & $PIP install sonocrop --no-deps --quiet
    & $PIP install "$PREPUS" --no-deps --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de l installation de prepUS."
        exit 1
    }
    Write-Host "[OK] prepUS installe."
} else {
    Write-Host "[OK] prepUS deja present."
}

# -- Resume --------------------------------------------------------------------
Write-Host ""
Write-Host "========================================================="
Write-Host " Setup termine avec succes."
Write-Host " Python venv : $PYTHON"
Write-Host " Pour lancer le pipeline :"
Write-Host "   & $PYTHON -m starhe_plugin.pipeline <fichier.dcm>"
Write-Host "========================================================="
