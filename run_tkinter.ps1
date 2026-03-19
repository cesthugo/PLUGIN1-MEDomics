# run_tkinter.ps1 — Lanceur du prototype STARHE Tkinter
# Utilise directement le Python 3.13 du venv starhe_plugin,
# sans dépendre du venv actif dans le terminal courant.
#
# prepUS est vendorisé dans third_party/prepUS/ et installé automatiquement
# si absent du venv — aucune dépendance externe à un chemin local sur la machine.

$PYTHON   = "$PSScriptRoot\pythonCode\modules\starhe_plugin\.venv\Scripts\python.exe"
$PIP      = "$PSScriptRoot\pythonCode\modules\starhe_plugin\.venv\Scripts\pip.exe"
$MODULES  = "$PSScriptRoot\pythonCode\modules"
$PREPUS   = "$PSScriptRoot\third_party\prepUS"

if (-not (Test-Path $PYTHON)) {
    Write-Error "Python 3.13 venv introuvable : $PYTHON"
    Write-Host "Crée d'abord le venv avec :"
    Write-Host "  py -3.13 -m venv pythonCode\modules\starhe_plugin\.venv"
    Write-Host "  pythonCode\modules\starhe_plugin\.venv\Scripts\pip install -r pythonCode\modules\starhe_plugin\requirements.txt"
    exit 1
}

# ── Vérification / installation automatique de prepUS ────────────────────────
$prepusInstalled = & $PYTHON -c "import prepUS" 2>&1
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

Write-Host "Lancement STARHE Tkinter (Python $(&$PYTHON --version 2>&1))..."
Set-Location $MODULES
& $PYTHON -m starhe_plugin.ui.prototype_tkinter
