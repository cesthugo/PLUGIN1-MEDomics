/**
 * electron/main.ts — Processus principal Electron pour le plugin STARHE
 *
 * Responsabilités :
 *   1. Créer la BrowserWindow et charger le renderer React
 *   2. Démarrer le serveur Go (go_server) en sous-processus
 *   3. Exposer le dialogue natif d'ouverture de fichiers DICOM via IPC
 *   4. Arrêter proprement le serveur Go à la fermeture de l'app
 *
 * Sécurité :
 *   - contextIsolation: true  — le renderer n'a pas accès direct à Node.js
 *   - nodeIntegration: false  — pas d'API Node dans le renderer
 *   - Seul le preload expose une API strictement définie via contextBridge
 */

import { app, BrowserWindow, ipcMain, dialog, net } from 'electron';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs   from 'fs';
import { ensureModelsDownloaded, getWeightsDir, modelsReady } from './download-models';

const isDev = !app.isPackaged;

// Port + URL du serveur Go — alignés avec go_server/config.go (PORT env)
const GO_PORT = process.env.STARHE_PORT ?? '8082';
const GO_BASE_URL = `http://localhost:${GO_PORT}`;

// ── Serveur Go ────────────────────────────────────────────────────────────────

let goServer: ChildProcess | null = null;
/** true dès que l'app commence à se fermer — inhibe les redémarrages */
let appQuitting = false;

// Délais de backoff exponentiel entre les redémarrages (ms)
const RESTART_DELAYS = [1_000, 2_000, 5_000, 10_000, 30_000];
let restartAttempt = 0;
let restartTimer: ReturnType<typeof setTimeout> | null = null;

/** Retourne le chemin vers le binaire go_server selon l'environnement et la plateforme. */
function getGoServerBin(): string {
  if (isDev) {
    // En développement : auto-détection OS + arch → build-resources/go-server/
    // __dirname = renderer/electron-dist/  →  ../build-resources/go-server/
    const os   = process.platform === 'win32' ? 'win'
               : process.platform === 'darwin' ? 'mac'
               : 'linux';
    const arch = process.arch === 'arm64' ? 'arm64' : 'x64';
    const ext  = process.platform === 'win32' ? '.exe' : '';
    return path.join(__dirname, '..', 'build-resources', 'go-server',
                     `go-server-${os}-${arch}${ext}`);
  }
  // En production : binaire copié dans les ressources packagées par electron-builder
  const ext = process.platform === 'win32' ? '.exe' : '';
  return path.join(process.resourcesPath, 'go_server', `go_server${ext}`);
}

/** Ping GET /health — résout au premier 200, rejette après `timeoutMs`. */
function waitForGoHealthy(timeoutMs = 30_000, intervalMs = 300): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const tryOnce = (): void => {
      const req = net.request(`${GO_BASE_URL}/health`);
      req.on('response', (res) => {
        if (res.statusCode === 200) return resolve();
        scheduleRetry();
      });
      req.on('error', scheduleRetry);
      req.end();
    };
    const scheduleRetry = (): void => {
      if (Date.now() > deadline) {
        return reject(new Error(`Go server n'a pas répondu sur ${GO_BASE_URL}/health en ${timeoutMs} ms`));
      }
      setTimeout(tryOnce, intervalMs);
    };
    tryOnce();
  });
}

function startGoServer(): void {
  if (appQuitting) return;

  const bin = getGoServerBin();

  if (!fs.existsSync(bin)) {
    console.warn(`[STARHE] Binaire Go introuvable : ${bin}`);
    console.warn('[STARHE] Compilez-le d\'abord :  cd go_server && make cross-compile');
    return;
  }

  goServer = spawn(bin, [], {
    stdio: 'inherit',
    env: {
      ...process.env,
      PORT: GO_PORT,
      // Pointe le bridge weasis vers la copie bundlée (extraResources).
      // Ignoré si non-packagé : weasis_bridge.py recalcule depuis PROJECT_ROOT.
      ...(isDev ? {} : { STARHE_WEASIS_DIR: path.join(process.resourcesPath, 'weasis-dcm2png') }),
      // Pointe le bridge weasis vers la JRE Temurin embarquée (Phase 3).
      // En dev : utilise le `java` du PATH (brew install openjdk@17).
      ...(isDev
        ? {}
        : {
            STARHE_JAVA_BIN: path.join(
              process.resourcesPath,
              'jre',
              'bin',
              process.platform === 'win32' ? 'java.exe' : 'java',
            ),
          }),
      // Pointe Go vers le worker Python bundlé (PyInstaller --onedir).
      // Si non défini, Go retombe sur le venv local (mode dev).
      ...(isDev
        ? {}
        : {
            STARHE_WORKER_BIN: path.join(
              process.resourcesPath,
              'starhe_worker',
              process.platform === 'win32' ? 'starhe_worker.exe' : 'starhe_worker',
            ),
          }),
      // Pointe le pipeline Python vers le dossier où les `.pth` ont été
      // téléchargés au 1er lancement (Phase 4). En dev : non défini → utilise
      // pythonCode/modules/starhe_plugin/models/ (.pth versionnés en local).
      ...(isDev ? {} : { STARHE_WEIGHTS_DIR: getWeightsDir() }),
    },
  });

  console.log(`[STARHE] Serveur Go démarré (pid ${goServer.pid}, tentative ${restartAttempt + 1})`);

  goServer.on('error', (err) =>
    console.error('[STARHE] Erreur démarrage serveur Go :', err.message),
  );

  goServer.on('exit', (code, signal) => {
    goServer = null;

    // Arrêt volontaire (SIGTERM/SIGINT depuis before-quit) → ne pas redémarrer
    if (appQuitting || signal === 'SIGTERM' || signal === 'SIGINT') return;

    // Crash ou arrêt inattendu → redémarrage automatique avec backoff
    const delay = RESTART_DELAYS[Math.min(restartAttempt, RESTART_DELAYS.length - 1)];
    restartAttempt += 1;
    console.warn(
      `[STARHE] Serveur Go arrêté (code=${code}, signal=${signal}).` +
      ` Redémarrage dans ${delay / 1000} s… (tentative ${restartAttempt})`,
    );

    restartTimer = setTimeout(() => {
      restartTimer = null;
      startGoServer();
    }, delay);
  });

  // Redémarrage réussi : remettre le compteur à zéro après 30 s de stabilité
  setTimeout(() => {
    if (goServer && !appQuitting) restartAttempt = 0;
  }, 30_000);
}

// ── Fenêtre principale ────────────────────────────────────────────────────────

let splashWin: BrowserWindow | null = null;
let mainWin: BrowserWindow | null = null;

function createSplash(): void {
  splashWin = new BrowserWindow({
    width: 480,
    height: 280,
    frame: false,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    transparent: false,
    backgroundColor: '#0c1018',
    show: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  splashWin.loadFile(path.join(__dirname, 'splash.html'));
  splashWin.on('closed', () => { splashWin = null; });
}

function createMainWindow(): void {
  mainWin = new BrowserWindow({
    width:     1440,
    height:    900,
    minWidth:  1024,
    minHeight: 700,
    title:     'STARHE — MEDomics Plugin',
    backgroundColor: '#0c1018',
    show: false, // affiché après ready-to-show pour éviter le flash blanc
    webPreferences: {
      preload:          path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration:  false,
      sandbox:          false,
    },
  });

  if (isDev) {
    mainWin.loadURL('http://localhost:5173');
    mainWin.webContents.openDevTools();
  } else {
    mainWin.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWin.once('ready-to-show', () => {
    mainWin?.show();
    splashWin?.close();
  });

  mainWin.on('closed', () => { mainWin = null; });
}

/** Affiche un dialog clair si le serveur Go ne répond pas (MongoDB down, port pris, etc.). */
async function showGoUnavailableDialog(err: Error): Promise<void> {
  const { response } = await dialog.showMessageBox({
    type: 'error',
    title: 'STARHE — Serveur indisponible',
    message: 'Le serveur Go STARHE n\'a pas pu démarrer.',
    detail:
      `${err.message}\n\n` +
      `Vérifie que :\n` +
      `  • MongoDB tourne sur le port 54017 (prérequis externe)\n` +
      `  • Le port ${GO_PORT} n'est pas déjà utilisé\n` +
      `  • Le binaire go_server est présent dans les ressources de l'app\n\n` +
      `Tu peux réessayer ou quitter l'application.`,
    buttons: ['Réessayer', 'Quitter'],
    defaultId: 0,
    cancelId: 1,
  });
  if (response === 0) {
    // Réessai : la window principale est déjà créée, on relance juste la sonde
    await bootSequence();
  } else {
    appQuitting = true;
    app.quit();
  }
}

/** Orchestration : splash → download models (1er lancement) → spawn Go → wait healthy → main window. */
async function bootSequence(): Promise<void> {
  if (!splashWin) createSplash();

  // Phase 4 : télécharger les modèles `.pth` si absents (mode packagé uniquement).
  // En dev, on suppose qu'ils sont déjà dans pythonCode/.../models/.
  if (!isDev && !modelsReady()) {
    splashWin?.close();
    try {
      await ensureModelsDownloaded();
    } catch (err) {
      // Utilisateur a cliqué "Quitter" dans la fenêtre download
      appQuitting = true;
      app.quit();
      return;
    }
    if (!splashWin) createSplash();
  }

  startGoServer();
  try {
    await waitForGoHealthy();
    if (!mainWin) createMainWindow();
  } catch (err) {
    splashWin?.close();
    await showGoUnavailableDialog(err as Error);
  }
}

// ── IPC : dialogue natif fichiers DICOM ───────────────────────────────────────

ipcMain.handle('open-dicom-files', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title:       'Ouvrir des fichiers DICOM',
    buttonLabel: 'Ouvrir',
    filters: [
      {
        name: 'Fichiers DICOM',
        // Extensions courantes + '' pour les fichiers sans extension
        // (ex: A0000, A0001 — standard DICOM sans suffixe).
        // pydicom identifie les DICOM par magic bytes, pas par l'extension.
        extensions: ['dcm', 'DCM', 'dicom', 'DICOM', 'dic', 'DIC', 'img', ''],
      },
      { name: 'Tous les fichiers', extensions: ['*'] },
    ],
    properties: ['openFile', 'multiSelections'],
  });
  return canceled ? [] : filePaths;
});

// ── Cycle de vie de l'application ─────────────────────────────────────────────

app.whenReady().then(() => {
  bootSequence();

  // macOS : recréer la fenêtre si l'app est réactivée sans fenêtre ouverte
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) bootSequence();
  });
});

app.on('before-quit', () => {
  appQuitting = true;
  if (restartTimer) {
    clearTimeout(restartTimer);
    restartTimer = null;
  }
  if (goServer) {
    goServer.kill('SIGTERM');
  }
});

app.on('window-all-closed', () => {
  // Sur macOS, l'app reste active même sans fenêtre (comportement natif)
  if (process.platform !== 'darwin') app.quit();
});
