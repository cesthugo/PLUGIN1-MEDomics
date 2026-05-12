// LayoutPickerModal.tsx — Sélecteur de disposition pour la vue multi-panneaux STARHE
//
// Affiché lorsque l'utilisateur ouvre plusieurs fichiers simultanément depuis le
// BatchModal. L'utilisateur choisit un des 4 layouts puis la vue multi-panneaux
// s'ouvre (disposition fixe — ne peut pas être modifiée après sélection).

import React from 'react';
import {
  CARD_BG, CARD_BORDER, SBAR_FG, SBAR_MUTED,
} from '../colors';

// ── Type exporté ─────────────────────────────────────────────────────────────

export type LayoutMode = 'single' | 'split-v' | 'split-h' | 'quad';

// ── Icônes SVG des layouts ───────────────────────────────────────────────────

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

// ── Données des options ──────────────────────────────────────────────────────

interface LayoutOption {
  mode:        LayoutMode;
  label:       string;
  description: string;
  slots:       number;
}

const OPTIONS: LayoutOption[] = [
  { mode: 'single',  label: '1 fichier',     description: 'Vue plein écran',  slots: 1 },
  { mode: 'split-v', label: '2 côte à côte', description: 'Gauche / Droite',  slots: 2 },
  { mode: 'split-h', label: '2 superposés',  description: 'Haut / Bas',       slots: 2 },
  { mode: 'quad',    label: '4 fichiers',    description: 'Grille 2×2',       slots: 4 },
];

// ── Composant ────────────────────────────────────────────────────────────────

interface Props {
  /** Nombre de fichiers que l'utilisateur souhaite ouvrir */
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
            Disposition des panneaux
          </div>
          <div style={{ fontSize: 12, color: SBAR_MUTED }}>
            {count} fichier{count !== 1 ? 's' : ''} sélectionné{count !== 1 ? 's' : ''} — choisissez comment les afficher.
            <br />
            <span style={{ color: '#64748b' }}>La disposition est fixe après sélection.</span>
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
          Annuler
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
