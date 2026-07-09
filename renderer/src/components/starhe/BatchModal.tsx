// components/BatchModal.tsx — STARHE multi-file batch analysis
//
// Allows analyzing several DICOM files sequentially (one at a time
// to avoid the Python pipeline's memory conflicts).
//
// Each entry goes through the states:
//   waiting → loading → analyzing → done | error
//
// At the end, a summary table shows risk score + number of lesions / file.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { loadDicom, loadDicomFile, loadMp4File, streamAnalysis } from '../../utilities/starhe/api';
import type { AnalyzeRequest } from '../../utilities/starhe/api';
import type { Detection } from '../../utilities/starhe/types';
import {
  SIDEBAR_BG, MAIN_BG, BLUE, SBAR_FG, SBAR_MUTED,
  CARD_BG, CARD_BORDER, CARD_SHADOW,
  RISK_LOW_FG, RISK_HIGH_FG, SUCCESS_FG, DANGER_FG, WARN_FG,
} from '../../utilities/starhe/colors';

// ── Types ─────────────────────────────────────────────────────────────────────

type ItemStatus = 'waiting' | 'loading' | 'analyzing' | 'done' | 'error';

interface BatchItem {
  id:        number;
  /** Displayed name (file name or short path) */
  name:      string;
  /** Server-side absolute path (filled after loadDicom) */
  serverPath: string;
  /** File object if browser upload, undefined if absolute path */
  file?:     File;
  status:    ItemStatus;
  progress:  string;
  /** Results if status === 'done' */
  riskScore?: number;
  riskLabel?: string;
  detCount?:  number;
  /** Error message if status === 'error' */
  error?:    string;
  /** Detections per frame (for JSON export and bbox reloading) */
  detections?: Detection[][];
  /** Number of DICOM frames (metadata for the JSON) */
  numFrames?:  number;
  /** Crop ROI returned by the pipeline */
  roi?:        unknown;
  /** true if this file is an MP4 (not a DICOM) */
  isMp4?:      boolean;
}

let _id = 1;
const uid = () => _id++;

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusIcon(s: ItemStatus): string {
  switch (s) {
    case 'waiting':   return '⏳';
    case 'loading':   return '📂';
    case 'analyzing': return '🔬';
    case 'done':      return '✅';
    case 'error':     return '❌';
  }
}

function statusColor(s: ItemStatus): string {
  switch (s) {
    case 'done':      return SUCCESS_FG;
    case 'error':     return DANGER_FG;
    case 'analyzing': return BLUE;
    case 'loading':   return WARN_FG;
    default:          return SBAR_MUTED;
  }
}

function riskColor(label?: string): string {
  if (!label) return SBAR_MUTED;
  return /élevé|high/i.test(label) ? RISK_HIGH_FG : RISK_LOW_FG;
}

// ── Subcomponent: queue row ───────────────────────────────────────────────────

function BatchRow({ item, onRemove }: { item: BatchItem; onRemove: () => void }) {
  const isActive = item.status === 'loading' || item.status === 'analyzing';
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '22px 1fr auto',
      alignItems: 'center',
      gap: 8,
      padding: '6px 10px',
      borderBottom: `1px solid ${CARD_BORDER}`,
      background: isActive ? '#0d1a2a' : 'transparent',
    }}>
      {/* Icône statut */}
      <span style={{ fontSize: 14 }}>{statusIcon(item.status)}</span>

      {/* Nom + progression */}
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontSize: 12, color: SBAR_FG, fontWeight: 600,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {item.name}
        </div>
        <div style={{ fontSize: 11, color: statusColor(item.status) }}>
          {item.status === 'done'
            ? `Risk: ${item.riskLabel ?? '—'}${item.riskScore !== undefined ? ` (${(item.riskScore * 100).toFixed(1)} %)` : ''} · ${item.detCount ?? 0} lesion(s)`
            : item.status === 'error'
            ? item.error
            : item.progress || '—'}
        </div>
      </div>

      {/* Bouton supprimer (uniquement si pas actif) */}
      {!isActive && (
        <button
          onClick={onRemove}
          title="Retirer de la liste"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: SBAR_MUTED, fontSize: 14, padding: 2,
          }}
        >✕</button>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface BatchResultToOpen {
  serverPath:  string;
  name:        string;
  detections?: Detection[][];
  risk?:       { score: number; label: string };
  numFrames?:  number;
  roi?:        unknown;
  /** Original browser File object — allows re-uploading if the temp file expired */
  file?:       File;
  /** true if this result comes from an MP4 file (not DICOM) */
  isMp4?:      boolean;
}

export interface BatchModalProps {
  onClose:       () => void;
  /** Default analysis mode (from the global settings) */
  analysisMode:  'both' | 'risk_only' | 'detect_only';
  /** Callback to open the analyzed file in a main tab (with preloaded results) */
  onOpenInTab:   (result: BatchResultToOpen) => void;
  /**
   * Callback to open several files with the layout picker.
   * If absent, the files open individually in separate tabs.
   */
  onOpenInLayout?: (results: BatchResultToOpen[]) => void;
}

export function BatchModal({ onClose, analysisMode: defaultMode, onOpenInTab, onOpenInLayout }: BatchModalProps) {
  const [items,        setItems]        = useState<BatchItem[]>([]);
  const [running,      setRunning]      = useState(false);
  const [done,         setDone]         = useState(false);
  const [batchMode,    setBatchMode]    = useState<'both' | 'risk_only' | 'detect_only'>(defaultMode);
  const [selected,     setSelected]     = useState<Set<number>>(new Set());
  const [concurrency,  setConcurrency]  = useState(3);
  /** Map itemId → abort fn for the parallel analyses in progress */
  const abortMapRef  = useRef<Map<number, () => void>>(new Map());
  const cancelledRef = useRef(false);

  // Update an item by id
  const update = useCallback((id: number, patch: Partial<BatchItem>) => {
    setItems(prev => prev.map(it => it.id === id ? { ...it, ...patch } : it));
  }, []);

  // ── DICOM detection: .dcm, .dicom, or extension-less (e.g. A0000, IM-0001) ─
  const isDicomFile = (f: File) => {
    const lname = f.name.toLowerCase();
    return lname.endsWith('.dcm') || lname.endsWith('.dicom') || !lname.includes('.');
  };
  const isMp4File = (f: File) => f.name.toLowerCase().endsWith('.mp4');

  // ── Add files (browser upload) ─────────────────────────────────────────────
  const onFileDrop = useCallback((files: FileList | null) => {
    if (!files) return;
    const all = Array.from(files);
    const dicomFiles = all.filter(isDicomFile);
    const mp4Files   = all.filter(isMp4File);
    const newItems: BatchItem[] = [
      ...dicomFiles.map(f => ({
        id: uid(), name: f.name, serverPath: '', file: f, isMp4: false,
        status: 'waiting' as ItemStatus, progress: 'En attente',
      })),
      ...mp4Files.map(f => ({
        id: uid(), name: f.name, serverPath: '', file: f, isMp4: true,
        status: 'waiting' as ItemStatus, progress: 'En attente',
      })),
    ];
    setItems(prev => [
      ...prev,
      ...newItems.filter(ni => !prev.some(ex => ex.name === ni.name)),
    ]);
    setDone(false);
  }, []);

  // ── MP4 file selection ─────────────────────────────────────────────────────
  const onPickMp4Files = useCallback(() => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.multiple = true;
    inp.accept = '.mp4,video/mp4';
    inp.onchange = () => onFileDrop(inp.files);
    inp.click();
  }, [onFileDrop]);

  // ── Add a whole folder (browser) ───────────────────────────────────────────
  const onPickFolder = useCallback(() => {
    const inp = document.createElement('input');
    inp.type = 'file';
    (inp as any).webkitdirectory = true;
    (inp as any).multiple = true;
    inp.onchange = () => onFileDrop(inp.files);
    inp.click();
  }, [onFileDrop]);

  // ── Add by absolute path (Electron / manual input) ────────────────────────
  const pathRef = useRef<HTMLInputElement>(null);
  const onAddPath = useCallback(() => {
    const val = pathRef.current?.value.trim();
    if (!val) return;
    const name = val.split('/').pop() ?? val;
    setItems(prev => [...prev, {
      id: uid(), name, serverPath: val, file: undefined,
      status: 'waiting', progress: 'En attente',
    }]);
    if (pathRef.current) pathRef.current.value = '';
    setDone(false);
  }, []);

  // ── Drag-and-drop ──────────────────────────────────────────────────────────
  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); };
  const onDrop     = (e: React.DragEvent) => { e.preventDefault(); onFileDrop(e.dataTransfer.files); };

  // ── Processing of a single item (reused by each worker) ──────────────────
  const processItem = useCallback(async (item: BatchItem, batchModeSnap: typeof batchMode) => {
    if (cancelledRef.current) return;

    // 1. File loading
    update(item.id, { status: 'loading', progress: item.isMp4 ? 'Chargement MP4…' : 'Chargement DICOM…' });
    let serverPath = item.serverPath;
    try {
      if (item.isMp4) {
        if (!item.file) throw new Error('fichier MP4 manquant (upload requis)');
        const data = await loadMp4File(item.file);
        serverPath = data.serverPath || item.name;
        update(item.id, { serverPath });
      } else if (item.file) {
        const data = await loadDicomFile(item.file);
        serverPath = data.serverPath || item.name;
        update(item.id, { serverPath });
      } else {
        await loadDicom(serverPath);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      update(item.id, { status: 'error', error: `Loading failed: ${msg}` });
      return;
    }

    if (cancelledRef.current) return;

    // 2. SSE analysis
    update(item.id, { status: 'analyzing', progress: 'Starting analysis…' });
    const req: AnalyzeRequest = item.isMp4
      ? {
          mp4Path:            serverPath,
          runRisk:            batchModeSnap !== 'detect_only',
          runDetection:       batchModeSnap !== 'risk_only',
          backScanConversion: true,
        }
      : {
          dicomPath:          serverPath,
          anonMode:           'hash',
          runRisk:            batchModeSnap !== 'detect_only',
          runDetection:       batchModeSnap !== 'risk_only',
          backScanConversion: true,
        };

    await new Promise<void>((resolve) => {
      let riskScore:  number | undefined;
      let riskLabel:  string | undefined;
      let detCount:   number | undefined;
      let detections: Detection[][] | undefined;
      let numFrames:  number | undefined;
      let roi:        unknown;
      // Business error emitted by Python (level "error") and reception of
      // the final "result" event — without this, a crashed pipeline was
      // marked ✓ done with "Risk: — · 0 lesion(s)" (false success).
      let pipelineError: string | undefined;
      let gotResult = false;

      const abort = streamAnalysis(
        req,
        (payload) => {
          const msg = payload.message ?? '';
          if (payload.level === 'progress' || payload.level === 'info') {
            update(item.id, { progress: msg });
          }
          if (payload.level === 'error') {
            pipelineError = msg || 'Erreur pipeline (voir logs serveur)';
          }
          if (payload.level === 'result') {
            gotResult = true;
          }
          if (payload.data?.risk) {
            const r = payload.data.risk;
            riskScore = r.score ?? r.risk_score ?? riskScore;
            riskLabel = r.label ?? r.risk_label ?? riskLabel;
          }
          if (payload.data?.detections_per_frame) {
            detections = payload.data.detections_per_frame as Detection[][];
            detCount   = detections.reduce((acc, fd) => acc + fd.length, 0);
          }
          if (payload.data?.num_frames !== undefined) numFrames = payload.data.num_frames as number;
          if (payload.data?.roi !== undefined) roi = payload.data.roi;
        },
        () => {
          abortMapRef.current.delete(item.id);
          if (pipelineError || !gotResult) {
            update(item.id, {
              status: 'error',
              error:  pipelineError ?? 'Pipeline terminé sans résultat (crash Python ?)',
            });
          } else {
            update(item.id, {
              status: 'done', progress: 'Done', serverPath,
              riskScore, riskLabel,
              detCount:   detCount ?? 0,
              detections: detections ?? [],
              numFrames,  roi,
            });
          }
          resolve();
        },
        (err) => {
          abortMapRef.current.delete(item.id);
          update(item.id, { status: 'error', error: err.message });
          resolve();
        },
      );
      abortMapRef.current.set(item.id, abort);
    });
  }, [update]);

  // ── Launch the batch (parallel workers) ────────────────────────────────────
  const runBatch = useCallback(async () => {
    cancelledRef.current = false;
    setRunning(true);
    setDone(false);

    const modeSnap = batchMode;
    // Queue shared between the workers (mutation-safe: single-threaded JS)
    const pending = items.filter(it => it.status === 'waiting' || it.status === 'error');

    // Each worker picks the next available item until exhaustion
    const worker = async () => {
      while (true) {
        if (cancelledRef.current) break;
        const item = pending.shift();
        if (!item) break;
        await processItem(item, modeSnap);
      }
    };

    const workers = Array.from({ length: Math.max(1, concurrency) }, worker);
    await Promise.all(workers);

    setRunning(false);
    setDone(true);
  }, [items, batchMode, concurrency, processItem]);

  // ── Cancel (interrupts all running workers) ──────────────────────────────
  const cancel = useCallback(() => {
    cancelledRef.current = true;
    for (const abort of abortMapRef.current.values()) abort();
    abortMapRef.current.clear();
    setRunning(false);
  }, []);

  // ── Remove a pending item ────────────────────────────────────────────────
  const removeItem = useCallback((id: number) => {
    setItems(prev => prev.filter(it => it.id !== id));
  }, []);

  // Stats finales
  const doneCount  = items.filter(it => it.status === 'done').length;
  const errCount   = items.filter(it => it.status === 'error').length;
  const waitCount  = items.filter(it => it.status === 'waiting').length;

  // ── Export CSV ────────────────────────────────────────────────────────────
  const exportCSV = useCallback(() => {
    const analysisLabel =
      batchMode === 'both'        ? 'RISK + DETECT' :
      batchMode === 'risk_only'   ? 'RISK only' :
                                    'DETECT only';

    const includeRisk   = batchMode !== 'detect_only';
    const includeDetect = batchMode !== 'risk_only';

    const header = [
      'File',
      'Status',
      ...(includeRisk   ? ['HCC Risk', 'Risk score (%)']          : []),
      ...(includeDetect ? ['Number of detected lesions']           : []),
      'Analysis mode',
      'Export date',
    ];

    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US') + ' ' + now.toLocaleTimeString('en-US');

    const rows = items.map(it => [
      it.name,
      it.status === 'done'  ? 'Done'        :
      it.status === 'error' ? 'Error'       :
      it.status === 'analyzing' ? 'In progress' : 'Pending',
      ...(includeRisk   ? [it.riskLabel ?? '', it.riskScore !== undefined ? (it.riskScore * 100).toFixed(2) : ''] : []),
      ...(includeDetect ? [it.status === 'done' ? String(it.detCount ?? 0) : '']                                  : []),
      analysisLabel,
      dateStr,
    ]);

    // Escapes fields containing commas, quotes or newlines
    const escape = (v: string) =>
      /[,"\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;

    const csv =
      [header, ...rows]
        .map(row => row.map(escape).join(','))
        .join('\r\n');

    // UTF-8 BOM so Excel opens it directly without encoding issues
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `starhe_batch_${now.toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [items, batchMode]);

  // ── Import JSON ─────────────────────────────────────────────────────────
  const importJSON = useCallback(() => {
    const inp  = document.createElement('input');
    inp.type   = 'file';
    inp.accept = '.json,application/json';
    inp.onchange = () => {
      const file = inp.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const payload = JSON.parse(reader.result as string);
          if (!payload?.starhe_batch || !Array.isArray(payload.results)) {
            alert('Invalid JSON file — not a STARHE batch export.');
            return;
          }
          const imported: BatchItem[] = (payload.results as any[]).map(r => ({
            id:         uid(),
            name:       r.file_name ?? r.server_path ?? 'unknown',
            serverPath: r.server_path ?? '',
            file:       undefined,
            status:     'done' as ItemStatus,
            progress:   'Imported from JSON',
            riskScore:  r.risk?.score,
            riskLabel:  r.risk?.label,
            detCount:   (r.detections_per_frame as Detection[][])
                          ?.reduce((acc: number, fd: Detection[]) => acc + fd.length, 0) ?? 0,
            detections: r.detections_per_frame ?? [],
            numFrames:  r.num_frames ?? undefined,
            roi:        r.roi ?? undefined,
          }));
          setItems(prev => [
            ...prev,
            ...imported.filter(ni => !prev.some(ex => ex.name === ni.name)),
          ]);
          setDone(true);
        } catch {
          alert('Impossible de lire le fichier JSON.');
        }
      };
      reader.readAsText(file);
    };
    inp.click();
  }, []);

  // ── Export JSON ─────────────────────────────────────────────────────────
  const exportJSON = useCallback(() => {
    const analysisLabel =
      batchMode === 'both'      ? 'RISK + DETECT' :
      batchMode === 'risk_only' ? 'RISK only'     : 'DETECT only';

    const payload = {
      starhe_batch:   '1.0',
      exported_at:    new Date().toISOString(),
      analysis_mode:  analysisLabel,
      results: items
        .filter(it => it.status === 'done')
        .map(it => ({
          file_name:            it.name,
          server_path:          it.serverPath,
          num_frames:           it.numFrames ?? null,
          roi:                  it.roi ?? null,
          risk: it.riskScore !== undefined
            ? { score: it.riskScore, label: it.riskLabel ?? '' }
            : null,
          detections_per_frame: it.detections ?? [],
        })),
    };

    const json = JSON.stringify(payload, null, 2);
    const blob = new Blob([json], { type: 'application/json;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `starhe_batch_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [items, batchMode]);

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !running) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [running, onClose]);

  // ── Rendu ─────────────────────────────────────────────────────────────────
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}
      onClick={e => { if (e.target === e.currentTarget && !running) onClose(); }}
    >
      <div style={{
        background: CARD_BG, border: `1px solid ${CARD_BORDER}`,
        boxShadow: CARD_SHADOW, borderRadius: 8,
        width: 640, maxWidth: '95vw', maxHeight: '85vh',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>

        {/* ── En-tête ── */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 18px', borderBottom: `1px solid ${CARD_BORDER}`,
          background: SIDEBAR_BG, flexShrink: 0,
        }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: SBAR_FG }}>
            📋  Batch analysis
          </span>
          <button
            onClick={importJSON}
            title="Import a previously exported JSON file (reloads results + bboxes)"
            style={{
              background: '#1e3a5f', border: '1px solid #1d4ed8',
              borderRadius: 4, padding: '3px 10px',
              color: '#93c5fd', fontSize: 11, cursor: 'pointer', fontWeight: 600,
            }}
          >⬆ Import JSON</button>
          {/* Sélecteur de mode d'analyse */}
          <div style={{ display: 'flex', gap: 4 }}>
            {(['both', 'risk_only', 'detect_only'] as const).map(m => {
              const label = m === 'both' ? 'RISK + DETECT' : m === 'risk_only' ? 'RISK' : 'DETECT';
              const active = batchMode === m;
              return (
                <button
                  key={m}
                  onClick={() => !running && setBatchMode(m)}
                  disabled={running}
                  title={m === 'both' ? 'STARHE RISK + DETECT' : m === 'risk_only' ? 'STARHE RISK only' : 'STARHE DETECT only'}
                  style={{
                    background: active ? BLUE : 'transparent',
                    border: `1px solid ${active ? BLUE : CARD_BORDER}`,
                    borderRadius: 4, padding: '3px 10px',
                    color: active ? '#fff' : SBAR_MUTED,
                    fontSize: 11, fontWeight: active ? 700 : 400,
                    cursor: running ? 'not-allowed' : 'pointer',
                    transition: 'background 0.1s, color 0.1s',
                  }}
                >{label}</button>
              );
            })}
          </div>
          <button
            onClick={running ? undefined : onClose}
            disabled={running}
            style={{
              background: 'none', border: 'none', cursor: running ? 'not-allowed' : 'pointer',
              color: SBAR_MUTED, fontSize: 18, lineHeight: 1,
            }}
          >✕</button>
        </div>

        {/* ── Zone d'ajout ── */}
        <div style={{
          padding: '12px 18px 10px', borderBottom: `1px solid ${CARD_BORDER}`,
          background: MAIN_BG, flexShrink: 0,
        }}>
          {/* Drag & drop */}
          <div
            onDragOver={onDragOver}
            onDrop={onDrop}
            style={{
              border: `2px dashed ${CARD_BORDER}`, borderRadius: 6,
              padding: '12px 16px', marginBottom: 8, textAlign: 'center',
              color: SBAR_MUTED, fontSize: 12, cursor: 'pointer',
              background: '#0a0e18',
            }}
            onClick={() => {
              const inp = document.createElement('input');
              inp.type = 'file'; inp.multiple = true;
              // No accept restriction: lets extension-less files through
              inp.onchange = () => onFileDrop(inp.files);
              inp.click();
            }}
          >
            📂  Drag & drop DICOM or MP4 files here, or click to select
            <div style={{ fontSize: 11, marginTop: 4, color: '#4a5568' }}>
              Accepts: <code>.dcm</code> · <code>.dicom</code> · files without extension (e.g. A0000) · <code>.mp4</code>
            </div>
          </div>
          <div style={{ marginBottom: 10, display: 'flex', gap: 6 }}>
            <button
              onClick={onPickFolder}
              style={{
                flex: 1, background: '#0a0e18',
                border: `1px dashed ${CARD_BORDER}`, borderRadius: 6,
                padding: '7px 16px', color: SBAR_MUTED, fontSize: 12,
                cursor: 'pointer', textAlign: 'center',
              }}
            >
              📁  Load DICOM folder
            </button>
            <button
              onClick={onPickMp4Files}
              style={{
                flex: 1, background: '#0a0e18',
                border: `1px dashed ${CARD_BORDER}`, borderRadius: 6,
                padding: '7px 16px', color: SBAR_MUTED, fontSize: 12,
                cursor: 'pointer', textAlign: 'center',
              }}
            >
              📹  Load MP4 files
            </button>
          </div>

          {/* Saisie chemin absolu */}
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              ref={pathRef}
              type="text"
              placeholder="/absolute/path/file.dcm"
              onKeyDown={e => { if (e.key === 'Enter') onAddPath(); }}
              style={{
                flex: 1, background: '#0a0e18', border: `1px solid ${CARD_BORDER}`,
                borderRadius: 4, padding: '5px 10px', color: SBAR_FG,
                fontSize: 12, outline: 'none',
              }}
            />
            <button
              onClick={onAddPath}
              style={{
                background: BLUE, border: 'none', borderRadius: 4, padding: '5px 12px',
                color: '#fff', fontSize: 12, cursor: 'pointer', fontWeight: 600,
              }}
            >Add</button>
          </div>
        </div>

        {/* ── Liste des fichiers ── */}
        <div style={{ flex: 1, overflowY: 'auto', background: MAIN_BG }}>
          {items.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: SBAR_MUTED, fontSize: 13 }}>
              No files added
            </div>
          ) : (
            items.map(item => (
              <BatchRow
                key={item.id}
                item={item}
                onRemove={() => removeItem(item.id)}
              />
            ))
          )}
        </div>

        {/* ── Pied de page ── */}
        <div style={{
          padding: '10px 18px', borderTop: `1px solid ${CARD_BORDER}`,
          background: SIDEBAR_BG, flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
        }}>
          {/* Stats */}
          <div style={{ fontSize: 12, color: SBAR_MUTED }}>
            {items.length > 0 && (
              <>
                <span style={{ color: SUCCESS_FG }}>{doneCount} ✓</span>
                {errCount > 0 && <span style={{ color: DANGER_FG }}> · {errCount} ✗</span>}
                {waitCount > 0 && <span> · {waitCount} en attente</span>}
              </>
            )}
            {done && errCount === 0 && doneCount > 0 && (
              <span style={{ color: SUCCESS_FG, marginLeft: 8 }}>Batch complete!</span>
            )}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8 }}>
            {doneCount > 0 && !running && (
              <>
                <button
                  onClick={exportJSON}
                  title="Download results + bounding boxes as JSON (reloadable)"
                  style={{
                    background: '#1e3a5f', border: '1px solid #1d4ed8',
                    borderRadius: 4, padding: '6px 14px',
                    color: '#93c5fd', fontSize: 12, cursor: 'pointer', fontWeight: 600,
                  }}
                >⬇  Export JSON</button>
                <button
                  onClick={exportCSV}
                  title="Download results as CSV"
                  style={{
                    background: '#14532d', border: '1px solid #166534',
                    borderRadius: 4, padding: '6px 14px',
                    color: '#86efac', fontSize: 12, cursor: 'pointer', fontWeight: 600,
                  }}
                >⬇  Export CSV</button>
              </>
            )}
            {running ? (
              <button
                onClick={cancel}
                style={{
                  background: '#7f1d1d', border: 'none', borderRadius: 4,
                  padding: '6px 16px', color: '#fca5a5', fontSize: 12,
                  cursor: 'pointer', fontWeight: 600,
                }}
              >⏹  Cancel</button>
            ) : (
              <>
                {/* Sélecteur de parallélisme */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginRight: 4 }}>
                  <span style={{ fontSize: 11, color: SBAR_MUTED, whiteSpace: 'nowrap' }}>Parallel:</span>
                  {([1, 2, 3, 4] as const).map(n => (
                    <button
                      key={n}
                      onClick={() => setConcurrency(n)}
                      title={n === 1 ? 'Sequential (1 at a time)' : `${n} simultaneous analyses`}
                      style={{
                        background: concurrency === n ? BLUE : 'transparent',
                        border: `1px solid ${concurrency === n ? BLUE : CARD_BORDER}`,
                        borderRadius: 3, padding: '2px 7px',
                        color: concurrency === n ? '#fff' : SBAR_MUTED,
                        fontSize: 11, cursor: 'pointer', fontWeight: concurrency === n ? 700 : 400,
                        minWidth: 24,
                      }}
                    >{n}</button>
                  ))}
                </div>
                <button
                  onClick={() => setItems([])}
                  disabled={items.length === 0}
                  style={{
                    background: 'transparent', border: `1px solid ${CARD_BORDER}`,
                    borderRadius: 4, padding: '6px 14px', color: SBAR_MUTED,
                    fontSize: 12, cursor: items.length === 0 ? 'not-allowed' : 'pointer',
                  }}
                >Clear</button>
                <button
                  onClick={runBatch}
                  disabled={items.filter(it => it.status === 'waiting' || it.status === 'error').length === 0}
                  style={{
                    background: BLUE, border: 'none', borderRadius: 4,
                    padding: '6px 18px', color: '#fff', fontSize: 12,
                    cursor: 'pointer', fontWeight: 700,
                    opacity: items.filter(it => it.status === 'waiting' || it.status === 'error').length === 0 ? 0.4 : 1,
                  }}
                >▶  Run batch ({items.filter(it => it.status === 'waiting' || it.status === 'error').length})</button>
              </>
            )}
          </div>
        </div>

        {/* ── Tableau récap (affiché quand au moins un item terminé) ── */}
        {doneCount > 0 && (
          <div style={{
            borderTop: `1px solid ${CARD_BORDER}`, background: '#080c14',
            padding: '10px 18px 14px', flexShrink: 0, maxHeight: 220, overflowY: 'auto',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: SBAR_MUTED, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                Summary
              </span>
              {!running && (() => {
                const doneItems = items.filter(it => it.status === 'done');
                const selItems  = doneItems.filter(it => selected.has(it.id));
                const toResult  = (it: BatchItem): BatchResultToOpen => ({
                  serverPath: it.serverPath, name: it.name,
                  detections: it.detections,
                  risk: it.riskScore !== undefined ? { score: it.riskScore, label: it.riskLabel ?? '' } : undefined,
                  numFrames: it.numFrames, roi: it.roi,
                  file: it.file, isMp4: it.isMp4,
                });
                const openAll = () => {
                  const results = doneItems.map(toResult);
                  if (results.length > 1 && onOpenInLayout) onOpenInLayout(results);
                  else results.forEach(r => onOpenInTab(r));
                };
                const openSel = () => {
                  const results = selItems.map(toResult);
                  if (results.length > 1 && onOpenInLayout) onOpenInLayout(results);
                  else results.forEach(r => onOpenInTab(r));
                };
                return (
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    {selItems.length > 0 && (
                      <button
                        onClick={openSel}
                        title={`Open ${selItems.length} selected file(s) in tabs`}
                        style={{
                          background: '#1e3a5f', border: '1px solid #1d4ed8',
                          borderRadius: 3, padding: '2px 10px',
                          color: '#93c5fd', fontSize: 11, cursor: 'pointer', fontWeight: 600,
                        }}
                      >↗ Open selection ({selItems.length})</button>
                    )}
                    <button
                      onClick={openAll}
                      title={`Open all ${doneItems.length} files in tabs`}
                      style={{
                        background: '#1c2a1c', border: '1px solid #166534',
                        borderRadius: 3, padding: '2px 10px',
                        color: '#86efac', fontSize: 11, cursor: 'pointer', fontWeight: 600,
                      }}
                    >↗ Open all ({doneItems.length})</button>
                    <button
                      onClick={exportJSON}
                      title="Download results + bounding boxes as JSON"
                      style={{
                        background: '#1e3a5f', border: '1px solid #1d4ed8',
                        borderRadius: 3, padding: '2px 10px',
                        color: '#93c5fd', fontSize: 11, cursor: 'pointer', fontWeight: 600,
                      }}
                    >⬇ JSON</button>
                    <button
                      onClick={exportCSV}
                      title="Download results as CSV"
                      style={{
                        background: '#14532d', border: '1px solid #166534',
                        borderRadius: 3, padding: '2px 10px',
                        color: '#86efac', fontSize: 11, cursor: 'pointer', fontWeight: 600,
                      }}
                    >⬇ CSV</button>
                  </div>
                );
              })()}
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ color: SBAR_MUTED }}>
                  <th style={{ padding: '3px 6px', width: 28, textAlign: 'center' }}>
                    <input
                      type="checkbox"
                      title="Select all / deselect all"
                      checked={items.filter(it => it.status === 'done').every(it => selected.has(it.id)) && items.some(it => it.status === 'done')}
                      onChange={e => {
                        const doneIds = items.filter(it => it.status === 'done').map(it => it.id);
                        setSelected(e.target.checked ? new Set(doneIds) : new Set());
                      }}
                      style={{ cursor: 'pointer', accentColor: '#3b82f6' }}
                    />
                  </th>
                  <th style={{ textAlign: 'left', padding: '3px 6px', fontWeight: 600 }}>File</th>
                  <th style={{ textAlign: 'center', padding: '3px 6px', fontWeight: 600 }}>HCC Risk</th>
                  <th style={{ textAlign: 'center', padding: '3px 6px', fontWeight: 600 }}>Score</th>
                  <th style={{ textAlign: 'center', padding: '3px 6px', fontWeight: 600 }}>Lesions</th>
                  <th style={{ textAlign: 'center', padding: '3px 6px', fontWeight: 600 }}>Open</th>
                </tr>
              </thead>
              <tbody>
                {items.filter(it => it.status === 'done').map(it => (
                  <tr key={it.id} style={{ borderTop: `1px solid ${CARD_BORDER}`, background: selected.has(it.id) ? '#0f1e38' : 'transparent' }}>
                    <td style={{ padding: '3px 6px', textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={selected.has(it.id)}
                        onChange={e => setSelected(prev => {
                          const next = new Set(prev);
                          e.target.checked ? next.add(it.id) : next.delete(it.id);
                          return next;
                        })}
                        style={{ cursor: 'pointer', accentColor: '#3b82f6' }}
                      />
                    </td>
                    <td style={{ padding: '3px 6px', color: SBAR_FG, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {it.name}
                    </td>
                    <td style={{ padding: '3px 6px', textAlign: 'center', fontWeight: 700, color: riskColor(it.riskLabel) }}>
                      {it.riskLabel ?? '—'}
                    </td>
                    <td style={{ padding: '3px 6px', textAlign: 'center', color: riskColor(it.riskLabel) }}>
                      {it.riskScore !== undefined ? `${(it.riskScore * 100).toFixed(1)} %` : '—'}
                    </td>
                    <td style={{ padding: '3px 6px', textAlign: 'center', color: it.detCount ? WARN_FG : SBAR_MUTED }}>
                      {it.detCount ?? 0}
                    </td>
                    <td style={{ padding: '3px 6px', textAlign: 'center' }}>
                      <button
                        onClick={() => onOpenInTab({
                          serverPath:  it.serverPath,
                          name:        it.name,
                          detections:  it.detections,
                          risk:        it.riskScore !== undefined
                                         ? { score: it.riskScore, label: it.riskLabel ?? '' }
                                         : undefined,
                          numFrames:   it.numFrames,
                          roi:         it.roi,
                          file:        it.file,
                        })}
                        title="Open in tab"
                        style={{
                          background: 'none', border: `1px solid ${CARD_BORDER}`,
                          borderRadius: 3, padding: '2px 8px', color: BLUE,
                          cursor: 'pointer', fontSize: 11,
                        }}
                      >→ Tab</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
