// components/MultiPanelView.tsx — Vue multi-panneaux (split-v / split-h / quad)
//
// Supporte :
//  - 2 panneaux côte à côte (split-v), 2 panneaux empilés (split-h), grille 2×2 (quad)
//  - Redimensionnement par glisser-déposer des séparateurs (poignées)
//  - Drag & drop d'onglets depuis la bande de vignettes vers les panneaux
//  - Zone d'expansion : déposer un fichier pour passer à la disposition supérieure
//  - Panneau actif (interactions activées) / panneau inactif (clic pour activer)

import React from 'react';
import { DicomCanvas } from './DicomCanvas';
import type { TabState, Measure } from '../types';
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

  // Resize state — colSplit/rowSplit are percentages [10, 90]
  const [colSplit, setColSplit] = React.useState(50);
  const [rowSplit, setRowSplit] = React.useState(50);
  const [resizing, setResizing] = React.useState<'col' | 'row' | null>(null);
  const gridRef = React.useRef<HTMLDivElement>(null);

  // Reset splits when layout changes
  React.useEffect(() => { setColSplit(50); setRowSplit(50); }, [layout]);

  // Ref stable pour onResetAllPanelsPan — évite les closures périmées dans l'effet de resize.
  const onResetAllPanelsPanRef = React.useRef(onResetAllPanelsPan);
  onResetAllPanelsPanRef.current = onResetAllPanelsPan;

  // Global mouse move/up for resize drag
  React.useEffect(() => {
    if (!resizing) return;
    const onMove = (e: MouseEvent) => {
      const el = gridRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (resizing === 'col') {
        setColSplit(Math.max(10, Math.min(90, (e.clientX - rect.left) / rect.width  * 100)));
      } else {
        setRowSplit(Math.max(10, Math.min(90, (e.clientY - rect.top)  / rect.height * 100)));
      }
    };
    const onUp = () => { setResizing(null); onResetAllPanelsPanRef.current(); };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup',   onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup',   onUp);
    };
  }, [resizing]);

  const c = colSplit; const r = rowSplit;
  const gridStyle: React.CSSProperties =
    layout === 'split-v' ? { gridTemplateColumns: `${c}fr ${100-c}fr` } :
    layout === 'split-h' ? { gridTemplateRows:    `${r}fr ${100-r}fr` } :
    layout === 'quad'    ? { gridTemplateColumns: `${c}fr ${100-c}fr`, gridTemplateRows: `${r}fr ${100-r}fr` } :
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

      {/* Grille de panneaux — avec zones de dépôt drag & drop + redimensionnement */}
      <div
        ref={gridRef}
        style={{
          flex: 1, display: 'grid', ...gridStyle,
          gap: 2, background: '#000',
          overflow: 'hidden', minHeight: 0,
          position: 'relative',
          cursor: resizing === 'col' ? 'col-resize' : resizing === 'row' ? 'row-resize' : 'default',
          userSelect: resizing ? 'none' : 'auto',
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
              {/* Canvas du panneau.
                 - panneau non-focalisé → pointerEvents: none  (overlay de focus actif)
                 - resize du séparateur en cours → pointerEvents: none sur TOUS les panneaux
                   pour que les events souris ne fuient pas sur le canvas pendant le drag
                   et n'accumulent pas de décalage de pan via un dragRef éventuellement actif.
              */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', pointerEvents: (isFocused && !resizing) ? 'auto' : 'none' }}>
                {tab ? (
                  <DicomCanvas
                    tab={resizing ? { ...tab, panX: 0, panY: 0 } : tab}
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

        {/* ── Poignées de redimensionnement ──────────────────────────────── */}

        {/* Séparateur vertical — split-v et quad */}
        {(layout === 'split-v' || layout === 'quad') && (
          <div
            title="Glisser pour redimensionner"
            style={{
              position: 'absolute', top: 0, bottom: 0,
              left: `calc(${colSplit}% - 5px)`, width: 10,
              cursor: 'col-resize', zIndex: 20,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            onMouseDown={e => { e.preventDefault(); setResizing('col'); }}
          >
            <div style={{
              width: resizing === 'col' ? 3 : 2,
              height: resizing === 'col' ? '90%' : '60%',
              background: resizing === 'col' ? '#3b82f6' : 'rgba(100,116,139,0.5)',
              borderRadius: 2,
              transition: 'height 0.15s, background 0.15s, width 0.15s',
              pointerEvents: 'none',
            }} />
          </div>
        )}

        {/* Séparateur horizontal — split-h et quad */}
        {(layout === 'split-h' || layout === 'quad') && (
          <div
            title="Glisser pour redimensionner"
            style={{
              position: 'absolute', left: 0, right: 0,
              top: `calc(${rowSplit}% - 5px)`, height: 10,
              cursor: 'row-resize', zIndex: 20,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            onMouseDown={e => { e.preventDefault(); setResizing('row'); }}
          >
            <div style={{
              height: resizing === 'row' ? 3 : 2,
              width: resizing === 'row' ? '90%' : '60%',
              background: resizing === 'row' ? '#3b82f6' : 'rgba(100,116,139,0.5)',
              borderRadius: 2,
              transition: 'width 0.15s, background 0.15s, height 0.15s',
              pointerEvents: 'none',
            }} />
          </div>
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
