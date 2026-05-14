// utils.ts — Utilitaires partagés du plugin STARHE

/**
 * Retourne true si le fichier est un DICOM.
 * Convention : extension .dcm / .dicom ou absence d'extension (standard US courant).
 */
export function isDicomFile(f: File): boolean {
  const n = f.name.toLowerCase();
  return n.endsWith('.dcm') || n.endsWith('.dicom') || !n.includes('.');
}

// Compteur auto-incrémenté pour les IDs d'onglets (singleton module)
let _nextTabId = 1;
export const nextTabId = (): number => _nextTabId++;
