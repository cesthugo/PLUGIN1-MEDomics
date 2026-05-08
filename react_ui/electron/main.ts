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

import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs   from 'fs';

const isDev = !app.isPackaged;

// ── Serveur Go ────────────────────────────────────────────────────────────────

let goServer: ChildProcess | null = null;
/** true dès que l'app commence à se fermer — inhibe les redémarrages */
let appQuitting = false;

// Délais de backoff exponentiel entre les redémarrages (ms)
const RESTART_DELAYS = [1_000, 2_000, 5_000, 10_000, 30_000];
let restartAttempt = 0;
let restartTimer: ReturnType<typeof setTimeout> | null = null;

/** Retourne le chemin vers le binaire go_server selon l'environnement. */
function getGoServerBin(): string {
  const ext = process.platform === 'win32' ? '.exe' : '';
  const bin = `go_server${ext}`;
  if (isDev) {
    // En développement : binaire compilé dans go_server/ à la racine du repo
    return path.join(__dirname, '../../go_server', bin);
  }
  // En production : binaire copié dans les ressources packagées
  return path.join(process.resourcesPath, 'go_server', bin);
}

function startGoServer(): void {
  if (appQuitting) return;

  const bin = getGoServerBin();

  if (!fs.existsSync(bin)) {
    console.warn(`[STARHE] Binaire Go introuvable : ${bin}`);
    console.warn('[STARHE] Compilez-le d\'abord :  cd go_server && go build -o go_server .');
    return;
  }

  goServer = spawn(bin, [], {
    stdio: 'inherit',
    env: { ...process.env },
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

function createWindow(): void {
  const win = new BrowserWindow({
    width:     1440,
    height:    900,
    minWidth:  1024,
    minHeight: 700,
    title:     'STARHE — MEDomics Plugin',
    backgroundColor: '#0c1018',
    webPreferences: {
      // Chemin vers le script preload compilé (electron-dist/preload.js)
      preload:          path.join(__dirname, 'preload.js'),
      contextIsolation: true,   // Sécurité : pas d'accès Node depuis le renderer
      nodeIntegration:  false,
      sandbox:          false,  // Nécessaire pour les preloads non-sandboxés
    },
  });

  if (isDev) {
    // Charge le serveur de développement Vite (avec HMR)
    win.loadURL('http://localhost:5173');
    win.webContents.openDevTools();
  } else {
    // Charge le build statique (dist/index.html)
    win.loadFile(path.join(__dirname, '../dist/index.html'));
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
  startGoServer();
  createWindow();

  // macOS : recréer la fenêtre si l'app est réactivée sans fenêtre ouverte
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
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
