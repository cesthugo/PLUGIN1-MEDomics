// components/ContextMenu.tsx — Menu contextuel clic droit du canvas
//
// Réplique _show_context_menu de prototype_tkinter.py.

import React, { useEffect, useRef } from 'react';
import type { ContextMenuItem, ViewMode } from '../../utilities/starhe/types';
import { SIDEBAR_BG, SBAR_FG, BLUE } from '../../utilities/starhe/colors';

export interface ContextMenuProps {
  x:       number;
  y:       number;
  items:   ContextMenuItem[];
  onClose: () => void;
}

export function ContextMenu({ x, y, items, onClose }: ContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  // Ferme sur clic extérieur ou Échap
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('mousedown', onClick);
    window.addEventListener('keydown',   onKey);
    return () => {
      window.removeEventListener('mousedown', onClick);
      window.removeEventListener('keydown',   onKey);
    };
  }, [onClose]);

  // Ajuste la position pour ne pas sortir de l'écran
  const left = Math.min(x, window.innerWidth  - 220);
  const top  = Math.min(y, window.innerHeight - items.length * 32 - 8);

  return (
    <div
      ref={ref}
      style={{
        position: 'fixed',
        left, top,
        minWidth: 210,
        background: SIDEBAR_BG,
        border: '1px solid #2a2a4e',
        borderRadius: 4,
        boxShadow: '0 4px 16px rgba(0,0,0,0.6)',
        zIndex: 9999,
        overflow: 'hidden',
        fontFamily: "'Segoe UI', system-ui, sans-serif",
      }}
    >
      {items.map((item, i) => {
        if (item.separator) {
          return <div key={i} style={{ borderTop: '1px solid #2a2a4e', margin: '2px 0' }} />;
        }
        return (
          <button
            key={i}
            onClick={() => { item.onClick(); onClose(); }}
            style={{
              display: 'block', width: '100%',
              background: 'transparent',
              border: 'none', cursor: 'pointer',
              padding: '7px 14px',
              textAlign: 'left',
              fontSize: 12,
              color: SBAR_FG,
              fontFamily: "'Segoe UI', system-ui, sans-serif",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = BLUE)}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            {item.checked ? '✓  ' : '    '}{item.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Helper : construit les items du menu contextuel principal du canvas ──────

export function buildCanvasContextMenu({
  viewMode,
  onTogglePan,
  onToggleMeasure,
  onToggleSeries,
  onContrast,
  onBrightness,
  onResetView,
}: {
  viewMode:        ViewMode;
  onTogglePan:     () => void;
  onToggleMeasure: () => void;
  onToggleSeries:  () => void;
  onContrast:      () => void;
  onBrightness:    () => void;
  onResetView:     () => void;
}): ContextMenuItem[] {
  return [
    { label: 'Pan / Zoom',        onClick: onTogglePan,     checked: viewMode === 'pan' },
    { label: 'Measure',           onClick: onToggleMeasure,  checked: viewMode === 'measure' },
    { label: '', onClick: () => {}, separator: true },
    { label: 'Contrast…',         onClick: onContrast },
    { label: 'Brightness…',       onClick: onBrightness },
    { label: '', onClick: () => {}, separator: true },
    { label: 'Series Scroll',     onClick: onToggleSeries,  checked: viewMode === 'series' },
    { label: '', onClick: () => {}, separator: true },
    { label: 'Reset view',           onClick: onResetView },
  ];
}
