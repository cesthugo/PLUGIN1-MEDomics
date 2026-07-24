// api.ts — Calls to the STARHE Go server


import type { DicomData, Detection, AnalysisResult, SSEPayload } from './types';

// Configurable base URL (priority order):
//   1. window.electronAPI.apiBase  → injected by electron/preload.ts
//   2. window.__STARHE_API_BASE__  → manual injection (MEDomics iframe via postMessage)
//   3. ''                          → relative path → Vite proxy in dev
//
// Function (not const) to re-read the value on each call,
// in particular after the late injection of window.__STARHE_API_BASE__.
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
  /** File path on the server (injected by the Go handler) */
  server_path?:       string;
  error?:             string;
}

// Frames are served at the DICOM's native resolution: MAX_DIM is an upper
// safety bound (the Go server rejects anything above 4096), not a downscale
// target — a 890×1280 clip is encoded untouched. Lowering it makes the viewer
// upscale a smaller JPEG and look blurry.
const FRAME_QUALITY = 92;
const FRAME_MAX_DIM = 4096;

export async function loadDicom(
  dicomPath: string,
  quality  = FRAME_QUALITY,
  maxDim   = FRAME_MAX_DIM,
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
 * Loads a DICOM from a File object (standard browser, without Electron).
 * Uploads the bytes as multipart/form-data → the Go server writes a
 * temporary file that it deletes after processing.
 */
export async function loadDicomFile(
  file:    File,
  quality = FRAME_QUALITY,
  maxDim  = FRAME_MAX_DIM,
): Promise<DicomData> {
  const form = new FormData();
  form.append('file', file);
  form.append('quality', String(quality));
  form.append('max_dim', String(maxDim));

  const res = await fetch(`${getApiBase()}/starhe/dicom/load`, {
    method: 'POST',
    body:   form,
    // Do not set Content-Type manually — the browser adds the
    // multipart boundary automatically if the field is left unset.
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

// ── MongoDB cache deletion ────────────────────────────────────────────────────

// ── AI model weights (local provisioning) ─────────────────────────────────────

export interface WeightStatus {
  id:      string;   // 'risk' | 'detect'
  name:    string;   // human-readable model name
  file:    string;   // canonical .pth file name
  present: boolean;  // true if the weight is available server-side
}

/** Per-model presence of the STARHE weights on the server. */
export async function getWeightsStatus(): Promise<WeightStatus[]> {
  const res = await fetch(`${getApiBase()}/starhe/weights/status`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export interface WeightUploadResult {
  ok: boolean; id: string; file?: string; warning?: string; error?: string;
}

/**
 * Uploads a user-picked .pth for one model. Uses XMLHttpRequest to report
 * upload progress (checkpoints are 300–440 MB). Resolves on success, rejects
 * with the server error message otherwise.
 */
export function uploadWeight(
  modelId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<WeightUploadResult> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append('id', modelId);
    form.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${getApiBase()}/starhe/weights/upload`);
    xhr.upload.onprogress = e => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let body: WeightUploadResult;
      try { body = JSON.parse(xhr.responseText); }
      catch { body = { ok: false, id: modelId, error: `HTTP ${xhr.status}` }; }
      if (xhr.status >= 200 && xhr.status < 300 && body.ok) resolve(body);
      else reject(new Error(body.error || `HTTP ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.send(form);
  });
}

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

// ── SSE analysis (STARHE pipeline) ───────────────────────────────────────────

export interface AnalyzeRequest {
  dicomPath?:          string;
  anonMode?:          string;
  runRisk?:           boolean;
  runDetection?:      boolean;
  backScanConversion?: boolean;
  backscanWidth?:     number;
  backscanHeight?:    number;
}

/**
 * Opens an SSE stream to /starhe/analyze.
 *
 * @param req  Request body
 * @param onEvent  Callback for each parsed SSE event
 * @param onDone  Called when the [DONE] signal is received
 * @returns abort() function to cancel the stream
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
      const url  = `${getApiBase()}/starhe/analyze`;
      const body = JSON.stringify({
        dicom_path:           req.dicomPath,
        anon_mode:            req.anonMode ?? 'hash',
        run_risk:             req.runRisk ?? true,
        run_detection:        req.runDetection ?? true,
        back_scan_conversion: req.backScanConversion ?? true,
        backscan_width:       req.backscanWidth ?? 512,
        backscan_height:      req.backscanHeight ?? 512,
      });
      const res = await fetch(url, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
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
            // malformed line — ignore
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

// ── Tab label from the DICOM date ─────────────────────────────────────────────

export function makeTabLabel(studyDate: string, fileName: string): string {
  const sd = studyDate.trim();
  // Short suffix of the file name (without extension) to distinguish the tabs
  const base   = fileName.replace(/\.[^.]+$/, '');
  const suffix = base.slice(0, 12);
  if (sd.length === 8 && /^\d{8}$/.test(sd)) {
    return `${sd.slice(6, 8)}/${sd.slice(4, 6)}/${sd.slice(0, 4)} · ${suffix}`;
  }
  if (sd && sd !== '— absent') return `${sd.slice(0, 10)} · ${suffix}`;
  return suffix;
}
