/**
 * electron/main.ts — Electron main process for the STARHE plugin
 *
 * Responsibilities:
 *   1. Create the BrowserWindow and load the React renderer
 *   2. Start the Go server (go_server) as a subprocess
 *   3. Expose the native DICOM file-open dialog via IPC
 *   4. Cleanly stop the Go server when the app closes
 *
 * Security:
 *   - contextIsolation: true  — the renderer has no direct access to Node.js
 *   - nodeIntegration: false  — no Node API in the renderer
 *   - Only the preload exposes a strictly defined API via contextBridge
 */

import { app, BrowserWindow, ipcMain, dialog, net } from 'electron';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs   from 'fs';
import { getWeightsDir, modelsReady, missingModels, installWeights } from './weights';

const isDev = !app.isPackaged;

// Go server port + URL — aligned with go_server/config.go (PORT env)
const GO_PORT = process.env.STARHE_PORT ?? '8082';
const GO_BASE_URL = `http://localhost:${GO_PORT}`;

// ── Go server ─────────────────────────────────────────────────────────────────

let goServer: ChildProcess | null = null;
/** true as soon as the app starts closing — inhibits restarts */
let appQuitting = false;

// Exponential backoff delays between restarts (ms)
const RESTART_DELAYS = [1_000, 2_000, 5_000, 10_000, 30_000];
let restartAttempt = 0;
let restartTimer: ReturnType<typeof setTimeout> | null = null;

/** Returns the path to the go_server binary depending on the environment and platform. */
function getGoServerBin(): string {
  if (isDev) {
    // In development: OS + arch auto-detection → build-resources/go-server/
    // __dirname = renderer/electron-dist/  →  ../build-resources/go-server/
    const os   = process.platform === 'win32' ? 'win'
               : process.platform === 'darwin' ? 'mac'
               : 'linux';
    const arch = process.arch === 'arm64' ? 'arm64' : 'x64';
    const ext  = process.platform === 'win32' ? '.exe' : '';
    return path.join(__dirname, '..', 'build-resources', 'go-server',
                     `go-server-${os}-${arch}${ext}`);
  }
  // In production: binary copied into the resources packaged by electron-builder
  const ext = process.platform === 'win32' ? '.exe' : '';
  return path.join(process.resourcesPath, 'go_server', `go_server${ext}`);
}

/** Ping GET /health — resolves on the first 200, rejects after `timeoutMs`. */
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
      // Point the weasis bridge to the bundled copy (extraResources).
      // Ignored if not packaged: weasis_bridge.py recomputes from PROJECT_ROOT.
      ...(isDev ? {} : { STARHE_WEASIS_DIR: path.join(process.resourcesPath, 'weasis-dcm2png') }),
      // Point the weasis bridge to the embedded Temurin JRE (Phase 3).
      // In dev: uses the `java` from PATH (brew install openjdk@17).
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
      // Point Go to the bundled Python worker (PyInstaller --onedir).
      // If not set, Go falls back to the local venv (dev mode).
      ...(isDev
        ? {}
        : {
            STARHE_WORKER_BIN: path.join(
              process.resourcesPath,
              'starhe_worker',
              process.platform === 'win32' ? 'starhe_worker.exe' : 'starhe_worker',
            ),
          }),
      // Point the Python pipeline to the directory where the `.pth` files were
      // downloaded at first launch (Phase 4). In dev: unset → uses
      // pythonCode/modules/starhe_plugin/models/ (.pth versioned locally).
      ...(isDev ? {} : { STARHE_WEIGHTS_DIR: getWeightsDir() }),
    },
  });

  console.log(`[STARHE] Serveur Go démarré (pid ${goServer.pid}, tentative ${restartAttempt + 1})`);

  goServer.on('error', (err) =>
    console.error('[STARHE] Erreur démarrage serveur Go :', err.message),
  );

  goServer.on('exit', (code, signal) => {
    goServer = null;

    // Intentional stop (SIGTERM/SIGINT from before-quit) → do not restart
    if (appQuitting || signal === 'SIGTERM' || signal === 'SIGINT') return;

    // Crash or unexpected stop → automatic restart with backoff
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

  // Successful restart: reset the counter after 30 s of stability
  setTimeout(() => {
    if (goServer && !appQuitting) restartAttempt = 0;
  }, 30_000);
}

// ── Main window ───────────────────────────────────────────────────────────────

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
    show: false, // shown after ready-to-show to avoid the white flash
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

/** Shows a clear dialog if the Go server does not respond (MongoDB down, port taken, etc.). */
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
    // Retry: the main window is already created, just restart the probe
    await bootSequence();
  } else {
    appQuitting = true;
    app.quit();
  }
}

/** Orchestration : splash → download models (1er lancement) → spawn Go → wait healthy → main window. */
async function bootSequence(): Promise<void> {
  if (!splashWin) createSplash();

  // The `.pth` weights are NOT downloaded — for confidentiality the user loads
  // them from their own computer (React "load model weights" step before an
  // analysis; see the `models:*` IPC handlers below). The app boots normally
  // whether or not the weights are present.

  startGoServer();
  try {
    await waitForGoHealthy();
    if (!mainWin) createMainWindow();
  } catch (err) {
    splashWin?.close();
    await showGoUnavailableDialog(err as Error);
  }
}

// ── IPC: native DICOM file dialog ─────────────────────────────────────────────

ipcMain.handle('open-dicom-files', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title:       'Ouvrir des fichiers DICOM',
    buttonLabel: 'Ouvrir',
    filters: [
      {
        name: 'Fichiers DICOM',
        // Common extensions + '' for extension-less files
        // (e.g. A0000, A0001 — standard DICOM without a suffix).
        // pydicom identifies DICOMs by magic bytes, not by the extension.
        extensions: ['dcm', 'DCM', 'dicom', 'DICOM', 'dic', 'DIC', 'img', ''],
      },
      { name: 'Tous les fichiers', extensions: ['*'] },
    ],
    properties: ['openFile', 'multiSelections'],
  });
  return canceled ? [] : filePaths;
});

// ── IPC: local model weights (loaded from the user's computer) ─────────────────

/** Returns whether the required `.pth` weights are present locally. */
ipcMain.handle('models:status', () => ({
  ready: modelsReady(),
  missing: missingModels(),
}));

/** Opens a native dialog to pick the `.pth` weights, then installs them into the
 *  weights dir. Returns the resulting status. */
ipcMain.handle('models:load', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title:       'Sélectionner les poids des modèles STARHE (.pth)',
    buttonLabel: 'Charger',
    filters: [
      { name: 'Poids PyTorch', extensions: ['pth'] },
      { name: 'Tous les fichiers', extensions: ['*'] },
    ],
    properties: ['openFile', 'multiSelections'],
  });
  if (canceled || filePaths.length === 0) {
    return { ready: modelsReady(), installed: [], missing: missingModels(), error: 'Annulé' };
  }
  return installWeights(filePaths);
});

// ── Cycle de vie de l'application ─────────────────────────────────────────────

app.whenReady().then(() => {
  bootSequence();

  // macOS: recreate the window if the app is reactivated with no window open
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
  // On macOS, the app stays active even with no window (native behavior)
  if (process.platform !== 'darwin') app.quit();
});
