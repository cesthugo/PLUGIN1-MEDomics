/**
 * electron/download-models.ts — Téléchargement des poids IA STARHE au 1er lancement
 *
 * Source de vérité du manifeste : repo GitHub Release `STARHE_MODELS` du même
 * dépôt que `scripts/download_models.py` (cesthugo/PLUGIN1-MEDomics).
 *
 * En mode dev : pas de téléchargement (les .pth sont supposés présents dans
 *               pythonCode/modules/starhe_plugin/models/).
 * En mode packagé : si `app.getPath('userData')/models/<file>.pth` est absent,
 *                   afficher une fenêtre avec barre de progression et télécharger.
 *
 * GitHub privé : passer `GITHUB_TOKEN=ghp_xxx` dans l'env Electron pour activer
 *                l'auth Bearer. Sans token et avec un repo privé : 404.
 */

import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import * as path from 'path';
import * as fs   from 'fs';
import * as https from 'https';
import * as http  from 'http';
import { URL } from 'url';

// ── Manifeste : 1 source de vérité, alignée avec scripts/download_models.py ──
const REPO_OWNER  = 'cesthugo';
const REPO_NAME   = 'PLUGIN1-MEDomics';
const RELEASE_TAG = 'STARHE_MODELS';

/** Fichiers à télécharger (nom dans la Release GitHub). */
export const REQUIRED_MODELS = [
  'best_acc_mean_cls_f1_epoch_14.pth',     // C3D classification ~312 MB
  'best_coco_bbox_mAP_50_iter_2100.pth',   // RTMDet detection   ~439 MB
];

const RELEASE_DL_BASE = `https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/${RELEASE_TAG}`;
const RELEASE_API_URL = `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/tags/${RELEASE_TAG}`;

const GITHUB_TOKEN = process.env.GITHUB_TOKEN || '';

/** Override pour tests : si défini, sert les modèles depuis ce préfixe d'URL
 *  (ex. `http://localhost:8000` pointant vers un dossier contenant les .pth).
 *  Ignoré dès qu'une release publique GitHub est disponible. */
const TEST_BASE_URL = process.env.STARHE_MODELS_BASE_URL || '';

// ── Chemins ───────────────────────────────────────────────────────────────────

/** Dossier où les poids `.pth` doivent être présents avant de booter le pipeline. */
export function getWeightsDir(): string {
  return path.join(app.getPath('userData'), 'models');
}

/** True si tous les fichiers du manifeste existent et font > 1 MB (sanity). */
export function modelsReady(): boolean {
  const dir = getWeightsDir();
  return REQUIRED_MODELS.every((name) => {
    const p = path.join(dir, name);
    try {
      return fs.statSync(p).size > 1_000_000;
    } catch {
      return false;
    }
  });
}

// ── HTTP : suivre redirects, headers Auth optionnels ─────────────────────────

function httpGet(urlStr: string, headers: Record<string, string>): Promise<{ res: any; finalUrl: string }> {
  return new Promise((resolve, reject) => {
    const followRedirect = (u: string, depth: number) => {
      if (depth > 6) return reject(new Error('Trop de redirections'));
      const url = new URL(u);
      const lib = url.protocol === 'http:' ? http : https;
      const req = lib.get(
        {
          hostname: url.hostname,
          port:     url.port || (url.protocol === 'http:' ? 80 : 443),
          path:     url.pathname + url.search,
          headers: {
            'User-Agent': 'STARHE-Electron-Downloader',
            ...headers,
          },
        },
        (res) => {
          const sc = res.statusCode ?? 0;
          if (sc >= 300 && sc < 400 && res.headers.location) {
            res.resume(); // drain
            const next = new URL(res.headers.location, u).toString();
            followRedirect(next, depth + 1);
            return;
          }
          if (sc !== 200) {
            res.resume();
            return reject(new Error(`HTTP ${sc} sur ${u}`));
          }
          resolve({ res, finalUrl: u });
        },
      );
      req.on('error', reject);
    };
    followRedirect(urlStr, 0);
  });
}

/** Pour un repo privé, GET /releases/download/ renvoie 404. Il faut passer par
 *  l'API et récupérer l'URL `assets[].url` avec header Accept: octet-stream. */
async function resolveAssetUrl(name: string): Promise<string> {
  if (TEST_BASE_URL) {
    return `${TEST_BASE_URL.replace(/\/$/, '')}/${name}`;
  }
  if (!GITHUB_TOKEN) {
    return `${RELEASE_DL_BASE}/${name}`;
  }
  return new Promise((resolve, reject) => {
    https
      .get(
        {
          hostname: 'api.github.com',
          path: `/repos/${REPO_OWNER}/${REPO_NAME}/releases/tags/${RELEASE_TAG}`,
          headers: {
            'User-Agent': 'STARHE-Electron-Downloader',
            Accept: 'application/vnd.github+json',
            Authorization: `Bearer ${GITHUB_TOKEN}`,
          },
        },
        (res) => {
          let body = '';
          res.on('data', (c) => (body += c));
          res.on('end', () => {
            if (res.statusCode !== 200) {
              return reject(new Error(`API GitHub HTTP ${res.statusCode}: ${body.slice(0, 200)}`));
            }
            try {
              const json = JSON.parse(body);
              const asset = (json.assets || []).find((a: any) => a.name === name);
              if (!asset) return reject(new Error(`Asset '${name}' introuvable dans release ${RELEASE_TAG}`));
              resolve(asset.url as string);
            } catch (e) {
              reject(e);
            }
          });
        },
      )
      .on('error', reject);
  });
}

// ── Téléchargement avec progression ──────────────────────────────────────────

async function downloadOne(
  name: string,
  destDir: string,
  onBytes: (done: number, total: number) => void,
): Promise<void> {
  const dest = path.join(destDir, name);
  const tmp  = dest + '.part';
  fs.mkdirSync(destDir, { recursive: true });
  if (fs.existsSync(tmp)) fs.unlinkSync(tmp);

  const url = await resolveAssetUrl(name);
  const headers: Record<string, string> = { Accept: 'application/octet-stream' };
  if (GITHUB_TOKEN) headers.Authorization = `Bearer ${GITHUB_TOKEN}`;

  const { res } = await httpGet(url, headers);
  const total = parseInt(String(res.headers['content-length'] || '0'), 10);
  let done = 0;

  await new Promise<void>((resolve, reject) => {
    const out = fs.createWriteStream(tmp);
    res.on('data', (chunk: Buffer) => {
      done += chunk.length;
      onBytes(done, total);
    });
    res.pipe(out);
    out.on('finish', () => out.close(() => resolve()));
    out.on('error', reject);
    res.on('error', reject);
  });

  fs.renameSync(tmp, dest);
}

// ── Fenêtre de téléchargement + orchestration ────────────────────────────────

let downloadWin: BrowserWindow | null = null;

function createDownloadWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 540,
    height: 340,
    frame: false,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    backgroundColor: '#0c1018',
    show: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'download-preload.js'),
    },
  });
  win.loadFile(path.join(__dirname, 'download-models.html'));
  win.on('closed', () => { downloadWin = null; });
  return win;
}

/** Télécharge tous les modèles manquants avec UI Electron.
 *  Résout quand tous les fichiers sont présents. Rejette si l'utilisateur quitte. */
export async function ensureModelsDownloaded(): Promise<void> {
  if (modelsReady()) return;

  const destDir = getWeightsDir();
  downloadWin = createDownloadWindow();

  // Attendre que le renderer ait chargé son script avant d'émettre des events
  await new Promise<void>((resolve) => {
    downloadWin!.webContents.once('did-finish-load', () => resolve());
  });

  const send = (evt: any) => downloadWin?.webContents.send('download:progress', evt);

  return new Promise<void>((resolve, reject) => {
    let userQuit = false;
    ipcMain.removeAllListeners('download:quit');
    ipcMain.removeAllListeners('download:retry');
    ipcMain.on('download:quit',  () => { userQuit = true; reject(new Error('Téléchargement annulé')); });
    ipcMain.on('download:retry', () => { run(); });

    const run = async () => {
      try {
        const missing = REQUIRED_MODELS.filter((n) => {
          try { return fs.statSync(path.join(destDir, n)).size < 1_000_000; }
          catch { return true; }
        });

        for (let i = 0; i < missing.length; i++) {
          const name = missing[i];
          send({ phase: 'start', file: name, current: i + 1, total: missing.length, bytesDone: 0, bytesTotal: 0 });
          await downloadOne(name, destDir, (done, total) => {
            send({ phase: 'progress', file: name, current: i + 1, total: missing.length, bytesDone: done, bytesTotal: total });
          });
        }

        if (!modelsReady()) {
          throw new Error('Modèles toujours manquants après téléchargement');
        }
        send({ phase: 'done' });
        // Laisser la fenêtre 600 ms pour montrer 100 % avant de la fermer
        setTimeout(() => {
          downloadWin?.close();
          resolve();
        }, 600);
      } catch (err) {
        if (userQuit) return;
        send({ phase: 'error', message: (err as Error).message });
      }
    };

    run();
  });
}
