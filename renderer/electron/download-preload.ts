/**
 * electron/download-preload.ts — Preload for the download window
 * of the AI models (Phase 4). Exposes a minimal API to the renderer to receive
 * the progress events and trigger retry/quit.
 */
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('starheDownload', {
  onProgress: (cb: (evt: any) => void) => {
    ipcRenderer.on('download:progress', (_e, evt) => cb(evt));
  },
  retry: () => ipcRenderer.send('download:retry'),
  quit:  () => ipcRenderer.send('download:quit'),
});
