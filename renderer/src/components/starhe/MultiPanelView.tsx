// components/MultiPanelView.tsx — Vue multi-panneaux (split-v / split-h / quad)
//
// Supporte :
//  - 2 panneaux côte à côte (split-v), 2 panneaux empilés (split-h), grille 2×2 (quad)
//  - Séparateurs fixes 50/50 (non déplaçables)
//  - Drag & drop d'onglets depuis la bande de vignettes vers les panneaux
//  - Zone d'expansion : déposer un fichier pour passer à la disposition supérieure
//  - Panneau actif (interactions activées) / panneau inactif (clic pour activer)

import React from 'react';
import { DicomCanvas } from './DicomCanvas';
import type { TabState, Measure } from '../../utilities/starhe/types';
import type { LayoutMode } from './LayoutPickerModal';

export interface MultiPanelViewProps {
  layout:             LayoutMode;
  tabIds:             number[];
  tabs:               TabState[];
  activeTabId:        number;
  onFocusPanel:       (tabId: number) => void;
  onExit:             () => void;
  onDropToPanel:      (slotIdx: number, tabId: number) => void;
  onExpandLayout:     (tabId: number) => void;
  onRemovePanel:      (slotIdx: number) => void;
  onZoomPan:          (zoom: number, panX: number, panY: number) => void;
  onResetAllPanelsPan: () => void;
  onContrastBright:   (contrast: number, brightness: number) => void;
  onFrameChange:      (idx: number) => void;
  onMeasureAdd:       (frameIdx: number, measure: Measure) => void;
  onMeasureMove:      (frameIdx: number, segIdx: number, newPts: [[number, number], [number, number]]) => void;
  onMeasureLabelMove: (frameIdx: number, segIdx: number, labelOffset: [number, number]) => void;
  onMeasureSelect:    (frameIdx: number, segIdx: number | null) => void;
  onContextMenu:      (x: number, y: number) => void;
}

export function MultiPanelView({
  layout, tabIds, tabs, activeTabId,
  onFocusPanel, onExit, onDropToPanel, onExpandLayout, onRemovePanel,
  onZoomPan, onResetAllPanelsPan, onContrastBright, onFrameChange,
  onMeasureAdd, onMeasureMove, onMeasureLabelMove, onMeasureSelect, onContextMenu,
}: MultiPanelViewProps) {
  const slots = layout === 'quad' ? 4 : layout === 'single' ? 1 : 2;
  const [dragOverSlot,   setDragOverSlot]   = React.useState<number | null>(null);
  const [dragDepth,      setDragDepth]      = React.useState(0);
  const [dragOverExpand, setDragOverExpand] = React.useState(false);

  // Séparateurs fixes 50/50 — non déplaçables
  const gridStyle: React.CSSProperties =
    layout === 'split-v' ? { gridTemplateColumns: '1fr 1fr' } :
    layout === 'split-h' ? { gridTemplateRows:    '1fr 1fr' } :
    layout === 'quad'    ? { gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr' } :
    {};

  // Stable no-op callbacks for unfocused panels (avoid unnecessary re-renders)
  const NOOP_ZP  = React.useCallback(() => {}, []);
  const NOOP_CB  = React.useCallback(() => {}, []);
  const NOOP_FC  = React.useCallback((_: number) => {}, []);
  const NOOP_MA  = React.useCallback((_a: number, _b: Measure) => {}, []);
  const NOOP_MM  = React.useCallback((_a: number, _b: number, _c: [[number,number],[number,number]]) => {}, []);
  const NOOP_LM  = React.useCallback((_a: number, _b: number, _c: [number,number]) => {}, []);
  const NOOP_MS  = React.useCallback((_a: number, _b: number | null) => {}, []);
  const NOOP_CTX = React.useCallback((_a: number, _b: number) => {}, []);

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>

      {/* Barre d'en-tête du mode multi-panneaux */}
      <div style={{
        display: 'flex', alignItems: 'center', height: 28, flexShrink: 0,
        background: '#0b1320', borderBottom: '1px solid #0a0a14',
        padding: '0 10px', gap: 8,
      }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: '#475569', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Vue multiple
        </span>
        <span style={{ fontSize: 10, color: '#334155' }}>
          {layout === 'split-v' ? 'Gauche / Droite' : layout === 'split-h' ? 'Haut / Bas' : 'Grille 2×2'}
        </span>
        <button
          onClick={onExit}
          title="Quitter la vue multiple et revenir à la vue normale"
          style={{
            marginLeft: 'auto', background: 'transparent',
            border: '1px solid #374151', borderRadius: 4,
            color: '#94a3b8', fontSize: 10, fontWeight: 600,
            padding: '2px 8px', cursor: 'pointer',
          }}
          onMouseEnter={e => (e.currentTarget.style.borderColor = '#ef4444')}
          onMouseLeave={e => (e.currentTarget.style.borderColor = '#374151')}
        >
          ✕ Quitter
        </button>
      </div>

      {/* Grille de panneaux — avec zones de dépôt drag & drop */}
      <div
        style={{
          flex: 1, display: 'grid', ...gridStyle,
          gap: 2, background: '#000',
          overflow: 'hidden', minHeight: 0,
          position: 'relative',
        }}
        onDragEnter={() => setDragDepth(d => d + 1)}
        onDragLeave={() => setDragDepth(d => d - 1)}
        onDrop={() => setDragDepth(0)}
      >
        {Array.from({ length: slots }, (_, i) => {
          const tabId      = tabIds[i];
          const tab        = tabId !== undefined && tabId >= 0 ? tabs.find(t => t.id === tabId) ?? null : null;
          const isFocused  = tabId !== undefined && tabId === activeTabId;
          const isDragTarget = dragOverSlot === i;

          return (
            <div
              key={i}
              style={{
                position: 'relative', overflow: 'hidden',
                display: 'flex', flexDirection: 'column',
                outline: isDragTarget
                  ? '2px solid #f59e0b'
                  : isFocused ? '2px solid #3b82f6' : '1px solid #0a0a14',
                outlineOffset: (isDragTarget || isFocused) ? '-2px' : '-1px',
                background: isDragTarget ? 'rgba(245,158,11,0.08)' : 'transparent',
                transition: 'outline 0.1s, background 0.1s',
              }}
              onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setDragOverSlot(i); }}
              onDragEnter={e => { e.preventDefault(); setDragOverSlot(i); }}
              onDragLeave={() => setDragOverSlot(null)}
              onDrop={e => {
                e.preventDefault();
                e.stopPropagation();
                setDragOverSlot(null);
                const raw = e.dataTransfer.getData('text/plain');
                if (!raw.startsWith('starhe-tab:')) return;
                const droppedId = parseInt(raw.replace('starhe-tab:', ''), 10);
                onDropToPanel(i, droppedId);
              }}
            >
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', pointerEvents: isFocused ? 'auto' : 'none' }}>
                {tab ? (
                  <DicomCanvas
                    tab={tab}
                    onZoomPan={isFocused          ? onZoomPan          : NOOP_ZP}
                    onPanReset={onResetAllPanelsPan}
                    onContrastBright={isFocused   ? onContrastBright   : NOOP_CB}
                    onFrameChange={isFocused      ? onFrameChange      : NOOP_FC}
                    onMeasureAdd={isFocused       ? onMeasureAdd       : NOOP_MA}
                    onMeasureMove={isFocused      ? onMeasureMove      : NOOP_MM}
                    onMeasureLabelMove={isFocused ? onMeasureLabelMove : NOOP_LM}
                    onMeasureSelect={isFocused    ? onMeasureSelect    : NOOP_MS}
                    onContextMenu={isFocused      ? onContextMenu      : NOOP_CTX}
                  />
                ) : (
                  <div style={{
                    flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: '#080d14',
                  }}>
                    <span style={{ color: isDragTarget ? '#f59e0b' : '#1e293b', fontSize: 12 }}>
                      {isDragTarget ? '⊕ Déposer ici' : 'Panneau vide'}
                    </span>
                  </div>
                )}
              </div>

              {/* Overlay de sélection (panneau non-actif) */}
              {!isFocused && tab && !isDragTarget && (
                <div
                  onClick={() => onFocusPanel(tabId!)}
                  style={{ position: 'absolute', inset: 0, cursor: 'pointer', background: 'rgba(0,0,0,0.06)' }}
                >
                  <span style={{
                    position: 'absolute', bottom: 6, right: 6,
                    fontSize: 10, color: '#64748b',
                    background: 'rgba(0,0,0,0.6)', padding: '2px 5px', borderRadius: 3,
                    pointerEvents: 'none',
                  }}>
                    Cliquer pour activer
                  </span>
                </div>
              )}

              {/* Indicateur de dépôt sur panneau occupé */}
              {isDragTarget && tab && (
                <div style={{
                  position: 'absolute', inset: 0, pointerEvents: 'none',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: 'rgba(245,158,11,0.18)',
                }}>
                  <span style={{
                    fontSize: 13, fontWeight: 700, color: '#fbbf24',
                    background: 'rgba(0,0,0,0.7)', padding: '4px 10px', borderRadius: 4,
                  }}>⇄ Remplacer</span>
                </div>
              )}

              {/* Badge nom du fichier */}
              {tab && !isDragTarget && (
                <div style={{
                  position: 'absolute', top: 4, left: 4, zIndex: 5,
                  pointerEvents: 'none',
                  fontSize: 10, color: '#94a3b8',
                  background: 'rgba(0,0,0,0.55)', padding: '1px 6px', borderRadius: 3,
                  maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {tab.label}
                </div>
              )}

              {/* Bouton fermer le panneau (haut droite) */}
              {tab && (
                <button
                  title="Fermer ce panneau"
                  onClick={e => { e.stopPropagation(); onRemovePanel(i); }}
                  style={{
                    position: 'absolute', top: 4, right: 4, zIndex: 15,
                    width: 18, height: 18,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: 'rgba(0,0,0,0.55)',
                    border: '1px solid rgba(100,116,139,0.4)',
                    borderRadius: 3, color: '#94a3b8',
                    fontSize: 10, fontWeight: 700,
                    cursor: 'pointer', lineHeight: 1, padding: 0,
                    transition: 'background 0.12s, color 0.12s, border-color 0.12s',
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'rgba(239,68,68,0.85)';
                    (e.currentTarget as HTMLButtonElement).style.color = '#fff';
                    (e.currentTarget as HTMLButtonElement).style.borderColor = '#ef4444';
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,0,0,0.55)';
                    (e.currentTarget as HTMLButtonElement).style.color = '#94a3b8';
                    (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(100,116,139,0.4)';
                  }}
                >
                  ✕
                </button>
              )}
            </div>
          );
        })}

        {/* ── Séparateurs fixes (non déplaçables) ────────────────────────── */}

        {/* Séparateur vertical — split-v et quad */}
        {(layout === 'split-v' || layout === 'quad') && (
          <div style={{
            position: 'absolute', top: 0, bottom: 0,
            left: 'calc(50% - 1px)', width: 2,
            background: 'rgba(100,116,139,0.4)',
            pointerEvents: 'none', zIndex: 20,
          }} />
        )}

        {/* Séparateur horizontal — split-h et quad */}
        {(layout === 'split-h' || layout === 'quad') && (
          <div style={{
            position: 'absolute', left: 0, right: 0,
            top: 'calc(50% - 1px)', height: 2,
            background: 'rgba(100,116,139,0.4)',
            pointerEvents: 'none', zIndex: 20,
          }} />
        )}
      </div>

      {/* Zone d'expansion — visible lors d'un glisser quand <4 panneaux */}
      {dragDepth > 0 && slots < 4 && (
        <div
          style={{
            height: dragOverExpand ? 44 : 26,
            flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: dragOverExpand ? '#0f2040' : '#080d14',
            borderTop: dragOverExpand ? '1px solid #f59e0b' : '1px solid #0a0a14',
            cursor: 'copy', fontSize: 11,
            color: dragOverExpand ? '#fbbf24' : '#475569',
            transition: 'all 0.15s', gap: 6,
          }}
          onDragEnter={e => { e.stopPropagation(); setDragOverExpand(true); }}
          onDragLeave={() => setDragOverExpand(false)}
          onDragOver={e => { e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect = 'copy'; }}
          onDrop={e => {
            e.preventDefault(); e.stopPropagation();
            setDragDepth(0); setDragOverExpand(false);
            const raw = e.dataTransfer.getData('text/plain');
            if (!raw.startsWith('starhe-tab:')) return;
            const tabId = parseInt(raw.replace('starhe-tab:', ''), 10);
            onExpandLayout(tabId);
          }}
        >
          <span style={{ fontSize: 14 }}>⊕</span>
          <span>{dragOverExpand ? 'Déposer pour ajouter un panneau' : 'Glisser ici pour agrandir la vue'}</span>
        </div>
      )}
    </div>
  );
}
