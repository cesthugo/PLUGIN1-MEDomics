# medomics_register.ps1 — Enregistre le plugin STARHE dans MEDomics (Windows)
#
# Crée %APPDATA%\MEDomics\plugins\starhe\plugin.json
# MEDomics détectera automatiquement le plugin au prochain démarrage.
$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Manifest   = Join-Path $ScriptDir "..\medomics_integration\plugin.json"

if (-not (Test-Path $Manifest)) {
    Write-Error "Manifest introuvable : $Manifest"
    exit 1
}

$PluginsDir = Join-Path $env:APPDATA "MEDomics\plugins\starhe"
New-Item -ItemType Directory -Force -Path $PluginsDir | Out-Null
Copy-Item $Manifest -Destination "$PluginsDir\plugin.json" -Force
Write-Host "STARHE enregistré : $PluginsDir\plugin.json"
