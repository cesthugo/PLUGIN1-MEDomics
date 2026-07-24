// StarhePlugin/index.tsx — Root component of the STARHE plugin for MEDomics
//
// Full replica of prototype_tkinter.py (STARHEApp) in React:
//   - Dark MEDomics title bar
//   - Left sidebar (270 px): controls + results
//   - Light central area: DICOM viewer + log console
//   - Patient bar (top of the card) + file tab bar (bottom)
//   - Multi-tab / multi-patient
//   - Playback with a speed multiplier
//   - Pan / Zoom / Measure / Series Scroll
//   - Contrast / Brightness (floating dialogs + right-click)
//   - Right-click context menu
//   - AI analysis via SSE (STARHE pipeline)
//   - MongoDB cache (reset)
//   - Light / dark theme
//   - "Live analysis" window
//   - Keyboard shortcuts (Space, ←/→, P, M, S, R, C, L, ±, B, Ctrl+0/+/-)

import React, {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';

import type {
  TabState, Patient, LogEntry, LogLevel, ViewMode, Measure,
} from '../utilities/starhe/types';
import {
  SIDEBAR_BG, SIDEBAR_HOV, MAIN_BG, CARD_BG, CARD_BORDER, CARD_SHADOW,
  BLUE, BLUE_TEXT, SBAR_FG, SBAR_MUTED, BORDER, CANVAS_BG,
  PTAB_BG, PTAB_ACT_BG,
} from '../utilities/starhe/colors';
import { loadDicom, loadDicomFile, deleteCache, makeTabLabel, getWeightsStatus } from '../utilities/starhe/api';
import { filterDicomFiles, mapWithConcurrency } from '../utilities/starhe/utils';
import medomicsLogo from '../assets/medomics_logo.png';
import { usePipelineSSE } from '../utilities/starhe/hooks/usePipelineSSE';
import { usePlayback }    from '../utilities/starhe/hooks/usePlayback';
import { useDisplaySettings, DISPLAY_DEFAULTS } from '../utilities/starhe/hooks/useDisplaySettings';
import { Sidebar }        from '../components/starhe/Sidebar';
import { DicomCanvas }    from '../components/starhe/DicomCanvas';
import { ConsolePanel }   from '../components/starhe/ConsolePanel';
import { AdjustDialog }   from '../components/starhe/AdjustDialog';
import { ContextMenu, buildCanvasContextMenu } from '../components/starhe/ContextMenu';
import { LiveModal }      from '../components/starhe/LiveModal';
import { SettingsPanel }       from '../components/starhe/SettingsPanel';
import { DetectionGallery }    from '../components/starhe/DetectionGallery';
import { BatchModal }          from '../components/starhe/BatchModal';
import { WeightsModal }         from '../components/starhe/WeightsModal';
import type { BatchResultToOpen } from '../components/starhe/BatchModal';
import { LayoutPickerModal }   from '../components/starhe/LayoutPickerModal';
import type { LayoutMode }     from '../components/starhe/LayoutPickerModal';
import { MultiPanelView }      from '../components/starhe/MultiPanelView';
import { FileThumbnailStrip }  from '../components/starhe/FileThumbnailStrip';

// ── Auto-incremented ID ───────────────────────────────────────────────────────
let _nextTabId = 1;
const nextTabId = () => _nextTabId++;
let _nextLogId = 1;
const nextLogId = () => _nextLogId++;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeDefaultTab(): TabState {
  return {
    id:              nextTabId(),
    label:           '—',
    patientName:     'Unknown patient',
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

// ── Main component ────────────────────────────────────────────────────────────

export interface StarhePluginProps {
  /** Main area background color (theme override) */
  mainBg?: string;
  /** Total height (default: 100vh) */
  height?: string | number;
  /** Total width (default: 100%) */
  width?: string | number;
}

export function StarhePlugin({ mainBg, height = '100vh', width = '100%' }: StarhePluginProps) {
  // ── Tabs and patients ──────────────────────────────────────────────────────
  const [tabs,             setTabs]            = useState<TabState[]>([]);
  const [activeTabId,      setActiveTabId]     = useState<number>(-1);
  const [patients,         setPatients]        = useState<Patient[]>([]);
  const [activePatientName, setActivePatientName] = useState<string>('');

  // Ref to read the current state in closeTab (synchronous read outside the updater)
  const tabsRef     = useRef<TabState[]>(tabs);
  tabsRef.current   = tabs;
  const patientsRef = useRef<Patient[]>(patients);
  patientsRef.current = patients;

  // Derived: computed on each render from the stable IDs
  const activeTabIdx = tabs.findIndex(t => t.id === activeTabId);
  const activeTab    = activeTabIdx >= 0 ? tabs[activeTabIdx] : null;
  const activePatientIdx = patients.findIndex(p => p.name === activePatientName);

  // ── Video playback ─────────────────────────────────────────────────────────
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

  // Tab for which the analysis was launched (stable ID, independent of the active tab)
  const [analysisTargetTabId, setAnalysisTargetTabId] = useState<number>(-1);

  // When a result arrives, inject it into the *target* tab (not necessarily the active one)
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

  // ── Display settings (persisted in localStorage) ──────────────────────────
  const { settings: displaySettings, updateSettings, resetSettings } = useDisplaySettings();
  const [showSettings, setShowSettings] = useState(false);
  // ── Dynamic CSS injection (size + font + text color) ─────────────────────────────
  // Principle: CSS selectors [style*="font-size: Npx"] + !important to scale
  // all inline sizes proportionally without touching the layout.
  const styleContent = useMemo(() => {
    const s  = displaySettings.fontScale;
    const ff = displaySettings.fontFamily;
    // px sizes used in the interface — scale each proportionally
    const sizes = [9, 10, 11, 12, 13, 14, 16, 18, 20, 22];
    const fontSizeRules = sizes
      .map(n => `.starhe-root [style*="font-size: ${n}px"] { font-size: ${(n * s).toFixed(1)}px !important; }`)
      .join('\n');
    // textColor: injected only if different from the default (otherwise we would override the semantic colors)
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
  // ── Theme ──────────────────────────────────────────────────────────────────
  const [darkMode, setDarkMode] = useState(false);
  const effectiveMainBg = mainBg ?? (darkMode ? '#1a1a2e' : displaySettings.mainBg);
  const cardBg = darkMode ? '#16213e' : CARD_BG;
  const cardTitleFg = darkMode ? '#89b4fa' : BLUE_TEXT;

  // ── Contrast / brightness dialogs ──────────────────────────────────────────
  const [showContrast,   setShowContrast]   = useState(false);
  const [showBrightness, setShowBrightness] = useState(false);

  // ── Menu contextuel ────────────────────────────────────────────────────────
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number } | null>(null);

  // ── Live window ────────────────────────────────────────────────────────────
  const [showLive,  setShowLive]  = useState(false);
  const [showBatch, setShowBatch] = useState(false);
  const [showWeights, setShowWeights] = useState(false);

  // ── Sidebar collapse (left: DICOM controls · right: detection gallery) ─
  const [leftSidebarOpen,  setLeftSidebarOpen]  = useState(true);
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true);

  // ── Drag & drop of a file onto the single view → switch to side-by-side split ─
  const [singleViewDragOver, setSingleViewDragOver] = useState(false);

  // ── Vue multi-panneaux ─────────────────────────────────────────────────────
  const [multiPanel, setMultiPanel] = useState<{ layout: LayoutMode; tabIds: number[] } | null>(null);
  const [showLayoutPicker, setShowLayoutPicker] = useState(false);

  // ── Chargement DICOM ───────────────────────────────────────────────────────
  const [loadingPaths, setLoadingPaths] = useState<Set<string>>(new Set());

  // Electron detection: via the preload API (reliable method with contextIsolation)
  // or via the userAgent (fallback if the preload is absent)
  const isElectron = typeof window !== 'undefined' &&
    (window.electronAPI !== undefined ||
     navigator.userAgent.includes('Electron'));

  // ── Inject a tab after a successful load ──────────────────────────────────
  const addTab = useCallback((
    displayName: string,
    dicomPath:   string,
    data:        import('../utilities/starhe/types').DicomData,
  ) => {
    const label  = makeTabLabel(data.studyDate, data.fileName);
    const newTab: TabState = {
      ...makeDefaultTab(),
      label,
      patientName: data.patientName,
      dicomPath,
      data,
    };
    // Functional updaters: each call receives the result of the previous one (React batches)
    // → safe even if several files load simultaneously before the next render
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(newTab.id);  // stable ID — no stale index
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
    addLog(`DICOM loaded — ${data.frameCount} frame(s), ${data.rows}×${data.cols} px.`, 'success');
  }, [addLog]);

  // ── Open a batch result in a tab (shared helper) ─────────────────────────
  const openBatchResultAsTab = useCallback(async (result: BatchResultToOpen): Promise<number> => {
    const name = result.name;
    addLog(`Loading: ${name}`, 'info');
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
        detText:  `${result.detections?.reduce((a, fd) => a + fd.length, 0) ?? 0} lesion(s)`,
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
    addLog(`DICOM loaded with results — ${data.frameCount} frame(s).`, 'success');
    return newTab.id;
  }, [addLog]);

  // Loading by absolute path (Electron or manual input)
  const doLoadPath = useCallback(async (path: string, displayName: string) => {
    if (loadingPaths.has(path)) return;
    setLoadingPaths(prev => new Set([...prev, path]));
    addLog(`Loading: ${displayName}`, 'info');
    try {
      const data = await loadDicom(path);
      addTab(displayName, path, data);
    } catch (err: unknown) {
      const msg = err instanceof Error
        ? (err.message || err.name || 'Unknown error')
        : String(err);
      const hint = msg === 'Failed to fetch' ? ' — serveur inaccessible (port 8082 ?)' : '';
      addLog(`ERREUR chargement ${displayName} : ${msg}${hint}`, 'error');
    } finally {
      setLoadingPaths(prev => { const next = new Set(prev); next.delete(path); return next; });
    }
  }, [addLog, addTab, loadingPaths]);

  // Loading by byte upload (standard browser without Electron)
  const doLoadFile = useCallback(async (file: File) => {
    if (loadingPaths.has(file.name)) return;
    setLoadingPaths(prev => new Set([...prev, file.name]));
    addLog(`Loading: ${file.name}`, 'info');
    try {
      const data = await loadDicomFile(file);
      addTab(file.name, data.serverPath || file.name, data);
    } catch (err: unknown) {
      const msg = err instanceof Error
        ? (err.message || err.name || 'Unknown error')
        : String(err);
      const hint = msg === 'Failed to fetch' ? ' — serveur inaccessible (port 8082 ?)' : '';
      addLog(`ERREUR chargement ${file.name} : ${msg}${hint}`, 'error');
    } finally {
      setLoadingPaths(prev => { const next = new Set(prev); next.delete(file.name); return next; });
    }
  }, [addLog, addTab, loadingPaths]);

  // "DICOM Folder" — picks a folder and loads every DICOM file inside.
  // Individual files are handled by the separate button (onLoadDicomFiles).
  const onLoadDicom = useCallback(async () => {
    if (isElectron && window.electronAPI?.openDicomFolder) {
      // Electron: native folder dialog; the main process walks the tree and
      // returns real absolute paths (detected by extension or DICM magic).
      const paths = await window.electronAPI.openDicomFolder();
      if (paths.length === 0) return;
      addLog(`Folder: ${paths.length} DICOM file(s) detected.`, 'info');
      // Load concurrently (bounded pool) so all files open together.
      await mapWithConcurrency(paths, 4, async p => {
        const name = p.split(/[\\/]/).pop() ?? p;
        await doLoadPath(p, name);
      });
      return;
    }

    // Browser: directory picker — `webkitdirectory` returns the folder tree.
    const input = document.createElement('input');
    input.type = 'file';
    (input as any).webkitdirectory = true;
    (input as any).multiple = true;
    input.onchange = async () => {
      const all = Array.from(input.files ?? []);
      if (all.length === 0) return;
      const dicoms = await filterDicomFiles(all);
      if (dicoms.length === 0) {
        addLog(`No DICOM file found in this folder (${all.length} file(s) scanned).`, 'warning');
        return;
      }
      addLog(`Folder: ${dicoms.length}/${all.length} DICOM file(s) detected.`, 'info');
      // Load concurrently (bounded pool) so all files open together.
      await mapWithConcurrency(dicoms, 4, doLoadFile);
    };
    input.click();
  }, [isElectron, doLoadPath, doLoadFile, addLog]);

  // Loading individual DICOM files (second button of the sidebar)
  const onLoadDicomFiles = useCallback(async () => {
    const input   = document.createElement('input');
    input.type     = 'file';
    input.multiple = true;
    input.onchange = async () => {
      // Explicitly picked files: load them as-is, without the folder scan's
      // filtering — the user already chose exactly what to open.
      const files = Array.from(input.files ?? []);
      for (const file of files) await doLoadFile(file);
    };
    input.click();
  }, [doLoadFile]);

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

  // ── Analysis ───────────────────────────────────────────────────────────────

  const onRunPipeline = useCallback(async () => {
    if (!activeTab?.data) return;
    if (analysisStatus === 'running') return;

    const mode = displaySettings.analysisMode;

    // The .pth weights are provided by the user (not bundled). Before running,
    // ensure every model this analysis needs has its weight present server-side;
    // if any is missing, open the weights menu instead of launching an analysis
    // doomed to fail. Works in both modes (browser and Electron) via the Go server.
    const needed = new Set<string>();
    if (mode !== 'detect_only') needed.add('risk');
    if (mode !== 'risk_only')   needed.add('detect');
    try {
      const status = await getWeightsStatus();
      const missing = status.filter(s => needed.has(s.id) && !s.present);
      if (missing.length > 0) {
        addLog(`Missing model weights: ${missing.map(m => m.name).join(', ')}. Load them to run the analysis.`, 'warning');
        setShowWeights(true);
        return;
      }
    } catch (err) {
      // Status endpoint unreachable — don't hard-block on a transient failure;
      // let the analysis proceed and surface any real error via SSE.
      addLog(`Could not verify model weights: ${err instanceof Error ? err.message : String(err)}`, 'warning');
    }

    setAnalysisTargetTabId(activeTab.id);  // figer la cible avant le lancement
    startAnalysis({
      dicomPath:    activeTab.dicomPath,
      runRisk:      mode !== 'detect_only',
      runDetection: mode !== 'risk_only',
    });
  }, [activeTab, analysisStatus, startAnalysis, displaySettings.analysisMode, isElectron, addLog]);

  const onResetAnalysis = useCallback(async () => {
    if (!activeTab?.dicomPath) return;
    const ok = window.confirm(
      `Delete cached STARHE results for:\n${activeTab.dicomPath}?`
    );
    if (!ok) return;
    try {
      const { deleted } = await deleteCache(activeTab.dicomPath);
      addLog(`✓  MongoDB result deleted (${deleted} doc).`, 'success');
    } catch {
      addLog('⚠  No cached result to delete.', 'warning');
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

  const onResetAllPanelsPan = useCallback(() => {
    if (!multiPanel) return;
    const ids = multiPanel.tabIds;
    setTabs(prev => prev.map(t => ids.includes(t.id) ? { ...t, panX: 0, panY: 0 } : t));
  }, [multiPanel]);

  const onContrastBright = useCallback((contrast: number, brightness: number) =>
    updateActiveTab(t => ({ ...t, contrast, brightness })), [updateActiveTab]);

  const onCanvasFrameChange = useCallback((idx: number) => {
    if (isPlaying) setIsPlaying(false);
    updateActiveTab(t => ({ ...t, frameIdx: idx }));
  }, [isPlaying, updateActiveTab]);

  // ── Measures ───────────────────────────────────────────────────────────────

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
          segs[segIdx] = { ...segs[segIdx], pts: newPts }; // preserves labelOffset
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

  // ── Tabs ───────────────────────────────────────────────────────────────────

  const switchTab = useCallback((tabId: number) => {
    if (!tabsRef.current.some(t => t.id === tabId)) return;
    if (isPlaying) setIsPlaying(false);
    setActiveTabId(tabId);
    const patient = patientsRef.current.find(p => p.tabIds.includes(tabId));
    if (patient) setActivePatientName(patient.name);
  }, [isPlaying]);

  // ── Multi-panneaux : callbacks ─────────────────────────────────────────────

  const onFocusPanel    = useCallback((tabId: number) => switchTab(tabId), [switchTab]);
  const onExitMultiPanel = useCallback(() => setMultiPanel(null), []);
  const onOpenLayoutPicker = useCallback(() => setShowLayoutPicker(true), []);

  const onDropToPanel = useCallback((slotIdx: number, tabId: number) => {
    setMultiPanel(prev => {
      if (!prev) return prev;
      const next = [...prev.tabIds];
      // De-duplication: if the file is already shown elsewhere, swap the
      // two cells (the previous occupant moves to the source cell) rather than
      // leaving the same file in two panels.
      const from = next.findIndex((id, idx) => id === tabId && idx !== slotIdx);
      const displaced = next[slotIdx];
      next[slotIdx] = tabId;
      if (from >= 0) next[from] = displaced;
      return { ...prev, tabIds: next };
    });
    switchTab(tabId);
  }, [switchTab]);

  // Drop a file onto the single view → switch to side-by-side split
  // [current file, dropped file]. No-op if re-dropping the current file.
  const onDropToSingleView = useCallback((droppedId: number) => {
    if (!activeTab || droppedId === activeTab.id) return;
    setMultiPanel({ layout: 'split-v', tabIds: [activeTab.id, droppedId] });
    switchTab(droppedId);
  }, [activeTab, switchTab]);

  const onExpandLayout = useCallback((tabId: number) => {
    setMultiPanel(prev => {
      if (!prev) return prev;
      // De-duplication: do nothing if the file is already in a panel.
      if (prev.tabIds.includes(tabId)) return prev;
      const nextLayout: LayoutMode =
        prev.layout === 'split-v' || prev.layout === 'split-h' ? 'quad' : prev.layout;
      const next = [...prev.tabIds];
      const empty = next.findIndex(id => id < 0);
      if (empty >= 0) next[empty] = tabId; else next.push(tabId);
      while (next.length < 4) next.push(-1);
      return { layout: nextLayout, tabIds: next.slice(0, 4) };
    });
  }, []);

  const onRemovePanel = useCallback((slotIdx: number) => {
    setMultiPanel(prev => {
      if (!prev) return prev;
      const next = [...prev.tabIds]; next[slotIdx] = -1;
      return { ...prev, tabIds: next };
    });
  }, []);

  const closeTab = useCallback((tabId: number) => {
    const currentTabs = tabsRef.current;
    // No side effects in the updaters (avoids the React StrictMode double-call)
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

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────

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

  // ── Active patient: associated tabs ────────────────────────────────────────
  const activePatient = activePatientIdx >= 0 ? patients[activePatientIdx] : null;
  // patientTabs: file tabs of the active patient, in tab order (not tabIds)
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
            marginLeft: 10, overflow: 'hidden', padding: 3,
          }}
        >
          <img
            src={medomicsLogo}
            alt="MEDomics"
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          />
        </div>
        <span style={{ color: '#7c8899', fontSize: 20, marginLeft: 8, marginRight: 4 }}>│</span>
        <span style={{ color: displaySettings.textColor, fontSize: 13 }}>Plugin1 Hugo — STARHE</span>
        <span style={{ color: '#7c8899', fontSize: 9, marginLeft: 8 }}>v0.1.0-prototype</span>

        {/* Bouton Réglages — haut droite */}
        <div style={{ marginLeft: 'auto', paddingRight: 12 }}>
          <button
            onClick={() => setShowSettings(v => !v)}
            title="Display settings"
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
            ⚙&nbsp;Settings
          </button>
        </div>
      </div>

      {/* ── Corps : sidebar + zone principale ─────────────────────────────── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Sidebar gauche (repliable) */}
        {leftSidebarOpen && (
          <Sidebar
            tab={activeTab}
            analysisStatus={analysisStatus}
            darkMode={darkMode}
            sidebarBg={displaySettings.sidebarBg}
            textColor={displaySettings.textColor}
            analysisMode={displaySettings.analysisMode}
            onLoadDicom={onLoadDicom}
            onLoadDicomFiles={onLoadDicomFiles}
            onPrevFrame={onPrevFrame}
            onNextFrame={onNextFrame}
            onTogglePlay={onTogglePlay}
            isPlaying={isPlaying}
            onFrameScale={onFrameScale}
            onSpeedChange={onSpeedChange}
            onLoopChange={onLoopChange}
            onResetVideo={onResetVideo}
            onRunPipeline={onRunPipeline}
            onOpenWeights={() => setShowWeights(true)}
            onResetAnalysis={onResetAnalysis}
            onOpenLive={() => setShowLive(true)}
            onOpenBatch={() => setShowBatch(true)}
            onGotoFrame={onGotoFrame}
            onToggleTheme={() => setDarkMode(d => !d)}
            onAnalysisModeChange={mode => updateSettings({ analysisMode: mode })}
          />
        )}

        {/* Toggle repli sidebar gauche (remplace le séparateur 1 px) */}
        <SidebarToggle
          side="left"
          open={leftSidebarOpen}
          onToggle={() => setLeftSidebarOpen(v => !v)}
        />

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
                DICOM Viewer
              </span>
              {/* Bouton disposition multi-panneaux */}
              <button
                onClick={onOpenLayoutPicker}
                title="Choose panel layout"
                style={{
                  marginLeft: 10, background: multiPanel ? '#1e3a5f' : 'none',
                  border: `1px solid ${multiPanel ? '#3b82f6' : 'transparent'}`,
                  borderRadius: 4, cursor: 'pointer',
                  color: multiPanel ? '#93c5fd' : SBAR_MUTED,
                  fontSize: 10, fontWeight: 600,
                  padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 4,
                  transition: 'background 0.15s, border-color 0.15s',
                }}
                onMouseEnter={e => { if (!multiPanel) (e.currentTarget as HTMLElement).style.background = '#1e293b'; }}
                onMouseLeave={e => { if (!multiPanel) (e.currentTarget as HTMLElement).style.background = 'none'; }}
              >
                ⊞ Layout
              </button>
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

            {/* Canvas DICOM ou vue multi-panneaux */}
            {multiPanel ? (
              <MultiPanelView
                layout={multiPanel.layout}
                tabIds={multiPanel.tabIds}
                tabs={tabs}
                activeTabId={activeTabId}
                onFocusPanel={onFocusPanel}
                onExit={onExitMultiPanel}
                onDropToPanel={onDropToPanel}
                onExpandLayout={onExpandLayout}
                onRemovePanel={onRemovePanel}
                onZoomPan={onZoomPan}
                onResetAllPanelsPan={onResetAllPanelsPan}
                onContrastBright={onContrastBright}
                onFrameChange={onCanvasFrameChange}
                onMeasureAdd={onMeasureAdd}
                onMeasureMove={onMeasureMove}
                onMeasureLabelMove={onMeasureLabelMove}
                onMeasureSelect={onMeasureSelect}
                onContextMenu={(x, y) => setCtxMenu({ x, y })}
              />
            ) : (
              <div
                style={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative', minHeight: 0 }}
                // Drop another file here → side-by-side view (split-v).
                onDragOver={e => {
                  if (!activeTab) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = 'move';
                  if (!singleViewDragOver) setSingleViewDragOver(true);
                }}
                onDragLeave={() => setSingleViewDragOver(false)}
                onDrop={e => {
                  e.preventDefault();
                  setSingleViewDragOver(false);
                  const raw = e.dataTransfer.getData('text/plain');
                  if (!raw.startsWith('starhe-tab:')) return;
                  onDropToSingleView(parseInt(raw.replace('starhe-tab:', ''), 10));
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
                {/* Indicateur de dépôt (visible pendant le glisser) */}
                {singleViewDragOver && activeTab && (
                  <div style={{
                    position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 30,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: 'rgba(59,130,246,0.10)',
                    outline: '2px dashed #3b82f6', outlineOffset: -6,
                  }}>
                    <span style={{
                      fontSize: 13, fontWeight: 700, color: '#93c5fd',
                      background: 'rgba(0,0,0,0.7)', padding: '6px 14px', borderRadius: 6,
                      display: 'flex', alignItems: 'center', gap: 6,
                    }}>⊞ Drop to compare side by side</span>
                  </div>
                )}
              </div>
            )}

            {/* Bande de vignettes — visible dans les deux modes, draggable vers les panneaux */}
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

        {/* ── Panel galerie détections (droit, repliable) ───────────────── */}
        {displaySettings.analysisMode !== 'risk_only' && activeTab && (
          <>
            <SidebarToggle
              side="right"
              open={rightSidebarOpen}
              onToggle={() => setRightSidebarOpen(v => !v)}
            />
            {rightSidebarOpen && (
              <DetectionGallery
                framesB64={activeTab.data?.framesB64 ?? []}
                detections={activeTab.detectionsBy.original ?? []}
                imgW={activeTab.data?.cols ?? 512}
                imgH={activeTab.data?.rows ?? 512}
                onGotoFrame={onGotoFrame}
                sidebarBg={displaySettings.sidebarBg}
                textColor={displaySettings.textColor}
              />
            )}
          </>
        )}
      </div>

      {/* ── Dialogues flottants ────────────────────────────────────────────── */}
      {showContrast && (
        <AdjustDialog
          title="Contrast"
          initial={activeTab?.contrast ?? 1}
          min={0.1} max={3} neutral={1}
          onClose={() => setShowContrast(false)}
          onChange={v => updateActiveTab(t => ({ ...t, contrast: v }))}
        />
      )}
      {showBrightness && (
        <AdjustDialog
          title="Brightness"
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

      {/* Sélecteur de disposition */}
      {showLayoutPicker && (
        <LayoutPickerModal
          count={tabs.length}
          onPick={layout => {
            setShowLayoutPicker(false);
            if (layout === 'single') { setMultiPanel(null); return; }
            const slots = layout === 'quad' ? 4 : 2;
            // Active tab first, then the other distinct tabs —
            // without duplicates (the same file does not appear in two panels).
            const others = tabs.map(t => t.id).filter(id => id !== activeTabId);
            const ids = [activeTabId, ...others].slice(0, slots);
            while (ids.length < slots) ids.push(-1);
            setMultiPanel({ layout, tabIds: ids });
          }}
          onCancel={() => setShowLayoutPicker(false)}
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
              const newTabId = await openBatchResultAsTab(result);
              setActiveTabId(newTabId);
            } catch (err: unknown) {
              const msg = err instanceof Error ? err.message : String(err);
              addLog(`ERREUR ouverture ${result.name} : ${msg}`, 'error');
            }
          }}
        />
      )}

      {/* Menu des poids de modèles (chargement local des .pth) */}
      {showWeights && (
        <WeightsModal onClose={() => setShowWeights(false)} />
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

// ── Sidebar collapse button ─────────────────────────────────────────────────────
// Thin discreet vertical strip (replaces the 1 px separator) with a chevron.
// Always visible — allows hiding then re-showing the adjacent panel.

function SidebarToggle({
  side,
  open,
  onToggle,
}: {
  side: 'left' | 'right';
  open: boolean;
  onToggle: () => void;
}) {
  // Chevron: "retract" the panel when open, "extend" when closed.
  const char = side === 'left'
    ? (open ? '‹' : '›')
    : (open ? '›' : '‹');
  const IDLE = '#0a0a14';
  const HOVER = '#1e1d2f';
  return (
    <div
      onClick={onToggle}
      title={open ? 'Masquer le panneau' : 'Afficher le panneau'}
      style={{
        width: 14, minWidth: 14, flexShrink: 0,
        background: IDLE, cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#6b7280',
        transition: 'background 0.15s, color 0.15s',
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLElement).style.background = HOVER;
        (e.currentTarget as HTMLElement).style.color = '#cbd5e1';
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLElement).style.background = IDLE;
        (e.currentTarget as HTMLElement).style.color = '#6b7280';
      }}
    >
      <span style={{ fontSize: 14, fontWeight: 700, lineHeight: 1 }}>{char}</span>
    </div>
  );
}

export default StarhePlugin;
