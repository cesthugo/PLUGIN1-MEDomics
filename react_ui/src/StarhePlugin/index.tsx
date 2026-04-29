// StarhePlugin/index.tsx — Composant racine du plugin STARHE pour MEDomics
//
// Réplique intégrale de prototype_tkinter.py (STARHEApp) en React :
//   - Barre de titre sombre MEDomics
//   - Sidebar gauche (270 px) : contrôles + résultats
//   - Zone centrale claire : visionneuse DICOM + console log
//   - Barre patients (haut de la carte) + barre onglets fichiers (bas)
//   - Multi-onglets / multi-patients
//   - Playback avec multiplicateur de vitesse
//   - Pan / Zoom / Mesure / Series Scroll
//   - Contraste / Luminosité (dialogues flottants + clic droit)
//   - Menu contextuel clic droit
//   - Analyse IA via SSE (pipeline STARHE)
//   - Cache MongoDB (réinitialisation)
//   - Thème clair / sombre
//   - Fenêtre "Analyse en direct"
//   - Raccourcis clavier (Espace, ←/→, P, M, S, R, C, L, ±, B, Ctrl+0/+/-)

import React, {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';

import type {
  TabState, Patient, LogEntry, LogLevel, ViewMode, Measure,
} from './types';
import {
  SIDEBAR_BG, SIDEBAR_HOV, MAIN_BG, CARD_BG, CARD_BORDER, CARD_SHADOW,
  BLUE, BLUE_TEXT, SBAR_FG, SBAR_MUTED, BORDER, CANVAS_BG,
  PTAB_BG, PTAB_ACT_BG, TAB_BG, TAB_ACT_BG,
} from './colors';
import { loadDicom, loadDicomFile, deleteCache, makeTabLabel } from './api';
import { usePipelineSSE } from './hooks/usePipelineSSE';
import { usePlayback }    from './hooks/usePlayback';
import { useDisplaySettings, DISPLAY_DEFAULTS } from './hooks/useDisplaySettings';
import { Sidebar }        from './components/Sidebar';
import { DicomCanvas }    from './components/DicomCanvas';
import { ConsolePanel }   from './components/ConsolePanel';
import { AdjustDialog }   from './components/AdjustDialog';
import { ContextMenu, buildCanvasContextMenu } from './components/ContextMenu';
import { LiveModal }      from './components/LiveModal';
import { SettingsPanel }       from './components/SettingsPanel';
import { DetectionGallery }    from './components/DetectionGallery';

// ── ID auto-incrémenté ────────────────────────────────────────────────────────
let _nextTabId = 1;
const nextTabId = () => _nextTabId++;
let _nextLogId = 1;
const nextLogId = () => _nextLogId++;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeDefaultTab(): TabState {
  return {
    id:              nextTabId(),
    label:           '—',
    patientName:     'Patient inconnu',
    dicomPath:       '',
    data:            null,
    frameIdx:        0,
    detectionsBy:    {},
    resultsBy:       {},
    measuresByFrame: {},
    selectedMeasure: null,
    zoom:            1,
    panX:            0,
    panY:            0,
    contrast:        1,
    brightness:      0,
    viewMode:        'normal',
    speedMult:       1,
    loop:            true,
  };
}

// ── Composant principal ───────────────────────────────────────────────────────

export interface StarhePluginProps {
  /** Couleur de fond de la zone principale (surcharge thème) */
  mainBg?: string;
  /** Hauteur totale (défaut : 100vh) */
  height?: string | number;
  /** Largeur totale (défaut : 100%) */
  width?: string | number;
}

export function StarhePlugin({ mainBg, height = '100vh', width = '100%' }: StarhePluginProps) {
  // ── Onglets et patients ────────────────────────────────────────────────────
  const [tabs,             setTabs]            = useState<TabState[]>([]);
  const [activeTabId,      setActiveTabId]     = useState<number>(-1);
  const [patients,         setPatients]        = useState<Patient[]>([]);
  const [activePatientName, setActivePatientName] = useState<string>('');

  // Ref pour lire l'état courant dans closeTab (lecture synchrone hors updater)
  const tabsRef     = useRef<TabState[]>(tabs);
  tabsRef.current   = tabs;
  const patientsRef = useRef<Patient[]>(patients);
  patientsRef.current = patients;

  // Dérivés : calculés à chaque render à partir des IDs stables
  const activeTabIdx = tabs.findIndex(t => t.id === activeTabId);
  const activeTab    = activeTabIdx >= 0 ? tabs[activeTabIdx] : null;
  const activePatientIdx = patients.findIndex(p => p.name === activePatientName);

  // ── Lecture vidéo ──────────────────────────────────────────────────────────
  const [isPlaying, setIsPlaying] = useState(false);

  const handleFrameChange = useCallback((idx: number) => {
    setTabs(prev => prev.map(t => t.id === activeTabId ? { ...t, frameIdx: idx } : t));
  }, [activeTabId]);

  const handleStop = useCallback(() => setIsPlaying(false), []);

  usePlayback({
    frameCount:    activeTab?.data?.frameCount ?? 0,
    baseFps:       activeTab?.data?.baseFps    ?? 22,
    speedMult:     activeTab?.speedMult        ?? 1,
    loop:          activeTab?.loop             ?? true,
    playing:       isPlaying,
    frameIdx:      activeTab?.frameIdx         ?? 0,
    onFrameChange: handleFrameChange,
    onStop:        handleStop,
  });

  // ── Log ────────────────────────────────────────────────────────────────────
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const addLog = useCallback((message: string, level: LogLevel = 'info') => {
    setLogs(prev => [...prev.slice(-200), { id: nextLogId(), level, message }]);
  }, []);

  // ── Pipeline SSE ───────────────────────────────────────────────────────────
  const { status: analysisStatus, progress, startAnalysis, cancelAnalysis, lastResult }
    = usePipelineSSE(addLog);

  // Onglet pour lequel l'analyse a été lancée (ID stable, indépendant de l'onglet actif)
  const [analysisTargetTabId, setAnalysisTargetTabId] = useState<number>(-1);

  // Quand un résultat arrive, l'injecter dans l'onglet *cible* (pas nécessairement l'actif)
  useEffect(() => {
    if (!lastResult || analysisTargetTabId < 0) return;
    setTabs(prev => prev.map(t => {
      if (t.id !== analysisTargetTabId) return t;
      return {
        ...t,
        detectionsBy: { ...t.detectionsBy, original: lastResult.detectionsPerFrame },
        resultsBy:    { ...t.resultsBy,    original: lastResult.result },
      };
    }));
  }, [lastResult, analysisTargetTabId]);

  // ── Réglages d'affichage (persistés dans localStorage) ────────────────────
  const { settings: displaySettings, updateSettings, resetSettings } = useDisplaySettings();
  const [showSettings, setShowSettings] = useState(false);
  // ── Injection CSS dynamique (taille + police + couleur du texte) ─────────────────
  // Principe : sélecteurs CSS [style*="font-size: Npx"] + !important pour scaler
  // proportionnellement toutes les tailles inline sans toucher au layout.
  const styleContent = useMemo(() => {
    const s  = displaySettings.fontScale;
    const ff = displaySettings.fontFamily;
    // Tailles px utilisées dans l'interface — scaler chacune proportionnellement
    const sizes = [9, 10, 11, 12, 13, 14, 16, 18, 20, 22];
    const fontSizeRules = sizes
      .map(n => `.starhe-root [style*="font-size: ${n}px"] { font-size: ${(n * s).toFixed(1)}px !important; }`)
      .join('\n');
    // textColor : injecté seulement si différent du défaut (sinon on écraserait les couleurs sémantiques)
    const colorRule = displaySettings.textColor !== DISPLAY_DEFAULTS.textColor
      ? `.starhe-root * { color: ${displaySettings.textColor} !important; }`
      : '';
    return [
      `.starhe-root, .starhe-root * { font-family: ${ff} !important; }`,
      fontSizeRules,
      colorRule,
    ].join('\n');
  }, [displaySettings.fontScale, displaySettings.fontFamily, displaySettings.textColor]);

  useEffect(() => {
    let el = document.getElementById('starhe-dynamic-styles') as HTMLStyleElement | null;
    if (!el) {
      el = document.createElement('style');
      el.id = 'starhe-dynamic-styles';
      document.head.appendChild(el);
    }
    el.textContent = styleContent;
  }, [styleContent]);
  // ── Thème ──────────────────────────────────────────────────────────────────
  const [darkMode, setDarkMode] = useState(false);
  const effectiveMainBg = mainBg ?? (darkMode ? '#1a1a2e' : displaySettings.mainBg);
  const cardBg = darkMode ? '#16213e' : CARD_BG;
  const cardTitleFg = darkMode ? '#89b4fa' : BLUE_TEXT;

  // ── Dialogues contraste / luminosité ──────────────────────────────────────
  const [showContrast,   setShowContrast]   = useState(false);
  const [showBrightness, setShowBrightness] = useState(false);

  // ── Menu contextuel ────────────────────────────────────────────────────────
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number } | null>(null);

  // ── Fenêtre live ───────────────────────────────────────────────────────────
  const [showLive, setShowLive] = useState(false);

  // ── Chargement DICOM ───────────────────────────────────────────────────────
  const [loadingPaths, setLoadingPaths] = useState<Set<string>>(new Set());

  // Détection Electron (file.path disponible uniquement dans ce contexte)
  const isElectron = typeof window !== 'undefined' &&
    ((window as any).process?.type === 'renderer' ||
     navigator.userAgent.includes('Electron'));

  // ── Injection d'un onglet après chargement réussi ─────────────────────────
  const addTab = useCallback((
    displayName: string,
    dicomPath:   string,
    data:        import('./types').DicomData,
  ) => {
    const label  = makeTabLabel(data.studyDate, data.fileName);
    const newTab: TabState = {
      ...makeDefaultTab(),
      label,
      patientName: data.patientName,
      dicomPath,
      data,
    };
    // Functional updaters : chaque appel reçoit le résultat du précédent (React batchs)
    // → sûr même si plusieurs fichiers chargent simultanément avant le prochain render
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(newTab.id);  // ID stable — pas d'index périmé
    setPatients(prev => {
      const existIdx = prev.findIndex(p => p.name === data.patientName);
      if (existIdx >= 0) {
        const updated = [...prev];
        updated[existIdx] = { ...updated[existIdx], tabIds: [...updated[existIdx].tabIds, newTab.id] };
        return updated;
      }
      return [...prev, { name: data.patientName, tabIds: [newTab.id] }];
    });
    setActivePatientName(data.patientName);
    addLog(`DICOM chargé — ${data.frameCount} frame(s), ${data.rows}×${data.cols} px.`, 'success');
  }, [addLog]);

  // Chargement par chemin absolu (Electron ou saisie manuelle)
  const doLoadPath = useCallback(async (path: string, displayName: string) => {
    if (loadingPaths.has(path)) return;
    setLoadingPaths(prev => new Set([...prev, path]));
    addLog(`Chargement : ${displayName}`, 'info');
    try {
      const data = await loadDicom(path);
      addTab(displayName, path, data);
    } catch (err: unknown) {
      addLog(`ERREUR chargement ${displayName} : ${(err as Error).message}`, 'error');
    } finally {
      setLoadingPaths(prev => { const next = new Set(prev); next.delete(path); return next; });
    }
  }, [addLog, addTab, loadingPaths]);

  // Chargement par upload d'octets (navigateur standard sans Electron)
  const doLoadFile = useCallback(async (file: File) => {
    if (loadingPaths.has(file.name)) return;
    setLoadingPaths(prev => new Set([...prev, file.name]));
    addLog(`Chargement : ${file.name}`, 'info');
    try {
      const data = await loadDicomFile(file);
      addTab(file.name, data.serverPath || file.name, data);
    } catch (err: unknown) {
      addLog(`ERREUR chargement ${file.name} : ${(err as Error).message}`, 'error');
    } finally {
      setLoadingPaths(prev => { const next = new Set(prev); next.delete(file.name); return next; });
    }
  }, [addLog, addTab, loadingPaths]);

  // Chargement via explorateur de fichiers
  const onLoadDicom = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.onchange = async () => {
      for (const file of Array.from(input.files ?? [])) {
        if (isElectron) {
          // Electron expose le chemin absolu réel
          const path = (file as File & { path?: string }).path ?? file.name;
          await doLoadPath(path, file.name);
        } else {
          // Navigateur standard : upload des octets
          await doLoadFile(file);
        }
      }
    };
    input.click();
  }, [isElectron, doLoadPath, doLoadFile]);

  // Chargement par chemin absolu tapé manuellement (mode dev / Electron avancé)
  const onLoadPath = useCallback((path: string) => {
    const name = path.split(/[\\/]/).pop() ?? path;
    doLoadPath(path, name);
  }, [doLoadPath]);

  // ── Navigation ────────────────────────────────────────────────────────────

  const updateActiveTab = useCallback((updater: (t: TabState) => TabState) => {
    setTabs(prev => prev.map(t => t.id === activeTabId ? updater(t) : t));
  }, [activeTabId]);

  const onPrevFrame = useCallback(() => {
    if (!activeTab?.data) return;
    if (isPlaying) setIsPlaying(false);
    const n = activeTab.data.frameCount;
    updateActiveTab(t => ({ ...t, frameIdx: (t.frameIdx - 1 + n) % n }));
  }, [activeTab, isPlaying, updateActiveTab]);

  const onNextFrame = useCallback(() => {
    if (!activeTab?.data) return;
    if (isPlaying) setIsPlaying(false);
    const n = activeTab.data.frameCount;
    updateActiveTab(t => ({ ...t, frameIdx: (t.frameIdx + 1) % n }));
  }, [activeTab, isPlaying, updateActiveTab]);

  const onTogglePlay = useCallback(() => {
    if (!activeTab?.data) return;
    setIsPlaying(p => !p);
  }, [activeTab]);

  const onFrameScale = useCallback((idx: number) => {
    if (isPlaying) setIsPlaying(false);
    updateActiveTab(t => ({ ...t, frameIdx: idx }));
  }, [isPlaying, updateActiveTab]);

  const onSpeedChange = useCallback((v: number) =>
    updateActiveTab(t => ({ ...t, speedMult: v })), [updateActiveTab]);

  const onLoopChange = useCallback((v: boolean) =>
    updateActiveTab(t => ({ ...t, loop: v })), [updateActiveTab]);

  const onResetVideo = useCallback(() => {
    if (isPlaying) setIsPlaying(false);
    updateActiveTab(t => ({ ...t, frameIdx: 0 }));
  }, [isPlaying, updateActiveTab]);

  // ── Analyse ────────────────────────────────────────────────────────────────

  const onRunPipeline = useCallback(() => {
    if (!activeTab?.data) return;
    if (analysisStatus === 'running') return;
    const mode = displaySettings.analysisMode;
    setAnalysisTargetTabId(activeTab.id);  // figer la cible avant le lancement
    startAnalysis({
      dicomPath:    activeTab.dicomPath,
      runRisk:      mode !== 'detect_only',
      runDetection: mode !== 'risk_only',
    });
  }, [activeTab, analysisStatus, startAnalysis, displaySettings.analysisMode]);

  const onResetAnalysis = useCallback(async () => {
    if (!activeTab?.dicomPath) return;
    const ok = window.confirm(
      `Supprimer les résultats STARHE en cache pour :\n${activeTab.dicomPath} ?`
    );
    if (!ok) return;
    try {
      const { deleted } = await deleteCache(activeTab.dicomPath);
      addLog(`✓  Résultat MongoDB supprimé (${deleted} doc).`, 'success');
    } catch {
      addLog('⚠  Aucun résultat en cache à supprimer.', 'warning');
    }
    updateActiveTab(t => ({
      ...t,
      detectionsBy: {},
      resultsBy:    {},
    }));
  }, [activeTab, addLog, updateActiveTab]);

  const onGotoFrame = useCallback((idx: number) => {
    if (isPlaying) setIsPlaying(false);
    updateActiveTab(t => ({ ...t, frameIdx: idx }));
  }, [isPlaying, updateActiveTab]);

  // ── Vue canvas ─────────────────────────────────────────────────────────────

  const onZoomPan = useCallback((zoom: number, panX: number, panY: number) =>
    updateActiveTab(t => ({ ...t, zoom, panX, panY })), [updateActiveTab]);

  const onContrastBright = useCallback((contrast: number, brightness: number) =>
    updateActiveTab(t => ({ ...t, contrast, brightness })), [updateActiveTab]);

  const onCanvasFrameChange = useCallback((idx: number) => {
    if (isPlaying) setIsPlaying(false);
    updateActiveTab(t => ({ ...t, frameIdx: idx }));
  }, [isPlaying, updateActiveTab]);

  // ── Mesures ────────────────────────────────────────────────────────────────

  const onMeasureAdd = useCallback((frameIdx: number, measure: Measure) => {
    updateActiveTab(t => {
      const frames = { ...t.measuresByFrame };
      frames[frameIdx] = [...(frames[frameIdx] ?? []), measure];
      return { ...t, measuresByFrame: frames };
    });
  }, [updateActiveTab]);

  const onMeasureMove = useCallback(
    (frameIdx: number, segIdx: number, newPts: [[number,number],[number,number]]) => {
      updateActiveTab(t => {
        const frames = { ...t.measuresByFrame };
        const segs   = [...(frames[frameIdx] ?? [])];
        // Convention : pts nulles = suppression
        if (newPts[0][0] === -1) {
          segs.splice(segIdx, 1);
        } else {
          segs[segIdx] = { ...segs[segIdx], pts: newPts }; // préserve labelOffset
        }
        frames[frameIdx] = segs;
        return { ...t, measuresByFrame: frames };
      });
    }, [updateActiveTab]);

  const onMeasureLabelMove = useCallback(
    (frameIdx: number, segIdx: number, labelOffset: [number, number]) => {
      updateActiveTab(t => {
        const frames = { ...t.measuresByFrame };
        const segs   = [...(frames[frameIdx] ?? [])];
        if (segs[segIdx]) {
          segs[segIdx] = { ...segs[segIdx], labelOffset };
          frames[frameIdx] = segs;
        }
        return { ...t, measuresByFrame: frames };
      });
    }, [updateActiveTab]);

  const onMeasureSelect = useCallback((frameIdx: number, segIdx: number | null) => {
    updateActiveTab(t => ({ ...t, selectedMeasure: segIdx }));
  }, [updateActiveTab]);

  // ── Mode vue ───────────────────────────────────────────────────────────────

  const onToggleViewMode = useCallback((mode: ViewMode) => {
    updateActiveTab(t => ({
      ...t,
      viewMode: t.viewMode === mode ? 'normal' : mode,
    }));
  }, [updateActiveTab]);

  const onResetView = useCallback(() => {
    updateActiveTab(t => ({
      ...t, zoom: 1, panX: 0, panY: 0, contrast: 1, brightness: 0, viewMode: 'normal',
    }));
  }, [updateActiveTab]);

  // ── Onglets ────────────────────────────────────────────────────────────────

  const switchTab = useCallback((tabId: number) => {
    if (!tabsRef.current.some(t => t.id === tabId)) return;
    if (isPlaying) setIsPlaying(false);
    setActiveTabId(tabId);
    const patient = patientsRef.current.find(p => p.tabIds.includes(tabId));
    if (patient) setActivePatientName(patient.name);
  }, [isPlaying]);

  const closeTab = useCallback((tabId: number) => {
    const currentTabs = tabsRef.current;
    // Pas de side effects dans les updaters (évite le double-appel React StrictMode)
    if (currentTabs.length <= 1) {
      setTabs([]);
      setActiveTabId(-1);
      setPatients([]);
      setActivePatientName('');
      setIsPlaying(false);
      return;
    }
    const idx = currentTabs.findIndex(t => t.id === tabId);
    const next = currentTabs.filter(t => t.id !== tabId);
    const newActiveTab = next[Math.max(0, Math.min(idx, next.length - 1))];
    setTabs(next);
    setActiveTabId(newActiveTab?.id ?? -1);
    const updatedPatients = patientsRef.current
      .map(p => ({ ...p, tabIds: p.tabIds.filter(id => id !== tabId) }))
      .filter(p => p.tabIds.length > 0);
    setPatients(updatedPatients);
    const newPatient = updatedPatients.find(p => p.tabIds.includes(newActiveTab?.id ?? -1));
    if (newPatient) setActivePatientName(newPatient.name);
  }, []);

  // ── Raccourcis clavier ─────────────────────────────────────────────────────

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const focused = document.activeElement;
      if (focused && ['INPUT', 'TEXTAREA'].includes((focused as HTMLElement).tagName)) return;

      switch (e.key) {
        case ' ':           e.preventDefault(); onTogglePlay(); break;
        case 'ArrowLeft':   e.preventDefault(); onPrevFrame(); break;
        case 'ArrowRight':  e.preventDefault(); onNextFrame(); break;
        case 'Home':        e.preventDefault(); onResetVideo(); break;
        case 'p': case 'P': onToggleViewMode('pan');     break;
        case 'm': case 'M': onToggleViewMode('measure'); break;
        case 's': case 'S': onToggleViewMode('series');  break;
        case 'r': case 'R': onResetView(); break;
        case 'c': case 'C': setShowContrast(v => !v); break;
        case 'l': case 'L': setShowBrightness(v => !v); break;
        case 'Escape':
          updateActiveTab(t => ({
            ...t,
            viewMode: 'normal',
            selectedMeasure: null,
          }));
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
      if ((e.metaKey || e.ctrlKey) && e.key === '=') {
        e.preventDefault();
        updateActiveTab(t => {
          const newZ = Math.min(10, t.zoom * 1.25);
          return { ...t, zoom: newZ };
        });
      }
      if ((e.metaKey || e.ctrlKey) && e.key === '-') {
        e.preventDefault();
        updateActiveTab(t => {
          const newZ = Math.max(0.1, t.zoom / 1.25);
          return { ...t, zoom: newZ };
        });
      }
      if ((e.metaKey || e.ctrlKey) && e.key === '0') {
        e.preventDefault();
        updateActiveTab(t => ({ ...t, zoom: 1, panX: 0, panY: 0 }));
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Tab') {
        e.preventDefault();
        if (activePatientIdx >= 0 && patients[activePatientIdx]) {
          const ptTabs = patients[activePatientIdx].tabIds;
          const curPos = ptTabs.findIndex(id => id === activeTab?.id) ?? 0;
          const nextId = ptTabs[(curPos + (e.shiftKey ? -1 : 1) + ptTabs.length) % ptTabs.length];
          if (nextId) switchTab(nextId);
        }
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'w') {
        if (activeTab) closeTab(activeTab.id);
      }
      // Shift+← / Shift+→ : ±10 frames
      if (e.shiftKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        if (activeTab?.data) {
          const n = activeTab.data.frameCount;
          updateActiveTab(t => ({ ...t, frameIdx: Math.max(0, t.frameIdx - 10) }));
        }
      }
      if (e.shiftKey && e.key === 'ArrowRight') {
        e.preventDefault();
        if (activeTab?.data) {
          const n = activeTab.data.frameCount;
          updateActiveTab(t => ({ ...t, frameIdx: Math.min(n - 1, t.frameIdx + 10) }));
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

  // ── Patient actif : tabs associés ──────────────────────────────────────────
  const activePatient = activePatientIdx >= 0 ? patients[activePatientIdx] : null;
  // patientTabs : onglets fichiers du patient actif, dans l'ordre des tabs (pas tabIds)
  const activePatientTabIds = new Set(activePatient?.tabIds ?? []);
  const patientTabs = tabs.filter(t => activePatientTabIds.has(t.id));

  // ── Rendu ─────────────────────────────────────────────────────────────────

  return (
    <div
      className="starhe-root"
      style={{
        width, height,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* ── Header MEDomics ──────────────────────────────────────────────── */}
      <div
        style={{
          background: displaySettings.sidebarBg, height: 50, minHeight: 50,
          display: 'flex', alignItems: 'center', flexShrink: 0,
          borderBottom: '1px solid #0a0a14',
        }}
      >
        <div
          style={{
            width: 38, height: 38, background: BLUE, borderRadius: 6,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginLeft: 10, fontSize: 18, fontWeight: 700, color: '#fff',
          }}
        >
          M
        </div>
        <span style={{ color: '#7c8899', fontSize: 20, marginLeft: 8, marginRight: 4 }}>│</span>
        <span style={{ color: displaySettings.textColor, fontSize: 13 }}>Plugin1 Hugo — STARHE</span>
        <span style={{ color: '#7c8899', fontSize: 9, marginLeft: 8 }}>v0.1.0-prototype</span>

        {/* Bouton Réglages — haut droite */}
        <div style={{ marginLeft: 'auto', paddingRight: 12 }}>
          <button
            onClick={() => setShowSettings(v => !v)}
            title="Réglages d'affichage"
            style={{
              background: showSettings ? SIDEBAR_HOV : 'none',
              border: '1px solid ' + (showSettings ? '#3a4860' : 'transparent'),
              borderRadius: 5,
              cursor: 'pointer',
              color: displaySettings.textColor,
              fontSize: 12,
              fontWeight: 600,
              padding: '5px 10px',
              display: 'flex', alignItems: 'center', gap: 5,
              transition: 'background 0.15s, border-color 0.15s',
            }}
            onMouseEnter={e => { if (!showSettings) (e.currentTarget as HTMLElement).style.background = '#1e1d2f'; }}
            onMouseLeave={e => { if (!showSettings) (e.currentTarget as HTMLElement).style.background = 'none'; }}
          >
            ⚙&nbsp;Réglages
          </button>
        </div>
      </div>

      {/* ── Corps : sidebar + zone principale ─────────────────────────────── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Sidebar */}
        <Sidebar
          tab={activeTab}
          analysisStatus={analysisStatus}
          darkMode={darkMode}
          sidebarBg={displaySettings.sidebarBg}
          textColor={displaySettings.textColor}
          analysisMode={displaySettings.analysisMode}
          onLoadDicom={onLoadDicom}
          onLoadPath={onLoadPath}
          onPrevFrame={onPrevFrame}
          onNextFrame={onNextFrame}
          onTogglePlay={onTogglePlay}
          isPlaying={isPlaying}
          onFrameScale={onFrameScale}
          onSpeedChange={onSpeedChange}
          onLoopChange={onLoopChange}
          onResetVideo={onResetVideo}
          onRunPipeline={onRunPipeline}
          onResetAnalysis={onResetAnalysis}
          onOpenLive={() => setShowLive(true)}
          onGotoFrame={onGotoFrame}
          onToggleTheme={() => setDarkMode(d => !d)}
        />

        {/* Séparateur 1 px */}
        <div style={{ width: 1, background: '#0a0a14', flexShrink: 0 }} />

        {/* Zone principale */}
        <div
          style={{
            flex: 1, background: effectiveMainBg,
            display: 'flex', flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Carte visionneuse */}
          <div
            style={{
              flex: 1,
              margin: '10px 13px 4px',
              border: `1px solid ${CARD_BORDER}`,
              borderRadius: 4,
              background: cardBg,
              display: 'flex', flexDirection: 'column',
              overflow: 'hidden',
              boxShadow: `2px 2px 0 ${CARD_SHADOW}`,
            }}
          >
            {/* En-tête carte */}
            <div
              style={{
                height: 36, minHeight: 36, background: cardBg,
                display: 'flex', alignItems: 'center',
                borderBottom: `1px solid ${BORDER}`,
                flexShrink: 0, paddingLeft: 12,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 700, color: cardTitleFg }}>
                Visionneuse DICOM
              </span>
              {/* Boutons zoom */}
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 2, paddingRight: 8 }}>
                <button
                  onClick={() => updateActiveTab(t => ({ ...t, zoom: Math.max(0.1, t.zoom / 1.25) }))}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, fontWeight: 700, color: cardTitleFg }}
                >−</button>
                <span style={{ fontSize: 11, color: SBAR_MUTED, width: 50, textAlign: 'center' }}>
                  {activeTab ? `${Math.round(activeTab.zoom * 100)} %` : '100 %'}
                </span>
                <button
                  onClick={() => updateActiveTab(t => ({ ...t, zoom: Math.min(10, t.zoom * 1.25) }))}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, fontWeight: 700, color: cardTitleFg }}
                >+</button>
              </div>
            </div>

            {/* Barre patients */}
            <PatientTabBar
              patients={patients}
              activePatientIdx={activePatientIdx}
              onSwitchPatient={patIdx => {
                const firstTabId = patients[patIdx]?.tabIds[0];
                if (firstTabId !== undefined) switchTab(firstTabId);
                else setActivePatientName(patients[patIdx]?.name ?? '');
              }}
            />

            {/* Canvas DICOM */}
            <DicomCanvas
              tab={activeTab}
              onZoomPan={onZoomPan}
              onContrastBright={onContrastBright}
              onFrameChange={onCanvasFrameChange}
              onMeasureAdd={onMeasureAdd}
              onMeasureMove={onMeasureMove}
              onMeasureLabelMove={onMeasureLabelMove}
              onMeasureSelect={onMeasureSelect}
              onContextMenu={(x, y) => setCtxMenu({ x, y })}
            />

            {/* Barre onglets fichiers */}
            <FileTabBar
              tabs={patientTabs}
              activeTabId={activeTab?.id ?? -1}
              onSwitchTab={switchTab}
              onCloseTab={closeTab}
              onOpenNew={onLoadDicom}
            />
          </div>

          {/* Console (affichée seulement si activée dans les réglages) */}
          {displaySettings.showConsole && (
            <ConsolePanel entries={logs} darkMode={darkMode} />
          )}
        </div>

        {/* ── Panel galerie détections (droit) ──────────────────────────── */}
        {displaySettings.analysisMode !== 'risk_only' && activeTab && (
          <>
            <div style={{ width: 1, background: '#0a0a14', flexShrink: 0 }} />
            <DetectionGallery
              framesB64={activeTab.data?.framesB64 ?? []}
              detections={activeTab.detectionsBy.original ?? []}
              imgW={activeTab.data?.cols ?? 512}
              imgH={activeTab.data?.rows ?? 512}
              onGotoFrame={onGotoFrame}
              sidebarBg={displaySettings.sidebarBg}
              textColor={displaySettings.textColor}
            />
          </>
        )}
      </div>

      {/* ── Dialogues flottants ────────────────────────────────────────────── */}
      {showContrast && (
        <AdjustDialog
          title="Contraste"
          initial={activeTab?.contrast ?? 1}
          min={0.1} max={3} neutral={1}
          onClose={() => setShowContrast(false)}
          onChange={v => updateActiveTab(t => ({ ...t, contrast: v }))}
        />
      )}
      {showBrightness && (
        <AdjustDialog
          title="Luminosité"
          initial={activeTab?.brightness ?? 0}
          min={-50} max={100} neutral={0}
          onClose={() => setShowBrightness(false)}
          onChange={v => updateActiveTab(t => ({ ...t, brightness: v }))}
        />
      )}

      {/* Menu contextuel */}
      {ctxMenu && (
        <ContextMenu
          x={ctxMenu.x}
          y={ctxMenu.y}
          onClose={() => setCtxMenu(null)}
          items={buildCanvasContextMenu({
            viewMode:        activeTab?.viewMode ?? 'normal',
            onTogglePan:     () => onToggleViewMode('pan'),
            onToggleMeasure: () => onToggleViewMode('measure'),
            onToggleSeries:  () => onToggleViewMode('series'),
            onContrast:      () => setShowContrast(v => !v),
            onBrightness:    () => setShowBrightness(v => !v),
            onResetView,
          })}
        />
      )}

      {/* Analyse en direct */}
      {showLive && (
        <LiveModal
          onClose={() => setShowLive(false)}
          addLog={addLog}
        />
      )}

      {/* Panneau réglages d'affichage */}
      {showSettings && (
        <SettingsPanel
          settings={displaySettings}
          onUpdate={updateSettings}
          onReset={resetSettings}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  );
}

// ── Barre patients ────────────────────────────────────────────────────────────

function PatientTabBar({
  patients,
  activePatientIdx,
  onSwitchPatient,
}: {
  patients: Patient[];
  activePatientIdx: number;
  onSwitchPatient: (idx: number) => void;
}) {
  if (!patients.length) return null;
  return (
    <div
      style={{
        background: PTAB_BG, height: 30, minHeight: 30,
        display: 'flex', alignItems: 'stretch', overflowX: 'auto',
        flexShrink: 0,
      }}
    >
      {patients.map((p, idx) => {
        const active = idx === activePatientIdx;
        return (
          <PatientTab
            key={p.name}
            name={p.name}
            active={active}
            onClick={() => onSwitchPatient(idx)}
          />
        );
      })}
    </div>
  );
}

function PatientTab({ name, active, onClick }: { name: string; active: boolean; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      style={{
        cursor: 'pointer',
        background: active ? PTAB_ACT_BG : PTAB_BG,
        color: active ? '#e5e7eb' : '#6b7280',
        fontSize: 11, fontWeight: 700,
        padding: '0 12px',
        display: 'flex', alignItems: 'center',
        borderBottom: active ? `2px solid ${BLUE}` : '2px solid transparent',
        whiteSpace: 'nowrap', userSelect: 'none',
      }}
    >
      {name}
    </div>
  );
}

// ── Barre onglets fichiers ────────────────────────────────────────────────────

function FileTabBar({
  tabs,
  activeTabId,
  onSwitchTab,
  onCloseTab,
  onOpenNew,
}: {
  tabs: TabState[];
  activeTabId: number;
  onSwitchTab: (id: number) => void;
  onCloseTab:  (id: number) => void;
  onOpenNew:   () => void;
}) {
  return (
    <div
      style={{
        background: TAB_BG, height: 32, minHeight: 32,
        display: 'flex', alignItems: 'stretch',
        borderTop: '1px solid #0a0a14',
        overflowX: 'auto', flexShrink: 0,
      }}
    >
      {tabs.map(tab => {
        const active = tab.id === activeTabId;
        return (
          <FileTab
            key={tab.id}
            label={tab.label}
            active={active}
            onClick={() => onSwitchTab(tab.id)}
            onClose={() => onCloseTab(tab.id)}
          />
        );
      })}
      <button
        onClick={onOpenNew}
        style={{
          background: '#000', color: '#fff',
          border: 'none', cursor: 'pointer',
          fontSize: 16, fontWeight: 700,
          padding: '0 10px',
          marginLeft: 2,
          alignSelf: 'center',
        }}
        title="Ajouter un fichier"
      >+</button>
    </div>
  );
}

function FileTab({
  label, active, onClick, onClose,
}: { label: string; active: boolean; onClick: () => void; onClose: () => void }) {
  return (
    <div
      style={{
        cursor: 'pointer',
        background: active ? TAB_ACT_BG : TAB_BG,
        color: active ? '#e5e7eb' : '#6b7280',
        fontSize: 11,
        display: 'flex', alignItems: 'center', gap: 2,
        padding: '0 2px 0 8px',
        borderTop: active ? `2px solid ${BLUE}` : '2px solid transparent',
        paddingTop: active ? 0 : 2,
        whiteSpace: 'nowrap', userSelect: 'none',
        flexShrink: 0,
      }}
      onClick={onClick}
    >
      {label}
      <button
        onClick={e => { e.stopPropagation(); onClose(); }}
        style={{
          background: '#000', color: '#fff',
          border: 'none', cursor: 'pointer',
          fontSize: 12, lineHeight: 1,
          padding: '2px 4px', marginLeft: 2,
          borderRadius: 2,
        }}
        onMouseEnter={e => (e.currentTarget.style.color = '#ff4444')}
        onMouseLeave={e => (e.currentTarget.style.color = '#fff')}
        title="Fermer l'onglet"
      >×</button>
    </div>
  );
}

export default StarhePlugin;
