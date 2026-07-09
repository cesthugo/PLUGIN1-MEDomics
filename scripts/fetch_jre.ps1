# fetch_jre.ps1 — Downloads a Temurin 17 JRE for Windows x64
# from the Adoptium API.
#
# Usage:
#   .\scripts\fetch_jre.ps1                # win-x64 (default)
#   .\scripts\fetch_jre.ps1 -Platform win-x64
#
# Output: renderer\build-resources\jre-win-x64\  (contains bin\java.exe)
# package.json convention: extraResources copies this directory to "jre\" in
# resources\jre\bin\java.exe of the NSIS installer.

param(
    [string]$Platform = "win-x64",
    [string]$JreVersion = "17"
)

$ErrorActionPreference = "Stop"

$Root    = Split-Path -Parent $PSScriptRoot
$OutRoot = Join-Path $Root "renderer\build-resources"

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

    # Adoptium ships `jdk-17.x.x+x-jre\` at the root of the Windows zip
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
