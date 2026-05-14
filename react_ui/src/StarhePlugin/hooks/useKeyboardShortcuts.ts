// hooks/useKeyboardShortcuts.ts — Raccourcis clavier du plugin STARHE
//
// Centralise tous les raccourcis clavier dans un seul hook.
// Extrait de index.tsx pour alléger le composant racine.
//
// Raccourcis actifs :
//   Espace        → play/pause
//   ← / →         → frame précédente / suivante
//   Shift+← / →   → ±10 frames
//   Home          → retour au début
//   P             → mode panoramique
//   M             → mode mesure
//   S             → mode série
//   R             → réinitialiser la vue
//   C             → dialogue contraste
//   L             → dialogue luminosité
//   Escape        → retour mode normal + déselection mesure
//   + / -         → vitesse lecture ×1.25 / ÷1.25
//   B             → toggle boucle
//   Ctrl+= / -    → zoom in / out
//   Ctrl+0        → zoom 100 %
//   Ctrl+Tab      → onglet suivant du même patient
//   Ctrl+W        → fermer l'onglet actif

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
      // Ne pas intercepter si un champ de saisie est actif
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

      // Ctrl+Tab — onglet suivant/précédent du même patient
      if ((e.metaKey || e.ctrlKey) && e.key === 'Tab') {
        e.preventDefault();
        if (activePatientIdx >= 0 && patients[activePatientIdx]) {
          const ptTabs = patients[activePatientIdx].tabIds;
          const curPos = ptTabs.findIndex(id => id === activeTab?.id) ?? 0;
          const nextId = ptTabs[(curPos + (e.shiftKey ? -1 : 1) + ptTabs.length) % ptTabs.length];
          if (nextId) switchTab(nextId);
        }
      }

      // Ctrl+W — fermer l'onglet actif
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
