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
import { BatchModal }          from './components/BatchModal';
import type { BatchResultToOpen } from './components/BatchModal';
import { LayoutPickerModal }   from './components/LayoutPickerModal';
import type { LayoutMode }     from './components/LayoutPickerModal';

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
  const [showLive,  setShowLive]  = useState(false);
  const [showBatch, setShowBatch] = useState(false);

  // ── Vue multi-panneaux ─────────────────────────────────────────────────────
  const [pendingLayoutOpen, setPendingLayoutOpen] = useState<BatchResultToOpen[] | null>(null);
  const [multiPanel, setMultiPanel] = useState<{ layout: LayoutMode; tabIds: number[] } | null>(null);

  // ── Chargement DICOM ───────────────────────────────────────────────────────
  const [loadingPaths, setLoadingPaths] = useState<Set<string>>(new Set());

  // Détection Electron : via l'API preload (méthode fiable avec contextIsolation)
  // ou via le userAgent (fallback si preload absent)
  const isElectron = typeof window !== 'undefined' &&
    (window.electronAPI !== undefined ||
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

  // ── Ouverture d'un résultat batch en onglet (helper partagé) ─────────────
  const openBatchResultAsTab = useCallback(async (result: BatchResultToOpen): Promise<number> => {
    const name = result.name;
    addLog(`Chargement : ${name}`, 'info');
    const data = await loadDicom(result.serverPath);
    const label = makeTabLabel(data.studyDate, data.fileName);
    const newTab: TabState = {
      ...makeDefaultTab(),
      label,
      patientName: data.patientName,
      dicomPath:   result.serverPath,
      data,
      detectionsBy: result.detections?.length ? { original: result.detections } : {},
      resultsBy: result.risk ? { original: {
        riskText: `${result.risk.label} (${(result.risk.score * 100).toFixed(1)} %)`,
        riskFg:   /élevé|high/i.test(result.risk.label) ? '#f87171' : '#4ade80',
        detText:  `${result.detections?.reduce((a, fd) => a + fd.length, 0) ?? 0} lésion(s)`,
        detFg:    '#facc15',
      }} : {},
    };
    setTabs(prev => [...prev, newTab]);
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
    addLog(`DICOM chargé avec résultats — ${data.frameCount} frame(s).`, 'success');
    return newTab.id;
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
      const msg = err instanceof Error
        ? (err.message || err.name || 'Erreur inconnue')
        : String(err);
      const hint = msg === 'Failed to fetch' ? ' — serveur inaccessible (port 8082 ?)' : '';
      addLog(`ERREUR chargement ${displayName} : ${msg}${hint}`, 'error');
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
      const msg = err instanceof Error
        ? (err.message || err.name || 'Erreur inconnue')
        : String(err);
      const hint = msg === 'Failed to fetch' ? ' — serveur inaccessible (port 8082 ?)' : '';
      addLog(`ERREUR chargement ${file.name} : ${msg}${hint}`, 'error');
    } finally {
      setLoadingPaths(prev => { const next = new Set(prev); next.delete(file.name); return next; });
    }
  }, [addLog, addTab, loadingPaths]);

  // Chargement DICOM — sélecteur de dossier (webkitdirectory) :
  // l’utilisateur choisit un dossier et tous les fichiers .dcm / .dicom /
  // sans extension à l’intérieur sont chargés automatiquement.
  const onLoadDicom = useCallback(async () => {
    if (isElectron && window.electronAPI?.openDicomFiles) {
      // Mode Electron : dialogue natif système → chemins absolus réels
      const paths = await window.electronAPI.openDicomFiles();
      for (const p of paths) {
        const name = p.split(/[\\/]/).pop() ?? p;
        await doLoadPath(p, name);
      }
    } else {
      // Mode navigateur : sélecteur de dossier (webkitdirectory)
      const isDicom = (f: File) => {
        const n = f.name.toLowerCase();
        return n.endsWith('.dcm') || n.endsWith('.dicom') || !n.includes('.');
      };
      const input = document.createElement('input');
      input.type = 'file';
      (input as any).webkitdirectory = true;
      (input as any).multiple = true;
      input.onchange = async () => {
        for (const file of Array.from(input.files ?? []).filter(isDicom)) {
          await doLoadFile(file);
        }
      };
      input.click();
    }
  }, [isElectron, doLoadPath, doLoadFile]);

  // Sélection manuelle de fichiers DICOM individuels
  const onLoadDicomFiles = useCallback(() => {
    const isDicom = (f: File) => {
      const n = f.name.toLowerCase();
      return n.endsWith('.dcm') || n.endsWith('.dicom') || !n.includes('.');
    };
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.onchange = async () => {
      for (const file of Array.from(input.files ?? []).filter(isDicom)) {
        await doLoadFile(file);
      }
    };
    input.click();
  }, [doLoadFile]);

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
          onLoadDicomFiles={onLoadDicomFiles}
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
          onOpenBatch={() => setShowBatch(true)}
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
              {/* ── Boutons de disposition (toujours visibles) ─────── */}
              {(() => {
                const n = patientTabs.length;
                const cur = multiPanel?.layout ?? 'single';
                const btnBase: React.CSSProperties = {
                  background: 'none', border: '1px solid transparent',
                  borderRadius: 4, cursor: 'pointer',
                  padding: '3px 5px', display: 'flex', alignItems: 'center',
                  transition: 'border-color 0.12s, background 0.12s',
                };
                const btnActive: React.CSSProperties = {
                  ...btnBase,
                  background: '#1e2d45', border: '1px solid #3b82f6',
                };
                const btnDisabled: React.CSSProperties = {
                  ...btnBase, opacity: 0.3, cursor: 'not-allowed',
                };
                const layouts: { key: LayoutMode; title: string; need: number; icon: React.ReactNode }[] = [
                  {
                    key: 'single', title: 'Vue simple (1 fichier)', need: 1,
                    icon: (
                      <svg width="16" height="12" viewBox="0 0 16 12" fill="none">
                        <rect x="1" y="1" width="14" height="10" rx="1" fill="#4a90d9" />
                      </svg>
                    ),
                  },
                  {
                    key: 'split-v', title: 'Vue scindée verticalement (2 fichiers côte à côte)', need: 2,
                    icon: (
                      <svg width="16" height="12" viewBox="0 0 16 12" fill="none">
                        <rect x="1"  y="1" width="6" height="10" rx="1" fill="#4a90d9" />
                        <rect x="9"  y="1" width="6" height="10" rx="1" fill="#4a90d9" />
                      </svg>
                    ),
                  },
                  {
                    key: 'split-h', title: 'Vue scindée horizontalement (2 fichiers haut/bas)', need: 2,
                    icon: (
                      <svg width="16" height="12" viewBox="0 0 16 12" fill="none">
                        <rect x="1" y="1"  width="14" height="4" rx="1" fill="#4a90d9" />
                        <rect x="1" y="7"  width="14" height="4" rx="1" fill="#4a90d9" />
                      </svg>
                    ),
                  },
                  {
                    key: 'quad', title: 'Vue 4 panneaux (2×2)', need: 2,
                    icon: (
                      <svg width="16" height="12" viewBox="0 0 16 12" fill="none">
                        <rect x="1" y="1" width="6" height="4" rx="1" fill="#4a90d9" />
                        <rect x="9" y="1" width="6" height="4" rx="1" fill="#4a90d9" />
                        <rect x="1" y="7" width="6" height="4" rx="1" fill="#4a90d9" />
                        <rect x="9" y="7" width="6" height="4" rx="1" fill="#4a90d9" />
                      </svg>
                    ),
                  },
                ];
                return (
                  <div style={{ marginLeft: 10, display: 'flex', alignItems: 'center', gap: 2 }}>
                    {layouts.map(({ key, title, need, icon }) => {
                      const active   = cur === key;
                      const disabled = n < need;
                      return (
                        <button
                          key={key}
                          title={title}
                          disabled={disabled}
                          style={disabled ? btnDisabled : active ? btnActive : btnBase}
                          onMouseEnter={e => { if (!disabled && !active) { (e.currentTarget as HTMLElement).style.background = '#132030'; (e.currentTarget as HTMLElement).style.borderColor = '#2d4a6a'; } }}
                          onMouseLeave={e => { if (!disabled && !active) { (e.currentTarget as HTMLElement).style.background = 'none'; (e.currentTarget as HTMLElement).style.borderColor = 'transparent'; } }}
                          onClick={() => {
                            if (disabled) return;
                            if (key === 'single') {
                              setMultiPanel(null);
                            } else {
                              const ids = patientTabs.slice(0, key === 'quad' ? 4 : 2).map(t => t.id);
                              setMultiPanel({ layout: key, tabIds: ids });
                            }
                          }}
                        >
                          {icon}
                        </button>
                      );
                    })}
                  </div>
                );
              })()}
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

            {/* Canvas DICOM — vue simple ou vue multi-panneaux */}
            {multiPanel ? (
              <MultiPanelView
                layout={multiPanel.layout}
                tabIds={multiPanel.tabIds}
                tabs={tabs}
                activeTabId={activeTabId}
                onFocusPanel={id => setActiveTabId(id)}
                onExit={() => setMultiPanel(null)}
                onDropToPanel={(slotIdx, droppedTabId) => {
                  const { layout, tabIds: cur } = multiPanel;
                  const slots = layout === 'quad' ? 4 : layout === 'single' ? 1 : 2;
                  const newIds: number[] = Array.from({ length: slots }, (_, i) => cur[i] ?? -1);
                  const existingSlot = newIds.indexOf(droppedTabId);
                  if (existingSlot === slotIdx) { setActiveTabId(droppedTabId); return; }
                  if (existingSlot >= 0) {
                    const tmp = newIds[slotIdx]; newIds[slotIdx] = droppedTabId; newIds[existingSlot] = tmp;
                  } else {
                    newIds[slotIdx] = droppedTabId;
                  }
                  setMultiPanel({ layout, tabIds: newIds });
                  setActiveTabId(droppedTabId);
                }}
                onExpandLayout={droppedTabId => {
                  const { layout, tabIds: cur } = multiPanel;
                  const slots = layout === 'quad' ? 4 : layout === 'single' ? 1 : 2;
                  if (slots >= 4) {
                    // Déjà au maximum — remplacer le dernier slot
                    const newIds = [...cur.slice(0, 3), droppedTabId];
                    setMultiPanel({ layout: 'quad', tabIds: newIds });
                  } else {
                    // Élargir à quad et ajouter le fichier au prochain slot libre
                    const newIds: number[] = Array.from({ length: 4 }, (_, i) => cur[i] ?? -1);
                    const firstEmpty = newIds.indexOf(-1);
                    newIds[firstEmpty >= 0 ? firstEmpty : slots] = droppedTabId;
                    setMultiPanel({ layout: 'quad', tabIds: newIds });
                  }
                  setActiveTabId(droppedTabId);
                }}
                onZoomPan={onZoomPan}
                onContrastBright={onContrastBright}
                onFrameChange={onCanvasFrameChange}
                onMeasureAdd={onMeasureAdd}
                onMeasureMove={onMeasureMove}
                onMeasureLabelMove={onMeasureLabelMove}
                onMeasureSelect={onMeasureSelect}
                onRemovePanel={slotIdx => {
                  const { layout, tabIds: cur } = multiPanel;
                  const slots = layout === 'quad' ? 4 : 2;
                  const newIds = Array.from({ length: slots }, (_, i): number => cur[i] ?? -1);
                  newIds[slotIdx] = -1;
                  const filled = newIds.filter(id => id !== -1);
                  if (filled.length === 0) { setMultiPanel(null); return; }
                  if (filled.length === 1) { setMultiPanel(null); setActiveTabId(filled[0]); return; }
                  if (filled.length === 2) { setMultiPanel({ layout: 'split-v', tabIds: filled }); return; }
                  setMultiPanel({ layout: 'quad', tabIds: newIds });
                }}
                onContextMenu={(x, y) => setCtxMenu({ x, y })}
              />
            ) : (
              <div
                style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}
                onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }}
                onDrop={e => {
                  e.preventDefault();
                  const raw = e.dataTransfer.getData('text/plain');
                  if (!raw.startsWith('starhe-tab:')) return;
                  const droppedId = parseInt(raw.replace('starhe-tab:', ''), 10);
                  if (!tabs.some(t => t.id === droppedId)) return;
                  const curId = activeTab?.id ?? -1;
                  if (droppedId === curId || curId === -1) return;
                  // Auto-switch à split-v avec le fichier courant + le fichier glissé
                  setMultiPanel({ layout: 'split-v', tabIds: [curId, droppedId] });
                }}
              >
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
              </div>
            )}
            {/* Bande de vignettes — toujours visible (vue simple et multi-panneaux) */}
            <FileThumbnailStrip
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

      {/* Analyse batch */}
      {showBatch && (
        <BatchModal
          onClose={() => setShowBatch(false)}
          analysisMode={displaySettings.analysisMode}
          onOpenInTab={async (result: BatchResultToOpen) => {
            setShowBatch(false);
            try {
              const tabId = await openBatchResultAsTab(result);
              setActiveTabId(tabId);
            } catch (err: unknown) {
              const msg = err instanceof Error ? err.message : String(err);
              addLog(`ERREUR ouverture ${result.name} : ${msg}`, 'error');
            }
          }}
          onOpenInLayout={(results: BatchResultToOpen[]) => {
            setShowBatch(false);
            setPendingLayoutOpen(results);
          }}
        />
      )}

      {/* Sélecteur de disposition multi-panneaux */}
      {pendingLayoutOpen && (
        <LayoutPickerModal
          count={pendingLayoutOpen.length}
          onCancel={() => setPendingLayoutOpen(null)}
          onPick={async (layout: LayoutMode) => {
            const toOpen = pendingLayoutOpen.slice(0, layout === 'single' ? 1 : layout === 'quad' ? 4 : 2);
            setPendingLayoutOpen(null);
            addLog(`Ouverture de ${toOpen.length} fichier(s) en vue ${layout}…`, 'info');
            try {
              const tabIds = await Promise.all(toOpen.map(r => openBatchResultAsTab(r)));
              setActiveTabId(tabIds[0]);
              if (layout !== 'single') setMultiPanel({ layout, tabIds });
            } catch (err: unknown) {
              const msg = err instanceof Error ? err.message : String(err);
              addLog(`ERREUR ouverture multi-panneaux : ${msg}`, 'error');
            }
          }}
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

// ── Bande de vignettes fichiers (remplace FileTabBar) ─────────────────────────

function FileThumbnailStrip({
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
  // Groupe les onglets par date (partie avant " · " dans le label)
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
          title="Ajouter un fichier"
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
              const active = tab.id === activeTabId;
              const firstFrame = tab.data?.framesB64?.[0];
              const labelParts = tab.label.split(' · ');
              const shortName = labelParts.length > 1 ? labelParts.slice(1).join(' · ') : tab.label;

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
                    width: 70,
                    minWidth: 70,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'stretch',
                    cursor: 'pointer',
                    borderRadius: 4,
                    border: active ? '2px solid #3b82f6' : '2px solid #1e293b',
                    background: active ? '#0f1e35' : '#111827',
                    overflow: 'hidden',
                    flexShrink: 0,
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
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
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
        title="Ouvrir un nouveau fichier DICOM"
        style={{
          width: 28, minWidth: 28, alignSelf: 'stretch',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', color: '#374151', fontSize: 20, fontWeight: 700,
          borderRadius: 4, border: '1px dashed #1e293b',
          transition: 'color 0.12s, border-color 0.12s, background 0.12s',
          flexShrink: 0, marginTop: groups.length > 1 || (groups[0]?.[1].length ?? 0) > 1 ? 16 : 0,
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

export default StarhePlugin;

// ── Visionneuse multi-panneaux ────────────────────────────────────────────────

interface MultiPanelViewProps {
  layout:            LayoutMode;
  tabIds:            number[];
  tabs:              TabState[];
  activeTabId:       number;
  onFocusPanel:      (tabId: number) => void;
  onExit:            () => void;
  onDropToPanel:     (slotIdx: number, tabId: number) => void;
  onExpandLayout:    (tabId: number) => void;
  onRemovePanel:     (slotIdx: number) => void;
  onZoomPan:          (zoom: number, panX: number, panY: number) => void;
  onContrastBright:   (contrast: number, brightness: number) => void;
  onFrameChange:      (idx: number) => void;
  onMeasureAdd:       (frameIdx: number, measure: Measure) => void;
  onMeasureMove:      (frameIdx: number, segIdx: number, newPts: [[number, number], [number, number]]) => void;
  onMeasureLabelMove: (frameIdx: number, segIdx: number, labelOffset: [number, number]) => void;
  onMeasureSelect:    (frameIdx: number, segIdx: number | null) => void;
  onContextMenu:      (x: number, y: number) => void;
}

function MultiPanelView({
  layout, tabIds, tabs, activeTabId,
  onFocusPanel, onExit, onDropToPanel, onExpandLayout, onRemovePanel,
  onZoomPan, onContrastBright, onFrameChange,
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
    const onUp = () => setResizing(null);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup',   onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, [resizing]);

  const c = colSplit; const r = rowSplit;
  const gridStyle: React.CSSProperties =
    layout === 'split-v' ? { gridTemplateColumns: `${c}fr ${100-c}fr` } :
    layout === 'split-h' ? { gridTemplateRows:    `${r}fr ${100-r}fr` } :
    layout === 'quad'    ? { gridTemplateColumns: `${c}fr ${100-c}fr`, gridTemplateRows: `${r}fr ${100-r}fr` } :
    {};

  // Stable no-op callbacks for unfocused panels (avoids re-renders)
  const NOOP_ZP  = React.useCallback(()                  => {}, []);
  const NOOP_CB  = React.useCallback(()                  => {}, []);
  const NOOP_FC  = React.useCallback((_: number)         => {}, []);
  const NOOP_MA  = React.useCallback((_a: number, _b: Measure)                                              => {}, []);
  const NOOP_MM  = React.useCallback((_a: number, _b: number, _c: [[number,number],[number,number]])        => {}, []);
  const NOOP_LM  = React.useCallback((_a: number, _b: number, _c: [number,number])                         => {}, []);
  const NOOP_MS  = React.useCallback((_a: number, _b: number | null)                                       => {}, []);
  const NOOP_CTX = React.useCallback((_a: number, _b: number)                                              => {}, []);

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
          const tabId     = tabIds[i];
          const tab       = tabId !== undefined && tabId >= 0 ? tabs.find(t => t.id === tabId) ?? null : null;
          const isFocused = tabId !== undefined && tabId === activeTabId;
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
              {/* Canvas du panneau (pointer-events bloqués si non-focalisé) */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', pointerEvents: isFocused ? 'auto' : 'none' }}>
                {tab ? (
                  <DicomCanvas
                    tab={tab}
                    onZoomPan={isFocused          ? onZoomPan        : NOOP_ZP}
                    onContrastBright={isFocused   ? onContrastBright : NOOP_CB}
                    onFrameChange={isFocused      ? onFrameChange    : NOOP_FC}
                    onMeasureAdd={isFocused       ? onMeasureAdd     : NOOP_MA}
                    onMeasureMove={isFocused      ? onMeasureMove    : NOOP_MM}
                    onMeasureLabelMove={isFocused ? onMeasureLabelMove : NOOP_LM}
                    onMeasureSelect={isFocused    ? onMeasureSelect  : NOOP_MS}
                    onContextMenu={isFocused      ? onContextMenu    : NOOP_CTX}
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
                    borderRadius: 3,
                    color: '#94a3b8',
                    fontSize: 10, fontWeight: 700,
                    cursor: 'pointer',
                    lineHeight: 1,
                    padding: 0,
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

        {/* ── Poignées de redimensionnement ───────────────────────── */}

        {/* Séparateur vertical — split-v et quad */}
        {(layout === 'split-v' || layout === 'quad') && (
          <div
            title="Glisser pour redimensionner"
            style={{
              position: 'absolute',
              top: 0, bottom: 0,
              left: `calc(${colSplit}% - 5px)`,
              width: 10,
              cursor: 'col-resize',
              zIndex: 20,
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
              position: 'absolute',
              left: 0, right: 0,
              top: `calc(${rowSplit}% - 5px)`,
              height: 10,
              cursor: 'row-resize',
              zIndex: 20,
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
            cursor: 'copy',
            fontSize: 11,
            color: dragOverExpand ? '#fbbf24' : '#475569',
            transition: 'all 0.15s',
            gap: 6,
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
