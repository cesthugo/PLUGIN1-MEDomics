# setup.ps1 — Automatic setup of the STARHE environment (Windows)
# Usage: .\setup.ps1
#
# This script:
#   1. Checks that Python 3.13 is installed
#   2. Creates the venv if missing
#   3. Installs requirements.txt
#   4. Installs sonocrop + prepUS (third_party/)
#
# No graphical interface is launched (unlike run_tkinter.ps1).

$ErrorActionPreference = "Stop"

$ROOT         = Split-Path -Parent $PSScriptRoot
$VENV_DIR     = "$ROOT\pythonCode\modules\starhe_plugin\.venv"
$PYTHON       = "$VENV_DIR\Scripts\python.exe"
$PIP          = "$VENV_DIR\Scripts\pip.exe"
$REQUIREMENTS = "$ROOT\pythonCode\modules\starhe_plugin\requirements.txt"
$PREPUS       = "$ROOT\third_party\prepUS"

# -- 1. Find Python 3.13 ------------------------------------------------------
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

# -- 2. Create the venv if missing --------------------------------------------
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

# -- 3. Install the dependencies ----------------------------------------------
Write-Host "[..] Installation des dependances (requirements.txt) ..."
& $PIP install --upgrade pip --quiet
& $PIP install -r "$REQUIREMENTS" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "Echec de l installation des dependances."
    exit 1
}
Write-Host "[OK] Dependances installees."

# -- 4. Install mmaction2 (--no-deps) + venv patches ---------------------------
# Required by C3D_BACKEND="mmaction2" (default) for STARHE-RISK.
$ErrorActionPreference = "Continue"
& $PYTHON -c "import mmaction" 2>&1 | Out-Null
$mmactionExitCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($mmactionExitCode -ne 0) {
    Write-Host "[..] Installation de mmaction2 (sans dependances) ..."
    & $PIP install mmaction2==1.2.0 --no-deps --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Echec de l installation de mmaction2."
        exit 1
    }
    Write-Host "[OK] mmaction2 installe."
}

# Python 3.13 + mmdet compatibility patches (same patches as setup.sh)
$MMACTION_PKG = "$VENV_DIR\Lib\site-packages\mmaction"
if (Test-Path $MMACTION_PKG) {
    # 1. Removal of the DRN import missing from wheel 1.2.0
    $locInit = "$MMACTION_PKG\models\localizers\__init__.py"
    if (Test-Path $locInit) {
        $content = Get-Content $locInit -Raw
        $content = $content -replace "from \.drn\.drn import DRN\r?\n", ""
        $content = $content -replace "__all__ = \['TEM', 'PEM', 'BMN', 'TCANet', 'DRN'\]", "__all__ = ['TEM', 'PEM', 'BMN', 'TCANet']"
        Set-Content $locInit -Value $content -NoNewline
    }

    # 2. AssertionError in roi_heads (mmdet <-> mmengine registry conflict)
    # 3. Same patch for task_modules
    foreach ($rel in @("models\roi_heads\__init__.py", "models\task_modules\__init__.py")) {
        $f = "$MMACTION_PKG\$rel"
        if (Test-Path $f) {
            $content = Get-Content $f -Raw
            $content = $content -replace "except \(ImportError, ModuleNotFoundError\):", "except (ImportError, ModuleNotFoundError, AssertionError):"
            Set-Content $f -Value $content -NoNewline
        }
    }
    Write-Host "[OK] Patches mmaction2 appliques."
}

# -- 5. Install prepUS + sonocrop ---------------------------------------------
$ErrorActionPreference = "Continue"
& $PYTHON -c "import prepUS" 2>&1 | Out-Null
$prepUSExitCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($prepUSExitCode -ne 0) {
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

# -- Summary -------------------------------------------------------------------
Write-Host ""
Write-Host "========================================================="
Write-Host " Setup termine avec succes."
Write-Host " Python venv : $PYTHON"
Write-Host " Pour lancer le pipeline :"
Write-Host "   & $PYTHON -m starhe_plugin.pipeline <fichier.dcm>"
Write-Host "========================================================="
