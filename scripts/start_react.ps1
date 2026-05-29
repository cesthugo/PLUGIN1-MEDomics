# start_react.ps1 — lance le serveur Go STARHE puis l'UI React/Vite.
#
# Usage :
#   .\start_react.ps1
#
# Logs :
#   logs\go_server.log
#   logs\react_ui.log
#   logs\starhe_dev.log


$ErrorActionPreference = "Stop"


$RootDir  = Split-Path -Parent $PSScriptRoot
$LogDir   = Join-Path $RootDir "logs"
$GoLog    = Join-Path $LogDir "go_server.log"
$GoErrLog = Join-Path $LogDir "go_server.err.log"
$ReactLog = Join-Path $LogDir "react_ui.log"
$ReactErrLog = Join-Path $LogDir "react_ui.err.log"
$MainLog  = Join-Path $LogDir "starhe_dev.log"


New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Content -Path $GoLog -Value ""
Set-Content -Path $GoErrLog -Value ""
Set-Content -Path $ReactLog -Value ""
Set-Content -Path $ReactErrLog -Value ""
Set-Content -Path $MainLog -Value ""


function Write-DevLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $MainLog -Value $line
}


function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-DevLog "ERREUR: $Name est introuvable dans le PATH."
        exit 1
    }
}


Require-Command "go"


# Sur Windows, npm est un script .ps1 / .cmd — on cherche npm.cmd en priorité
$_NpmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
$NpmExe  = if ($_NpmCmd) { $_NpmCmd.Source } else { $null }
if (-not $NpmExe) {
    $_NpmFallback = Get-Command npm -ErrorAction SilentlyContinue
    $NpmExe = if ($_NpmFallback) { $_NpmFallback.Source } else { $null }
}
if (-not $NpmExe) {
    # Fallback : emplacement standard Node.js sur Windows
    $candidates = @(
        "C:\Program Files\nodejs\npm.cmd",
        "C:\Program Files (x86)\nodejs\npm.cmd",
        (Join-Path $env:APPDATA "npm\npm.cmd")
    )
    $NpmExe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $NpmExe) {
    Write-DevLog "ERREUR: npm est introuvable. Installez Node.js et relancez depuis un nouveau terminal."
    exit 1
}
Write-DevLog "npm trouvé : $NpmExe"


# ── Vérification venv Python ──────────────────────────────────────────────────
$VenvPython = Join-Path $RootDir "pythonCode\modules\starhe_plugin\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-DevLog "Venv Python introuvable — lancement du setup..."
    & "$RootDir\scripts\setup.ps1"
    if (-not (Test-Path $VenvPython)) {
        Write-DevLog "ERREUR: setup.ps1 n'a pas créé le venv. Consulte les logs."
        exit 1
    }
    Write-DevLog "Venv Python prêt."
}


# ── Choix du port Go ─────────────────────────────────────────────────────────
# Si STARHE_PORT est déjà défini dans l'environnement, on le respecte.
# Sinon on part de 8082 et on cherche le premier port libre.
function Find-FreePort {
    param([int]$StartPort = 8082)
    $port = $StartPort
    while ($true) {
        try {
            $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
            $l.Start(); $l.Stop()
            return $port
        } catch {
            $port++
        }
    }
}


if (-not $env:STARHE_PORT) {
    $env:STARHE_PORT = (Find-FreePort 8082).ToString()
}
Write-DevLog "Port Go : $env:STARHE_PORT"


$GoProcess = $null
$ReactProcess = $null


try {
    $goAlreadyReady = $false
    try {
        Invoke-WebRequest -Uri "http://localhost:$env:STARHE_PORT/health" -UseBasicParsing -TimeoutSec 1 | Out-Null
        $goAlreadyReady = $true
    } catch { }


    if ($goAlreadyReady) {
        Write-DevLog "Serveur Go déjà disponible sur http://localhost:$env:STARHE_PORT, réutilisation du processus existant."
    } else {
        Write-DevLog "Compilation du serveur Go..."
        Push-Location (Join-Path $RootDir "go_server")
        & go build -o go_server.exe .
        if ($LASTEXITCODE -ne 0) {
            throw "Echec de la compilation Go. Consulte $GoLog"
        }


        Write-DevLog "Lancement du serveur Go..."
        $env:PORT = $env:STARHE_PORT
        $GoProcess = Start-Process -FilePath ".\go_server.exe" `
            -WorkingDirectory (Join-Path $RootDir "go_server") `
            -RedirectStandardOutput $GoLog `
            -RedirectStandardError $GoErrLog `
            -PassThru `
            -NoNewWindow
        Pop-Location
        Write-DevLog "Serveur Go démarré avec PID $($GoProcess.Id). Logs: $GoLog / $GoErrLog"
    }


    Write-DevLog "Attente du healthcheck Go sur http://localhost:$env:STARHE_PORT/health..."
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        if ($null -ne $GoProcess -and $GoProcess.HasExited) {
            throw "Le serveur Go s'est arrêté. Consulte $GoLog"
        }
        try {
            Invoke-WebRequest -Uri "http://localhost:$env:STARHE_PORT/health" -UseBasicParsing -TimeoutSec 1 | Out-Null
            $ready = $true
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if ($ready) {
        Write-DevLog "Serveur Go prêt."
    } else {
        Write-DevLog "Healthcheck non confirmé après 30s, lancement de React quand même."
    }

    $NodeModules = Join-Path $RootDir "react_ui\node_modules"
    if (-not (Test-Path $NodeModules)) {
        Write-DevLog "Dépendances React absentes: exécution de npm ci..."
        Push-Location (Join-Path $RootDir "react_ui")
        & $NpmExe ci *> $ReactLog
        Pop-Location
    }

    Write-DevLog "Lancement de React/Vite sur http://localhost:5173..."
    $ReactProcess = Start-Process -FilePath $NpmExe `
        -ArgumentList "run", "dev" `
        -WorkingDirectory (Join-Path $RootDir "react_ui") `
        -RedirectStandardOutput $ReactLog `
        -RedirectStandardError $ReactErrLog `
        -PassThru `
        -NoNewWindow
    Write-DevLog "React démarré avec PID $($ReactProcess.Id). Logs: $ReactLog / $ReactErrLog"
    Write-DevLog "Prêt. Ouvre http://localhost:5173 (si le port est occupé, consulte $ReactLog pour le port choisi par Vite)."
    Write-DevLog "Ferme cette fenêtre ou fais Ctrl+C pour arrêter Go + React."

    Wait-Process -Id $ReactProcess.Id
}
finally {
    Write-DevLog "Arrêt des processus..."
    if ($ReactProcess -and -not $ReactProcess.HasExited) {
        Stop-Process -Id $ReactProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($GoProcess -and -not $GoProcess.HasExited) {
        Stop-Process -Id $GoProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
