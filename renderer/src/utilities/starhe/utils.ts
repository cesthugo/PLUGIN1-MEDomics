// utils.ts — Shared utilities of the STARHE plugin

/** Extensions commonly used for DICOM files. */
export const DICOM_EXTENSIONS = ['.dcm', '.dicom', '.dic', '.ima', '.img'];

/** Names that are never DICOM images — OS metadata noise found in folders. */
const NON_DICOM_NAMES = new Set(['thumbs.db', 'desktop.ini', 'dicomdir']);

/**
 * Cheap name-based pre-filter: keeps DICOM extensions and extension-less files
 * (e.g. A0000 — the common ultrasound convention). Not authoritative on its own,
 * since an extension-less file may be anything; see `filterDicomFiles`.
 */
export function isDicomFile(f: File): boolean {
  const n = f.name.toLowerCase();
  if (n.startsWith('.') || NON_DICOM_NAMES.has(n)) return false;
  if (DICOM_EXTENSIONS.some(e => n.endsWith(e))) return true;
  return !n.includes('.');
}

/**
 * Authoritative DICOM test: the "DICM" magic number at byte offset 128
 * (PS3.10 preamble). Extension-agnostic — this is how pydicom identifies
 * a DICOM, so it detects files whatever their name.
 */
export async function hasDicomMagic(f: File): Promise<boolean> {
  if (f.size < 132) return false;
  try {
    const bytes = new Uint8Array(await f.slice(128, 132).arrayBuffer());
    return bytes[0] === 0x44 && bytes[1] === 0x49
        && bytes[2] === 0x43 && bytes[3] === 0x4d; // "DICM"
  } catch {
    return false;
  }
}

/**
 * Reduces a folder's contents to the actual DICOM files.
 * A file is kept when it carries the DICM magic number, or when it has an
 * explicit DICOM extension (some valid files omit the 128-byte preamble).
 * Extension-less files must pass the magic test, which keeps unrelated
 * files out of the viewer.
 */
export async function filterDicomFiles(files: File[]): Promise<File[]> {
  const candidates = files.filter(isDicomFile);
  const magic = await Promise.all(candidates.map(hasDicomMagic));
  return candidates.filter((f, i) => {
    if (magic[i]) return true;
    const n = f.name.toLowerCase();
    return DICOM_EXTENSIONS.some(e => n.endsWith(e));
  });
}

/**
 * Runs `task` over every item, keeping at most `limit` executions in flight.
 * Used to load a whole folder concurrently: a plain `for … await` loop would
 * load files one by one, while `Promise.all` on a large folder would spawn one
 * Python decode subprocess per file at once and exhaust memory.
 */
export async function mapWithConcurrency<T>(
  items: T[],
  limit: number,
  task: (item: T) => Promise<void>,
): Promise<void> {
  let cursor = 0;
  const workers = Array.from(
    { length: Math.max(1, Math.min(limit, items.length)) },
    async () => {
      while (cursor < items.length) {
        const idx = cursor++;
        await task(items[idx]);
      }
    },
  );
  await Promise.all(workers);
}

// Auto-incremented counter for tab IDs (module singleton)
let _nextTabId = 1;
export const nextTabId = (): number => _nextTabId++;
