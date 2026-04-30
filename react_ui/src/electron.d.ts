/**
 * electron.d.ts — Déclarations de types pour l'API Electron injectée
 *                 dans le renderer via contextBridge (preload.ts).
 *
 * Ces types sont disponibles globalement dans tout le code TypeScript
 * du renderer (src/) sans import explicite.
 */

interface Window {
  /**
   * API exposée par electron/preload.ts via contextBridge.
   * Disponible uniquement dans le contexte Electron.
   */
  electronAPI?: {
    /** Ouvre un dialogue natif de sélection de fichiers DICOM. */
    openDicomFiles: () => Promise<string[]>;
    /** Base URL du serveur Go local (ex: 'http://localhost:8080'). */
    apiBase: string;
  };

  /**
   * Alternative legacy : injection manuelle de la base URL (MEDomics).
   * Utilisé quand le plugin est intégré dans MEDomics sans Electron preload.
   */
  __STARHE_API_BASE__?: string;
}
