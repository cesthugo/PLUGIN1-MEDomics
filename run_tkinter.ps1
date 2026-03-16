# run_tkinter.ps1 — Lanceur du prototype STARHE Tkinter
# Utilise directement le Python 3.13 du venv starhe_plugin,
# sans dépendre du venv actif dans le terminal courant.

$PYTHON = "$PSScriptRoot\pythonCode\modules\starhe_plugin\.venv\Scripts\python.exe"
$MODULES = "$PSScriptRoot\pythonCode\modules"

if (-not (Test-Path $PYTHON)) {
    Write-Error "Python 3.13 venv introuvable : $PYTHON"
    Write-Host "Crée d'abord le venv avec :"
    Write-Host "  py -3.13 -m venv pythonCode\modules\starhe_plugin\.venv"
    Write-Host "  pythonCode\modules\starhe_plugin\.venv\Scripts\pip install -r pythonCode\modules\starhe_plugin\requirements.txt"
    exit 1
}

Write-Host "Lancement STARHE Tkinter (Python $(&$PYTHON --version 2>&1))..."
Set-Location $MODULES
& $PYTHON -m starhe_plugin.ui.prototype_tkinter
