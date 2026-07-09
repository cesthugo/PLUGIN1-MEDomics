/**
 * electron/preload.ts — Script de preload Electron (contextBridge)
 *
 * This script runs in an isolated context between the main process and
 * the React renderer. It exposes only the methods listed in
 * contextBridge.exposeInMainWorld(), keeping the renderer fully isolated
 * from Node.js while giving it access to the necessary native features.
 *
 * Security:
 *   - The renderer can only invoke the methods declared here
 *   - No direct access to ipcRenderer or the Node modules
 *   - Validate / filter the data on the main.ts side if needed
 */

import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  /**
   * Opens a native DICOM file selection dialog.
   * Returns an array of absolute paths (empty if the user cancels).
   */
  openDicomFiles: (): Promise<string[]> =>
    ipcRenderer.invoke('open-dicom-files'),

  /**
   * Base URL of the local Go server.
   * Used by api.ts to build the endpoints (API_BASE).
   */
  apiBase: 'http://localhost:8082' as const,
});
