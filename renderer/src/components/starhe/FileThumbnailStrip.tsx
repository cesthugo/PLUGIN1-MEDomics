// components/FileThumbnailStrip.tsx — Thumbnail strip of the DICOM files
//
// Replaces the former FileTabBar (text tabs) with visual thumbnails
// grouped by study date, with drag & drop support to the multi-panel view.

import React from 'react';
import { TAB_BG } from '../../utilities/starhe/colors';
import type { TabState } from '../../utilities/starhe/types';

export function FileThumbnailStrip({
  tabs,
  activeTabId,
  onSwitchTab,
  onCloseTab,
  onOpenNew,
}: {
  tabs:        TabState[];
  activeTabId: number;
  onSwitchTab: (id: number) => void;
  onCloseTab:  (id: number) => void;
  onOpenNew:   () => void;
}) {
  // Group the tabs by date (part before " · " in the label)
  const groups = React.useMemo(() => {
    const map = new Map<string, TabState[]>();
    for (const tab of tabs) {
      const dateKey = tab.label.includes(' · ') ? tab.label.split(' · ')[0] : '—';
      if (!map.has(dateKey)) map.set(dateKey, []);
      map.get(dateKey)!.push(tab);
    }
    return Array.from(map.entries());
  }, [tabs]);

  const multiGroup = groups.length > 1;

  if (!tabs.length) {
    return (
      <div style={{
        height: 32, minHeight: 32, background: TAB_BG,
        borderTop: '1px solid #0a0a14',
        display: 'flex', alignItems: 'center', flexShrink: 0,
      }}>
        <button
          onClick={onOpenNew}
          style={{ background: 'none', color: '#374151', border: 'none', cursor: 'pointer', fontSize: 16, fontWeight: 700, padding: '0 10px' }}
          title="Add a file"
        >+</button>
      </div>
    );
  }

  return (
    <div style={{
      background: '#0c0f18',
      borderTop: '1px solid #0a0a14',
      display: 'flex',
      alignItems: 'flex-start',
      minHeight: 100,
      flexShrink: 0,
      overflowX: 'auto',
      overflowY: 'hidden',
      padding: '6px 6px 4px',
      gap: 8,
    }}>
      {groups.map(([dateKey, groupTabs]) => (
        <div key={dateKey} style={{ display: 'flex', flexDirection: 'column', gap: 3, flexShrink: 0 }}>
          {/* En-tête de groupe (date) — affiché si plusieurs groupes OU groupe avec >1 fichier */}
          {(multiGroup || groupTabs.length > 1) && (
            <div style={{
              fontSize: 9, fontWeight: 600, color: '#475569',
              textAlign: 'center', letterSpacing: '0.03em',
              padding: '0 2px',
              borderBottom: '1px solid #1e293b',
              marginBottom: 2,
            }}>
              {dateKey}
            </div>
          )}
          {/* Rangée de vignettes du groupe */}
          <div style={{ display: 'flex', gap: 4 }}>
            {groupTabs.map(tab => {
              const active     = tab.id === activeTabId;
              const firstFrame = tab.data?.framesB64?.[0];
              const labelParts = tab.label.split(' · ');
              const shortName  = labelParts.length > 1 ? labelParts.slice(1).join(' · ') : tab.label;

              return (
                <div
                  key={tab.id}
                  title={tab.label}
                  draggable={true}
                  onDragStart={e => {
                    e.dataTransfer.setData('text/plain', `starhe-tab:${tab.id}`);
                    e.dataTransfer.effectAllowed = 'move';
                    (e.currentTarget as HTMLElement).style.opacity = '0.5';
                  }}
                  onDragEnd={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
                  onClick={() => onSwitchTab(tab.id)}
                  style={{
                    position: 'relative',
                    width: 70, minWidth: 70,
                    display: 'flex', flexDirection: 'column', alignItems: 'stretch',
                    cursor: 'pointer',
                    borderRadius: 4,
                    border: active ? '2px solid #3b82f6' : '2px solid #1e293b',
                    background: active ? '#0f1e35' : '#111827',
                    overflow: 'hidden', flexShrink: 0,
                    transition: 'border-color 0.12s, background 0.12s',
                  }}
                  onMouseEnter={e => { if (!active) (e.currentTarget as HTMLElement).style.borderColor = '#334155'; }}
                  onMouseLeave={e => { if (!active) (e.currentTarget as HTMLElement).style.borderColor = '#1e293b'; }}
                >
                  {/* Vignette — première frame JPEG */}
                  <div style={{
                    width: '100%', height: 58,
                    background: '#050810',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    overflow: 'hidden', flexShrink: 0,
                  }}>
                    {firstFrame ? (
                      <img
                        src={`data:image/jpeg;base64,${firstFrame}`}
                        alt={shortName}
                        style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                      />
                    ) : (
                      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                        <rect x="1" y="1" width="18" height="18" rx="2" fill="#1e293b" />
                        <path d="M6 10h8M10 6v8" stroke="#334155" strokeWidth="1.5" strokeLinecap="round" />
                      </svg>
                    )}
                  </div>

                  {/* Nom de fichier */}
                  <div style={{
                    padding: '2px 3px',
                    fontSize: 9,
                    color: active ? '#cbd5e1' : '#6b7280',
                    textAlign: 'center',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    background: active ? '#0f1e35' : 'transparent',
                    flexShrink: 0,
                  }}>
                    {shortName}
                  </div>

                  {/* Bouton fermer */}
                  <button
                    onClick={e => { e.stopPropagation(); onCloseTab(tab.id); }}
                    title="Fermer"
                    style={{
                      position: 'absolute', top: 2, right: 2,
                      background: 'rgba(0,0,0,0.55)',
                      border: 'none', borderRadius: 2,
                      color: '#64748b', fontSize: 9, lineHeight: 1,
                      padding: '1px 3px', cursor: 'pointer',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.color = '#ef4444')}
                    onMouseLeave={e => (e.currentTarget.style.color = '#64748b')}
                  >×</button>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Bouton ajouter un fichier */}
      <div
        onClick={onOpenNew}
        title="Open a new DICOM file"
        style={{
          width: 28, minWidth: 28, alignSelf: 'stretch',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', color: '#374151', fontSize: 20, fontWeight: 700,
          borderRadius: 4, border: '1px dashed #1e293b',
          transition: 'color 0.12s, border-color 0.12s, background 0.12s',
          flexShrink: 0,
          marginTop: groups.length > 1 || (groups[0]?.[1].length ?? 0) > 1 ? 16 : 0,
        }}
        onMouseEnter={e => {
          (e.currentTarget as HTMLElement).style.color = '#7eb8f7';
          (e.currentTarget as HTMLElement).style.borderColor = '#3b82f6';
          (e.currentTarget as HTMLElement).style.background = '#0f1e35';
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLElement).style.color = '#374151';
          (e.currentTarget as HTMLElement).style.borderColor = '#1e293b';
          (e.currentTarget as HTMLElement).style.background = 'transparent';
        }}
      >+</div>
    </div>
  );
}
