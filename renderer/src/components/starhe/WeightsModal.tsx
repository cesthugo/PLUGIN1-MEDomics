// WeightsModal.tsx — Local provisioning of the STARHE AI model weights.
//
// The .pth checkpoints are not bundled with the plugin. This modal lets the
// user pick each STARHE model's weight from their own computer and load it.
// RISK and DETECT are two independent models, each with its own weight file —
// they are listed and loaded separately.
//
// Opened automatically when an analysis is launched while a required weight is
// missing, and on demand from the sidebar's "Model weights" button.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  SIDEBAR_BG, BLUE, SBAR_FG, SBAR_MUTED, SUCCESS_FG, DANGER_FG, WARN_FG,
} from '../../utilities/starhe/colors';
import { getWeightsStatus, uploadWeight, type WeightStatus } from '../../utilities/starhe/api';

interface Props {
  onClose: () => void;
  /** Called after a weight is successfully loaded (lets the parent react). */
  onChanged?: () => void;
}

// Per-model transient UI state (selected file, upload progress, messages).
interface RowState {
  file:      File | null;
  uploading: boolean;
  progress:  number;
  error:     string | null;
  warning:   string | null;
}

const EMPTY_ROW: RowState = { file: null, uploading: false, progress: 0, error: null, warning: null };

export function WeightsModal({ onClose, onChanged }: Props) {
  const [status, setStatus] = useState<WeightStatus[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [rows, setRows] = useState<Record<string, RowState>>({});

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await getWeightsStatus());
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => { refreshStatus(); }, [refreshStatus]);

  const patchRow = (id: string, patch: Partial<RowState>) =>
    setRows(prev => ({ ...prev, [id]: { ...EMPTY_ROW, ...prev[id], ...patch } }));

  const onLoad = useCallback(async (id: string) => {
    const row = rows[id];
    if (!row?.file) return;
    patchRow(id, { uploading: true, progress: 0, error: null, warning: null });
    try {
      const res = await uploadWeight(id, row.file, pct => patchRow(id, { progress: pct }));
      patchRow(id, { uploading: false, file: null, warning: res.warning ?? null });
      await refreshStatus();
      onChanged?.();
    } catch (err) {
      patchRow(id, { uploading: false, error: err instanceof Error ? err.message : String(err) });
    }
  }, [rows, refreshStatus, onChanged]);

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 3000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.72)',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: SIDEBAR_BG, border: '1px solid #2a2d45',
          borderRadius: 10, width: 460, maxWidth: '92vw',
          boxShadow: '0 8px 32px rgba(0,0,0,0.65)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '14px 16px', borderBottom: '1px solid #24263c',
        }}>
          <span style={{ fontSize: 16 }}>🧠</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: SBAR_FG }}>STARHE model weights</div>
            <div style={{ fontSize: 11, color: SBAR_MUTED, marginTop: 2 }}>
              Load each model's <code style={{ color: '#93c5fd' }}>.pth</code> checkpoint from your computer.
            </div>
          </div>
          <button
            onClick={onClose}
            title="Close"
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: SBAR_MUTED, fontSize: 18, lineHeight: 1, padding: 4,
            }}
          >✕</button>
        </div>

        {/* Body */}
        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {loadError && (
            <div style={{ fontSize: 12, color: DANGER_FG }}>
              Could not read weights status: {loadError}
            </div>
          )}
          {status === null && !loadError && (
            <div style={{ fontSize: 12, color: SBAR_MUTED }}>Checking weights…</div>
          )}
          {status?.map(m => (
            <WeightRow
              key={m.id}
              model={m}
              row={rows[m.id] ?? EMPTY_ROW}
              onPickFile={file => patchRow(m.id, { file, error: null, warning: null })}
              onLoad={() => onLoad(m.id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ── One model row ─────────────────────────────────────────────────────────────

function WeightRow({
  model, row, onPickFile, onLoad,
}: {
  model: WeightStatus;
  row: RowState;
  onPickFile: (file: File) => void;
  onLoad: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div style={{
      background: '#0d1220', border: '1px solid #1e2740',
      borderRadius: 8, padding: 12,
    }}>
      {/* Name + status badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: SBAR_FG }}>{model.name}</div>
          <div style={{ fontSize: 10, color: SBAR_MUTED, fontFamily: "'Consolas', monospace" }}>
            {model.file}
          </div>
        </div>
        <span style={{
          fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 999,
          color: model.present ? SUCCESS_FG : DANGER_FG,
          background: model.present ? 'rgba(74,222,128,0.12)' : 'rgba(248,113,113,0.12)',
          border: `1px solid ${model.present ? 'rgba(74,222,128,0.4)' : 'rgba(248,113,113,0.4)'}`,
        }}>
          {model.present ? '● Loaded' : '○ Not loaded'}
        </span>
      </div>

      {/* File picker + Load */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input
          ref={inputRef}
          type="file"
          accept=".pth"
          style={{ display: 'none' }}
          onChange={e => { const f = e.target.files?.[0]; if (f) onPickFile(f); }}
        />
        <button
          onClick={() => inputRef.current?.click()}
          disabled={row.uploading}
          style={{
            flex: 1, minWidth: 0, textAlign: 'left',
            background: '#0a0e18', border: '1px solid #2a3245', borderRadius: 5,
            padding: '6px 10px', color: row.file ? SBAR_FG : SBAR_MUTED,
            fontSize: 11, cursor: row.uploading ? 'default' : 'pointer',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
          title={row.file?.name ?? 'Choose a .pth file'}
        >
          {row.file ? `📄 ${row.file.name}` : '📁 Choose .pth file…'}
        </button>
        <button
          onClick={onLoad}
          disabled={!row.file || row.uploading}
          style={{
            background: (!row.file || row.uploading) ? '#1a2a3f' : BLUE,
            border: 'none', borderRadius: 5, padding: '6px 16px',
            color: (!row.file || row.uploading) ? '#5b6b82' : '#fff',
            fontSize: 12, fontWeight: 700,
            cursor: (!row.file || row.uploading) ? 'default' : 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {row.uploading ? 'Loading…' : 'Load'}
        </button>
      </div>

      {/* Progress bar */}
      {row.uploading && (
        <div style={{ marginTop: 8, height: 5, background: '#1e2740', borderRadius: 3, overflow: 'hidden' }}>
          <div style={{
            width: `${row.progress}%`, height: '100%', background: BLUE,
            transition: 'width 0.15s',
          }} />
        </div>
      )}

      {/* Messages */}
      {row.error && (
        <div style={{ marginTop: 6, fontSize: 11, color: DANGER_FG }}>⚠ {row.error}</div>
      )}
      {row.warning && (
        <div style={{ marginTop: 6, fontSize: 11, color: WARN_FG }}>⚠ {row.warning}</div>
      )}
    </div>
  );
}
