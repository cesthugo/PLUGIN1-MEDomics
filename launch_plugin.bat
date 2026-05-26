@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

:: launch_plugin.bat — Lanceur standalone STARHE Plugin (Windows)
::
:: Double-cliquer dans l'Explorateur pour lancer le plugin SANS MEDomics.
:: Ce script orchestre :
::   1. Verification des prerequis (Python 3.13, Node.js, Go)
::   2. Creation du venv Python si absent + installation des dependances
::   3. Compilation du binaire Go STARHE si absent
::   4. Demarrage de MongoDB sur le port 54017
::   5. Demarrage du serveur Go STARHE -> http://localhost:8082
::   6. Demarrage du serveur de developpement React -> http://localhost:5173
::   7. Ouverture automatique du navigateur
::
:: Chaque service s'ouvre dans sa propre fenetre de terminal.

:: ── Chemins ──────────────────────────────────────────────────────────────────
set "PLUGIN_DIR=%~dp0"
if "%PLUGIN_DIR:~-1%"=="\" set "PLUGIN_DIR=%PLUGIN_DIR:~0,-1%"

set "GO_SERVER_DIR=%PLUGIN_DIR%\go_server"
set "REACT_UI_DIR=%PLUGIN_DIR%\react_ui"
set "VENV_DIR=%PLUGIN_DIR%\pythonCode\modules\starhe_plugin\.venv"
set "PYTHON_VENV=%VENV_DIR%\Scripts\python.exe"
set "PREPUS_DIR=%PLUGIN_DIR%\third_party\prepUS"
set "REQUIREMENTS=%PLUGIN_DIR%\pythonCode\modules\starhe_plugin\requirements.txt"
set "MODELS_DIR=%PLUGIN_DIR%\pythonCode\modules\starhe_plugin\models"
set "DATA_DIR=%PLUGIN_DIR%\data"
set "MONGO_DBPATH=%DATA_DIR%\mongodb"
set "GOSERVER_BIN=%GO_SERVER_DIR%\go_server.exe"

:: ── Banniere ─────────────────────────────────────────────────────────────────
echo.
echo  +----------------------------------------------------+
echo  ^|   STARHE Plugin -- Lanceur standalone              ^|
echo  ^|   Go :8082  .  React :5173  .  MongoDB :54017     ^|
echo  +----------------------------------------------------+
echo.

:: ── 1. Prerequis systeme ─────────────────────────────────────────────────────
echo -- Verification des prerequis ------------------------------------

:: Python 3.13
set "PYTHON_SYS="
:: Tester "py -3.13"
py -3.13 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_SYS_CMD=py"
    set "PYTHON_SYS_ARGS=-3.13"
    for /f "tokens=*" %%V in ('py -3.13 --version 2^>nul') do echo   [OK] %%V
    goto :python_found
)
:: Tester "python3.13"
where python3.13 >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_SYS_CMD=python3.13"
    set "PYTHON_SYS_ARGS="
    for /f "tokens=*" %%V in ('python3.13 --version 2^>nul') do echo   [OK] %%V
    goto :python_found
)
:: Tester "python"
python --version 2>&1 | findstr /C:"3.13." >nul
if not errorlevel 1 (
    set "PYTHON_SYS_CMD=python"
    set "PYTHON_SYS_ARGS="
    for /f "tokens=*" %%V in ('python --version 2^>nul') do echo   [OK] %%V
    goto :python_found
)
echo [ERREUR] Python 3.13 introuvable.
echo          Installe-le depuis : https://www.python.org/downloads/
echo          Coche "Add Python to PATH" lors de l'installation.
goto :error_exit

:python_found

:: Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Node.js introuvable.
    echo          Installe-le depuis : https://nodejs.org
    goto :error_exit
)
for /f "tokens=*" %%V in ('node --version 2^>nul') do echo   [OK] Node.js %%V

:: npm
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] npm introuvable. Il devrait etre inclus avec Node.js.
    goto :error_exit
)

:: Go
where go >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Go introuvable.
    echo          Installe-le depuis : https://go.dev/dl/
    goto :error_exit
)
for /f "tokens=3" %%V in ('go version 2^>nul') do echo   [OK] Go %%V

echo.

:: ── 2. Environnement Python ───────────────────────────────────────────────────
echo -- Environnement Python ------------------------------------------

if not exist "%PYTHON_VENV%" (
    echo   Creation du venv Python 3.13...
    if defined PYTHON_SYS_ARGS (
        %PYTHON_SYS_CMD% %PYTHON_SYS_ARGS% -m venv "%VENV_DIR%"
    ) else (
        %PYTHON_SYS_CMD% -m venv "%VENV_DIR%"
    )
    if errorlevel 1 (
        echo [ERREUR] Creation du venv echouee.
        goto :error_exit
    )
    echo   Installation des dependances ^(premiere fois, quelques minutes^)...
    "%PYTHON_VENV%" -m pip install --upgrade pip --quiet
    "%PYTHON_VENV%" -m pip install -r "%REQUIREMENTS%" --quiet
    if errorlevel 1 (
        echo [ERREUR] pip install requirements.txt echoue.
        goto :error_exit
    )
    echo   [OK] Venv cree et dependances installees.
) else (
    echo   [OK] Venv present.
)

:: prepUS
"%PYTHON_VENV%" -c "import prepUS" >nul 2>&1
if errorlevel 1 (
    echo   Installation de prepUS...
    "%PYTHON_VENV%" -m pip install sonocrop --no-deps --quiet
    "%PYTHON_VENV%" -m pip install "%PREPUS_DIR%" --no-deps --quiet
    if errorlevel 1 ( echo [ERREUR] Installation de prepUS echouee. & goto :error_exit )
    echo   [OK] prepUS installe.
)

:: Poids IA
if not exist "%MODELS_DIR%\best_acc_mean_cls_f1_epoch_14.pth" (
    echo   Telechargement des poids IA...
    "%PYTHON_VENV%" "%PLUGIN_DIR%\download_models.py"
    if errorlevel 1 ( echo [ERREUR] Telechargement des poids IA echoue. & goto :error_exit )
    echo   [OK] Poids IA presents.
)

echo.

:: ── 3. Binaire Go STARHE ─────────────────────────────────────────────────────
echo -- Serveur Go STARHE ---------------------------------------------

if not exist "%GOSERVER_BIN%" (
    echo   Compilation du binaire Go ^(premiere fois^)...
    pushd "%GO_SERVER_DIR%"
    go build -o go_server.exe .
    if errorlevel 1 (
        popd
        echo [ERREUR] Compilation du serveur Go echouee.
        goto :error_exit
    )
    popd
    echo   [OK] Binaire compile : %GOSERVER_BIN%
) else (
    echo   [OK] Binaire present.
)

echo.

:: ── 4. MongoDB (port 54017) ───────────────────────────────────────────────────
echo -- MongoDB ^(port 54017^) -----------------------------------------

:: Verifier si MongoDB est deja en ecoute sur 54017
netstat -an 2>nul | findstr ":54017.*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo   [OK] MongoDB deja actif sur le port 54017.
) else (
    :: Chercher mongod dans les emplacements connus
    set "MONGOD_PATH="
    where mongod >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=*" %%P in ('where mongod 2^>nul') do (
            if not defined MONGOD_PATH set "MONGOD_PATH=%%P"
        )
    )
    :: Chercher dans le chemin d'installation standard de MongoDB
    if not defined MONGOD_PATH (
        for /d %%D in ("%PROGRAMFILES%\MongoDB\Server\*") do (
            if exist "%%D\bin\mongod.exe" (
                if not defined MONGOD_PATH set "MONGOD_PATH=%%D\bin\mongod.exe"
            )
        )
    )

    if defined MONGOD_PATH (
        if not exist "%MONGO_DBPATH%" mkdir "%MONGO_DBPATH%"
        echo   Demarrage de MongoDB (%MONGOD_PATH%)...
        start "MongoDB STARHE" "%MONGOD_PATH%" --port 54017 --dbpath "%MONGO_DBPATH%"
        echo   [OK] MongoDB demarre dans une nouvelle fenetre.
        timeout /t 3 /nobreak >nul
    ) else (
        echo   [AVERTISSEMENT] mongod introuvable.
        echo   Les resultats ne seront pas persistes.
        echo   Lance MEDomics d'abord ou installe MongoDB Community :
        echo   https://www.mongodb.com/try/download/community
    )
)

echo.

:: ── 5. Dependances React UI ───────────────────────────────────────────────────
echo -- UI React STARHE -----------------------------------------------

if not exist "%REACT_UI_DIR%\node_modules" (
    echo   Installation des dependances React UI ^(premiere fois^)...
    pushd "%REACT_UI_DIR%"
    npm ci
    if errorlevel 1 ( popd & echo [ERREUR] npm ci echoue. & goto :error_exit )
    popd
    echo   [OK] Dependances installees.
) else (
    echo   [OK] node_modules present.
)

echo.

:: ── 6. Demarrage des services ─────────────────────────────────────────────────
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

echo -- Lancement des services ----------------------------------------

echo   Serveur Go STARHE  -^> http://localhost:8082
start "STARHE Go Server" /D "%GO_SERVER_DIR%" "%GOSERVER_BIN%"

echo   UI React STARHE    -^> http://localhost:5173
start "STARHE React UI" cmd /k "cd /d "%REACT_UI_DIR%" && npm run dev"

echo.
echo   Attente du demarrage de l'interface React ^(jusqu'a 40s^)...
set /a WAIT_COUNT=0
:wait_loop
    timeout /t 1 /nobreak >nul
    set /a WAIT_COUNT+=1
    curl -s http://localhost:5173 >nul 2>&1
    if not errorlevel 1 goto :react_ready
    if %WAIT_COUNT% geq 40 goto :react_ready
goto :wait_loop
:react_ready

:: ── 7. Ouvrir le navigateur ───────────────────────────────────────────────────
echo   Ouverture du navigateur -^> http://localhost:5173
start "" "http://localhost:5173"

echo.
echo  +----------------------------------------------------+
echo  ^|  STARHE Plugin en cours d'execution.               ^|
echo  ^|                                                    ^|
echo  ^|  Services actifs dans leurs propres fenetres :    ^|
echo  ^|    "STARHE Go Server"   (port 8082)               ^|
echo  ^|    "STARHE React UI"    (port 5173)               ^|
echo  ^|    "MongoDB STARHE"     (port 54017)              ^|
echo  ^|                                                    ^|
echo  ^|  Ferme ces fenetres pour arreter les services.    ^|
echo  +----------------------------------------------------+
echo.
pause
goto :end

:error_exit
echo.
echo Appuie sur une touche pour fermer cette fenetre...
pause >nul
exit /b 1

:end
exit /b 0
