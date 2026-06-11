# fetch_jre.ps1 — Télécharge une JRE Temurin 17 pour Windows x64
# depuis l'API Adoptium.
#
# Usage :
#   .\scripts\fetch_jre.ps1                # win-x64 (défaut)
#   .\scripts\fetch_jre.ps1 -Platform win-x64
#
# Sortie : react_ui\build-resources\jre-win-x64\  (contient bin\java.exe)
# Convention package.json : extraResources copie ce dossier vers "jre\" dans
# resources\jre\bin\java.exe de l'installeur NSIS.

param(
    [string]$Platform = "win-x64",
    [string]$JreVersion = "17"
)

$ErrorActionPreference = "Stop"

$Root    = Split-Path -Parent $PSScriptRoot
$OutRoot = Join-Path $Root "react_ui\build-resources"

switch ($Platform) {
    "win-x64"     { $AdoOs = "windows"; $AdoArch = "x64" }
    "win-aarch64" { $AdoOs = "windows"; $AdoArch = "aarch64" }
    default {
        Write-Error "Plateforme non supportée : $Platform (utilisez fetch_jre.sh sous Unix)"
        exit 1
    }
}

$OutDir = Join-Path $OutRoot "jre-$Platform"

# Idempotence
if (Test-Path (Join-Path $OutDir "bin\java.exe")) {
    Write-Host "[fetch_jre] JRE déjà présente : $OutDir"
    & (Join-Path $OutDir "bin\java.exe") -version
    exit 0
}

$Url = "https://api.adoptium.net/v3/binary/latest/$JreVersion/ga/$AdoOs/$AdoArch/jre/hotspot/normal/eclipse?project=jdk"
$TmpZip = Join-Path $env:TEMP "jre-temurin-$([System.Guid]::NewGuid().ToString()).zip"

Write-Host "[fetch_jre] Téléchargement Temurin $JreVersion pour ${Platform}…"
Write-Host "[fetch_jre]   URL : $Url"
Invoke-WebRequest -Uri $Url -OutFile $TmpZip -UseBasicParsing

# Extraction
$TmpExtract = Join-Path $env:TEMP "jre-extract-$([System.Guid]::NewGuid().ToString())"
New-Item -ItemType Directory -Force -Path $TmpExtract | Out-Null
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

try {
    Expand-Archive -Path $TmpZip -DestinationPath $TmpExtract -Force

    # Adoptium livre `jdk-17.x.x+x-jre\` à la racine du zip Windows
    $Inner = Get-ChildItem -Path $TmpExtract -Directory | Select-Object -First 1
    if (-not $Inner) {
        throw "Extraction vide"
    }
    Copy-Item -Path (Join-Path $Inner.FullName "*") -Destination $OutDir -Recurse -Force

    if (-not (Test-Path (Join-Path $OutDir "bin\java.exe"))) {
        throw "$OutDir\bin\java.exe introuvable après extraction"
    }

    Write-Host "[fetch_jre] OK : $OutDir"
    & (Join-Path $OutDir "bin\java.exe") -version
    $SizeMb = [math]::Round((Get-ChildItem -Path $OutDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    Write-Host "[fetch_jre] Taille : $SizeMb MB"
}
finally {
    Remove-Item -Force -Path $TmpZip -ErrorAction SilentlyContinue
    Remove-Item -Force -Recurse -Path $TmpExtract -ErrorAction SilentlyContinue
}
