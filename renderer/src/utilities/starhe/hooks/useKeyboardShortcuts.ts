// hooks/useKeyboardShortcuts.ts — STARHE plugin keyboard shortcuts
//
// Centralizes all the keyboard shortcuts in a single hook.
// Extracted from index.tsx to lighten the root component.
//
// Active shortcuts:
//   Space         → play/pause
//   ← / →         → previous / next frame
//   Shift+← / →   → ±10 frames
//   Home          → back to the start
//   P             → pan mode
//   M             → measure mode
//   S             → series mode
//   R             → reset the view
//   C             → contrast dialog
//   L             → brightness dialog
//   Escape        → back to normal mode + measure deselection
//   + / -         → playback speed ×1.25 / ÷1.25
//   B             → toggle loop
//   Ctrl+= / -    → zoom in / out
//   Ctrl+0        → zoom 100 %
//   Ctrl+Tab      → next tab of the same patient
//   Ctrl+W        → close the active tab

import { useEffect } from 'react';
import type { TabState, ViewMode, Patient } from '../types';

export interface UseKeyboardShortcutsParams {
  activeTab:         TabState | null;
  activePatientIdx:  number;
  patients:          Patient[];
  switchTab:         (id: number) => void;
  closeTab:          (id: number) => void;
  onTogglePlay:      () => void;
  onPrevFrame:       () => void;
  onNextFrame:       () => void;
  onResetVideo:      () => void;
  onToggleViewMode:  (mode: ViewMode) => void;
  onResetView:       () => void;
  updateActiveTab:   (updater: (t: TabState) => TabState) => void;
  setShowContrast:   (fn: (v: boolean) => boolean) => void;
  setShowBrightness: (fn: (v: boolean) => boolean) => void;
}

export function useKeyboardShortcuts({
  activeTab, activePatientIdx, patients,
  switchTab, closeTab,
  onTogglePlay, onPrevFrame, onNextFrame, onResetVideo,
  onToggleViewMode, onResetView, updateActiveTab,
  setShowContrast, setShowBrightness,
}: UseKeyboardShortcutsParams): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Do not intercept if an input field is active
      const focused = document.activeElement;
      if (focused && ['INPUT', 'TEXTAREA'].includes((focused as HTMLElement).tagName)) return;

      switch (e.key) {
        case ' ':           e.preventDefault(); onTogglePlay(); break;
        case 'ArrowLeft':   if (!e.shiftKey) { e.preventDefault(); onPrevFrame(); } break;
        case 'ArrowRight':  if (!e.shiftKey) { e.preventDefault(); onNextFrame(); } break;
        case 'Home':        e.preventDefault(); onResetVideo(); break;
        case 'p': case 'P': onToggleViewMode('pan');     break;
        case 'm': case 'M': onToggleViewMode('measure'); break;
        case 's': case 'S': onToggleViewMode('series');  break;
        case 'r': case 'R': onResetView(); break;
        case 'c': case 'C': setShowContrast(v => !v); break;
        case 'l': case 'L': setShowBrightness(v => !v); break;
        case 'Escape':
          updateActiveTab(t => ({ ...t, viewMode: 'normal', selectedMeasure: null }));
          break;
        case '+': case '=':
          if (!e.metaKey && !e.ctrlKey)
            updateActiveTab(t => ({ ...t, speedMult: Math.min(3, t.speedMult * 1.25) }));
          break;
        case '-':
          if (!e.metaKey && !e.ctrlKey)
            updateActiveTab(t => ({ ...t, speedMult: Math.max(0.25, t.speedMult * 0.8) }));
          break;
        case 'b': case 'B':
          updateActiveTab(t => ({ ...t, loop: !t.loop })); break;
      }

      // Zoom Ctrl+= / Ctrl+-
      if ((e.metaKey || e.ctrlKey) && e.key === '=') {
        e.preventDefault();
        updateActiveTab(t => ({ ...t, zoom: Math.min(10, t.zoom * 1.25) }));
      }
      if ((e.metaKey || e.ctrlKey) && e.key === '-') {
        e.preventDefault();
        updateActiveTab(t => ({ ...t, zoom: Math.max(0.1, t.zoom / 1.25) }));
      }
      if ((e.metaKey || e.ctrlKey) && e.key === '0') {
        e.preventDefault();
        updateActiveTab(t => ({ ...t, zoom: 1, panX: 0, panY: 0 }));
      }

      // Ctrl+Tab — next/previous tab of the same patient
      if ((e.metaKey || e.ctrlKey) && e.key === 'Tab') {
        e.preventDefault();
        if (activePatientIdx >= 0 && patients[activePatientIdx]) {
          const ptTabs = patients[activePatientIdx].tabIds;
          const curPos = ptTabs.findIndex(id => id === activeTab?.id) ?? 0;
          const nextId = ptTabs[(curPos + (e.shiftKey ? -1 : 1) + ptTabs.length) % ptTabs.length];
          if (nextId) switchTab(nextId);
        }
      }

      // Ctrl+W — close the active tab
      if ((e.metaKey || e.ctrlKey) && e.key === 'w') {
        if (activeTab) closeTab(activeTab.id);
      }

      // Shift+← / Shift+→ — ±10 frames
      if (e.shiftKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        if (activeTab?.data) {
          updateActiveTab(t => ({ ...t, frameIdx: Math.max(0, t.frameIdx - 10) }));
        }
      }
      if (e.shiftKey && e.key === 'ArrowRight') {
        e.preventDefault();
        if (activeTab?.data) {
          updateActiveTab(t => ({ ...t, frameIdx: Math.min(activeTab.data!.frameCount - 1, t.frameIdx + 10) }));
        }
      }
    };

    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [
    onTogglePlay, onPrevFrame, onNextFrame, onResetVideo,
    onToggleViewMode, onResetView, updateActiveTab, activeTab,
    activePatientIdx, patients, switchTab, closeTab,
  ]);
}
