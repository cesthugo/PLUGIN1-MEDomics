/**
 * electron/download-preload.ts — Preload pour la fenêtre de téléchargement
 * des modèles IA (Phase 4). Expose une API minimale au renderer pour recevoir
 * les events de progression et déclencher retry/quit.
 */
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('starheDownload', {
  onProgress: (cb: (evt: any) => void) => {
    ipcRenderer.on('download:progress', (_e, evt) => cb(evt));
  },
  retry: () => ipcRenderer.send('download:retry'),
  quit:  () => ipcRenderer.send('download:quit'),
});
