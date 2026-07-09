/**
 * electron.d.ts — Type declarations for the Electron API injected
 *                 into the renderer via contextBridge (preload.ts).
 *
 * These types are globally available throughout the renderer's
 * TypeScript code (src/) without an explicit import.
 */

// Declaration for image imports (PNG, JPG, SVG, WEBP)
declare module '*.png' { const src: string; export default src; }
declare module '*.jpg' { const src: string; export default src; }
declare module '*.jpeg' { const src: string; export default src; }
declare module '*.svg' { const src: string; export default src; }
declare module '*.webp' { const src: string; export default src; }

interface Window {
  /**
   * API exposed by electron/preload.ts via contextBridge.
   * Available only in the Electron context.
   */
  electronAPI?: {
    /** Opens a native DICOM file selection dialog. */
    openDicomFiles: () => Promise<string[]>;
    /** Base URL of the local Go server (e.g. 'http://localhost:8080'). */
    apiBase: string;
  };

  /**
   * Legacy alternative: manual injection of the base URL (MEDomics).
   * Used when the plugin is integrated into MEDomics without the Electron preload.
   */
  __STARHE_API_BASE__?: string;
}
