// utils.ts — Shared utilities of the STARHE plugin

/**
 * Returns true if the file is a DICOM.
 * Convention: .dcm / .dicom extension or no extension (common US standard).
 */
export function isDicomFile(f: File): boolean {
  const n = f.name.toLowerCase();
  return n.endsWith('.dcm') || n.endsWith('.dicom') || !n.includes('.');
}

// Auto-incremented counter for tab IDs (module singleton)
let _nextTabId = 1;
export const nextTabId = (): number => _nextTabId++;
