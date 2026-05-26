@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

:: launch_medomics.bat — Lanceur MEDomics + STARHE (Windows)
::
:: Double-cliquer sur ce fichier dans l'Explorateur pour lancer l'application.
:: Une fenêtre de commande s'ouvre, vérifie les prérequis, puis démarre MEDomics.
::
:: Ce que ce script orchestre :
::   1. Vérifie Node.js, npm et Go
::   2. Compile le binaire Go STARHE si absent (go_server\go_server.exe)
::   3. Installe les dépendances npm MEDomics si absentes
::   4. Construit l'UI React STARHE et la déploie dans MEDomics si dist absent
::   5. Lance `npm run dev` dans MEDomics → nextron démarre Electron, qui lance
::      automatiquement MongoDB, le serveur Go MEDomics et le serveur Go STARHE

:: ── Résolution des chemins ──────────────────────────────────────────────────
set "PLUGIN_DIR=%~dp0"
if "%PLUGIN_DIR:~-1%"=="\" set "PLUGIN_DIR=%PLUGIN_DIR:~0,-1%"

set "MEDOMICS_DIR=%PLUGIN_DIR%\..\MEDomics"
set "GO_SERVER_DIR=%PLUGIN_DIR%\go_server"
set "REACT_UI_DIR=%PLUGIN_DIR%\react_ui"

:: Résoudre le chemin absolu de MEDOMICS_DIR
pushd "%MEDOMICS_DIR%" 2>nul
if errorlevel 1 (
    echo.
    echo [ERREUR] Repertoire MEDomics introuvable : %MEDOMICS_DIR%
    echo          Verifie que PLUGIN1-MEDomics et MEDomics sont dans le meme dossier parent.
    goto :error_exit
)
set "MEDOMICS_DIR=%CD%"
popd

:: ── Bannière ────────────────────────────────────────────────────────────────
echo.
echo  +--------------------------------------------------+
echo  ^|   MEDomics + STARHE -- Lanceur de developpement  ^|
echo  +--------------------------------------------------+
echo.

:: ── 1. Vérification des prérequis ───────────────────────────────────────────
echo -- Verification des prerequis ---------------------------------

:: Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Node.js introuvable.
    echo          Installe-le depuis https://nodejs.org (LTS recommande^).
    goto :error_exit
)
for /f "tokens=*" %%V in ('node --version 2^>nul') do echo   [OK] Node.js %%V

:: npm
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] npm introuvable. Il devrait etre inclus avec Node.js.
    goto :error_exit
)
for /f "tokens=*" %%V in ('npm --version 2^>nul') do echo   [OK] npm %%V

:: Go
where go >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Go introuvable.
    echo          Installe-le depuis https://go.dev/dl/ puis relance ce script.
    goto :error_exit
)
for /f "tokens=3" %%V in ('go version 2^>nul') do echo   [OK] Go %%V

:: Répertoire go_server
if not exist "%GO_SERVER_DIR%" (
    echo [ERREUR] Repertoire go_server introuvable : %GO_SERVER_DIR%
    goto :error_exit
)

echo   [OK] MEDomics : %MEDOMICS_DIR%
echo.

:: ── 2. Compiler le binaire Go STARHE si absent ──────────────────────────────
echo -- Serveur Go STARHE ------------------------------------------
set "GOSERVER_BIN=%GO_SERVER_DIR%\go_server.exe"

if not exist "%GOSERVER_BIN%" (
    echo   Compilation du binaire ^(premiere fois^)...
    pushd "%GO_SERVER_DIR%"
    go build -o go_server.exe .
    if errorlevel 1 (
        popd
        echo [ERREUR] La compilation du serveur Go STARHE a echoue.
        echo          Verifie que Go est correctement installe.
        goto :error_exit
    )
    popd
    echo   [OK] Binaire compile : %GOSERVER_BIN%
) else (
    echo   [OK] Binaire present : %GOSERVER_BIN%
)
echo.

:: ── 3. Dépendances npm MEDomics ─────────────────────────────────────────────
echo -- Dependances Node.js MEDomics --------------------------------

if not exist "%MEDOMICS_DIR%\node_modules" (
    echo   Installation des dependances ^(premiere fois, quelques minutes^)...
    pushd "%MEDOMICS_DIR%"
    npm install
    if errorlevel 1 (
        popd
        echo [ERREUR] npm install a echoue dans %MEDOMICS_DIR%
        goto :error_exit
    )
    popd
    echo   [OK] Dependances installees.
) else (
    echo   [OK] node_modules present.
)
echo.

:: ── 4. UI React STARHE — construire et déployer si dist absent ───────────────
echo -- UI React STARHE --------------------------------------------

set "REACT_DIST=%REACT_UI_DIR%\dist"
set "MEDOMICS_STARHE_APP=%MEDOMICS_DIR%\app\starhe-ui"
set "MEDOMICS_STARHE_RENDERER=%MEDOMICS_DIR%\renderer\public\starhe-ui"

if not exist "%REACT_DIST%" (
    echo   Construction du bundle React STARHE ^(dist\ absent^)...

    if not exist "%REACT_UI_DIR%\node_modules" (
        echo   Installation des dependances React UI...
        pushd "%REACT_UI_DIR%"
        npm ci
        if errorlevel 1 ( popd & echo [ERREUR] npm ci a echoue. & goto :error_exit )
        popd
    )

    pushd "%REACT_UI_DIR%"
    npm run build
    if errorlevel 1 ( popd & echo [ERREUR] npm run build a echoue. & goto :error_exit )
    popd

    if not exist "%MEDOMICS_STARHE_APP%"      mkdir "%MEDOMICS_STARHE_APP%"
    if not exist "%MEDOMICS_STARHE_RENDERER%"  mkdir "%MEDOMICS_STARHE_RENDERER%"
    xcopy /E /Y /I /Q "%REACT_DIST%" "%MEDOMICS_STARHE_APP%"      >nul
    xcopy /E /Y /I /Q "%REACT_DIST%" "%MEDOMICS_STARHE_RENDERER%"  >nul
    echo   [OK] UI React construite et deployee dans MEDomics.
) else (
    echo   [OK] dist\ present -- UI deja construite.
)
echo.

:: ── 5. Lancer MEDomics ──────────────────────────────────────────────────────
echo -- Lancement --------------------------------------------------
echo   Demarrage de MEDomics ^(npm run dev^)...
echo   Electron lance : MongoDB + serveur Go MEDomics + serveur Go STARHE
echo.
echo   Pour arreter l'application, ferme la fenetre MEDomics.
echo   Ce terminal restera ouvert jusqu'a la fermeture de l'app.
echo.

pushd "%MEDOMICS_DIR%"
npm run dev
popd

echo.
echo MEDomics s'est arrete.
goto :end

:error_exit
echo.
echo Appuie sur une touche pour fermer cette fenetre...
pause >nul
exit /b 1

:end
echo Appuie sur une touche pour fermer cette fenetre...
pause >nul
exit /b 0
