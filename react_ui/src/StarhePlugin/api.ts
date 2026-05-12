// api.ts — Appels vers le serveur Go STARHE


import type { DicomData, Detection, AnalysisResult, SSEPayload } from './types';

// Base URL configurable (ordre de priorité) :
//   1. window.electronAPI.apiBase  → injecté par electron/preload.ts
//   2. window.__STARHE_API_BASE__  → injection manuelle (iframe MEDomics via postMessage)
//   3. ''                          → chemin relatif → proxy Vite en dev
//
// Fonction (non const) pour relire la valeur à chaque appel,
// notamment après l'injection tardive de window.__STARHE_API_BASE__.
export function getApiBase(): string {
  return window.electronAPI?.apiBase ?? (window as any).__STARHE_API_BASE__ ?? '';
}

// ── Chargement DICOM ──────────────────────────────────────────────────────────

export interface DicomLoadResponse {
  file_name:          string;
  frame_count:        number;
  rows:               number;
  cols:               number;
  modality:           string;
  pixel_spacing:      [number, number] | null;
  base_fps:           number;
  original_sensitive: [string, string][];
  kept_metadata:      [string, string][];
  patient_name:       string;
  study_date:         string;
  frames_b64:         string[];
  /** Chemin du fichier sur le serveur (injecté par le handler Go) */
  server_path?:       string;
  error?:             string;
}

export async function loadDicom(
  dicomPath: string,
  quality  = 70,
  maxDim   = 640,
): Promise<DicomData> {
  const res = await fetch(`${getApiBase()}/starhe/dicom/load`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ dicom_path: dicomPath, quality, max_dim: maxDim }),
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => `HTTP ${res.status}`);
    throw new Error(txt || `HTTP ${res.status}`);
  }

  const json: DicomLoadResponse = await res.json();
  if (json.error) throw new Error(json.error);

  return mapDicomResponse(json);
}

/**
 * Charge un DICOM depuis un objet File (navigateur standard, sans Electron).
 * Upload les octets en multipart/form-data → le serveur Go écrit un fichier
 * temporaire qu'il supprime après traitement.
 */
export async function loadDicomFile(
  file:    File,
  quality = 70,
  maxDim  = 640,
): Promise<DicomData> {
  const form = new FormData();
  form.append('file', file);
  form.append('quality', String(quality));
  form.append('max_dim', String(maxDim));

  const res = await fetch(`${getApiBase()}/starhe/dicom/load`, {
    method: 'POST',
    body:   form,
    // Ne pas définir Content-Type manuellement — le navigateur ajoute le
    // boundary multipart automatiquement si on laisse le champ absent.
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => `HTTP ${res.status}`);
    throw new Error(txt);
  }

  const json: DicomLoadResponse = await res.json();
  if (json.error) throw new Error(json.error);

  return mapDicomResponse(json);
}

function mapDicomResponse(json: DicomLoadResponse): DicomData {
  return {
    fileName:          json.file_name,
    frameCount:        json.frame_count,
    rows:              json.rows,
    cols:              json.cols,
    modality:          json.modality,
    pixelSpacing:      json.pixel_spacing,
    baseFps:           json.base_fps,
    originalSensitive: json.original_sensitive,
    keptMetadata:      json.kept_metadata,
    patientName:       json.patient_name,
    studyDate:         json.study_date,
    framesB64:         json.frames_b64,
    serverPath:        json.server_path ?? '',
  };
}

// ── Suppression du cache MongoDB ──────────────────────────────────────────────

export async function deleteCache(dicomPath: string): Promise<{ deleted: number }> {
  const res = await fetch(
    `${getApiBase()}/starhe/cache?path=${encodeURIComponent(dicomPath)}`,
    { method: 'DELETE' },
  );
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    throw new Error((j as any).error ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Analyse SSE (pipeline STARHE) ────────────────────────────────────────────

export interface AnalyzeRequest {
  dicomPath:          string;
  anonMode?:          string;
  runRisk?:           boolean;
  runDetection?:      boolean;
  backScanConversion?: boolean;
  backscanWidth?:     number;
  backscanHeight?:    number;
}

/**
 * Ouvre un flux SSE vers /starhe/analyze.
 *
 * @param req  Corps de la requête
 * @param onEvent  Callback pour chaque événement SSE parsé
 * @param onDone  Appelé quand le signal [DONE] est reçu
 * @returns Fonction abort() pour annuler le flux
 */
export function streamAnalysis(
  req: AnalyzeRequest,
  onEvent: (payload: SSEPayload) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): () => void {
  const ctrl = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${getApiBase()}/starhe/analyze`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          dicom_path:          req.dicomPath,
          anon_mode:           req.anonMode ?? 'hash',
          run_risk:            req.runRisk ?? true,
          run_detection:       req.runDetection ?? true,
          back_scan_conversion: req.backScanConversion ?? true,
          backscan_width:      req.backscanWidth ?? 512,
          backscan_height:     req.backscanHeight ?? 512,
        }),
        signal:  ctrl.signal,
      });

      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') { onDone(); return; }
          try {
            onEvent(JSON.parse(raw) as SSEPayload);
          } catch {
            // ligne malformée — ignorer
          }
        }
      }
      onDone();
    } catch (err: unknown) {
      if ((err as Error)?.name !== 'AbortError') {
        onError(err instanceof Error ? err : new Error(String(err)));
      }
    }
  })();

  return () => ctrl.abort();
}

// ── Label d'onglet depuis la date DICOM ──────────────────────────────────────

export function makeTabLabel(studyDate: string, fileName: string): string {
  const sd = studyDate.trim();
  // Suffixe court du nom de fichier (sans extension) pour différencier les onglets
  const base   = fileName.replace(/\.[^.]+$/, '');
  const suffix = base.slice(0, 12);
  if (sd.length === 8 && /^\d{8}$/.test(sd)) {
    return `${sd.slice(6, 8)}/${sd.slice(4, 6)}/${sd.slice(0, 4)} · ${suffix}`;
  }
  if (sd && sd !== '— absent') return `${sd.slice(0, 10)} · ${suffix}`;
  return suffix;
}
