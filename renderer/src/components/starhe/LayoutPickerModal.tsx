// LayoutPickerModal.tsx — Layout picker for the STARHE multi-panel view
//
// Shown when the user opens several files simultaneously from the
// BatchModal. The user picks one of the 4 layouts then the multi-panel view
// opens (fixed layout — cannot be changed after selection).

import React from 'react';
import {
  CARD_BG, CARD_BORDER, SBAR_FG, SBAR_MUTED,
} from '../../utilities/starhe/colors';

// ── Exported type ─────────────────────────────────────────────────────────────

export type LayoutMode = 'single' | 'split-v' | 'split-h' | 'quad';

// ── SVG icons of the layouts ──────────────────────────────────────────────────

function LayoutIcon({ mode }: { mode: LayoutMode }) {
  const W = 64, H = 46, P = 4, G = 3, R = 2;
  const fill = '#1e3a5f', stroke = '#3b82f6';

  if (mode === 'single') {
    return (
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <rect x={P} y={P} width={W - P * 2} height={H - P * 2} rx={R} fill={fill} stroke={stroke} strokeWidth={1.2} />
      </svg>
    );
  }
  if (mode === 'split-v') {
    const hw = (W - P * 2 - G) / 2;
    return (
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <rect x={P}           y={P} width={hw} height={H - P * 2} rx={R} fill={fill} stroke={stroke} strokeWidth={1.2} />
        <rect x={P + hw + G}  y={P} width={hw} height={H - P * 2} rx={R} fill={fill} stroke={stroke} strokeWidth={1.2} />
      </svg>
    );
  }
  if (mode === 'split-h') {
    const hh = (H - P * 2 - G) / 2;
    return (
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <rect x={P} y={P}           width={W - P * 2} height={hh} rx={R} fill={fill} stroke={stroke} strokeWidth={1.2} />
        <rect x={P} y={P + hh + G}  width={W - P * 2} height={hh} rx={R} fill={fill} stroke={stroke} strokeWidth={1.2} />
      </svg>
    );
  }
  // quad
  const hw = (W - P * 2 - G) / 2;
  const hh = (H - P * 2 - G) / 2;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <rect x={P}          y={P}          width={hw} height={hh} rx={R} fill={fill} stroke={stroke} strokeWidth={1.2} />
      <rect x={P + hw + G} y={P}          width={hw} height={hh} rx={R} fill={fill} stroke={stroke} strokeWidth={1.2} />
      <rect x={P}          y={P + hh + G} width={hw} height={hh} rx={R} fill={fill} stroke={stroke} strokeWidth={1.2} />
      <rect x={P + hw + G} y={P + hh + G} width={hw} height={hh} rx={R} fill={fill} stroke={stroke} strokeWidth={1.2} />
    </svg>
  );
}

// ── Option data ───────────────────────────────────────────────────────────────

interface LayoutOption {
  mode:        LayoutMode;
  label:       string;
  description: string;
  slots:       number;
}

const OPTIONS: LayoutOption[] = [
  { mode: 'single',  label: '1 file',         description: 'Full screen',    slots: 1 },
  { mode: 'split-v', label: '2 side by side', description: 'Left / Right',   slots: 2 },
  { mode: 'split-h', label: '2 stacked',      description: 'Top / Bottom',   slots: 2 },
  { mode: 'quad',    label: '4 files',        description: '2×2 Grid',          slots: 4 },
];

// ── Component ────────────────────────────────────────────────────────────────

interface Props {
  /** Number of files the user wants to open */
  count: number;
  onPick:   (layout: LayoutMode) => void;
  onCancel: () => void;
}

export function LayoutPickerModal({ count, onPick, onCancel }: Props) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 3000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.72)',
      }}
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div
        style={{
          background: CARD_BG, border: `1px solid ${CARD_BORDER}`,
          borderRadius: 10, padding: '24px 26px',
          minWidth: 340, maxWidth: 420,
          boxShadow: '0 8px 32px rgba(0,0,0,0.65)',
        }}
      >
        {/* Titre */}
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: SBAR_FG, marginBottom: 5 }}>
            Panel layout
          </div>
          <div style={{ fontSize: 12, color: SBAR_MUTED }}>
            {count} file{count !== 1 ? 's' : ''} selected — choose how to display them.
            <br />
            <span style={{ color: '#64748b' }}>The layout is fixed after selection.</span>
          </div>
        </div>

        {/* Grille 2×2 des options */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
          {OPTIONS.map(opt => (
            <LayoutButton key={opt.mode} opt={opt} onPick={onPick} />
          ))}
        </div>

        {/* Annuler */}
        <button
          onClick={onCancel}
          style={{
            width: '100%', background: 'transparent',
            border: '1px solid #374151', borderRadius: 6,
            padding: '7px 0', color: SBAR_MUTED,
            fontSize: 12, cursor: 'pointer',
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function LayoutButton({ opt, onPick }: { opt: LayoutOption; onPick: (m: LayoutMode) => void }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      onClick={() => onPick(opt.mode)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background:   hover ? '#1e3a5f' : '#0d1b2a',
        border:       hover ? '1px solid #3b82f6' : '1px solid #1d4ed8',
        borderRadius: 8, padding: '12px 8px',
        cursor: 'pointer', display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: 7,
        transition: 'background 0.12s, border-color 0.12s',
      }}
    >
      <LayoutIcon mode={opt.mode} />
      <div style={{ fontSize: 12, fontWeight: 700, color: SBAR_FG }}>{opt.label}</div>
      <div style={{ fontSize: 10, color: SBAR_MUTED }}>{opt.description}</div>
    </button>
  );
}
