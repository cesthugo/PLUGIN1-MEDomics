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
  useCallback, useEffect, useMemo, useState,
} from 'react';

import type {
  TabState, Patient, LogEntry, LogLevel, ViewMode, Measure,
} from './types';
import {
  SIDEBAR_BG, SIDEBAR_HOV, MAIN_BG, CARD_BG, CARD_BORDER, CARD_SHADOW,
  BLUE, BLUE_TEXT, SBAR_FG, SBAR_MUTED, BORDER, CANVAS_BG,
} from './colors';
import { loadDicom, loadDicomFile, deleteCache } from './api';
import medomicsLogo from '../assets/medomics_logo.png';
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
import { PatientTabBar }       from './components/PatientTabBar';
import { FileThumbnailStrip }  from './components/FileThumbnailStrip';
import { MultiPanelView }      from './components/MultiPanelView';
import { useTabManager }       from './hooks/useTabManager';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { isDicomFile }         from './utils';

// ── ID auto-incrémenté ────────────────────────────────────────────────────────
let _nextLogId = 1;
const nextLogId = () => _nextLogId++;

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
  // ── Logs ────────────────────────────────────────────────────────────────────
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const addLog = useCallback((message: string, level: LogLevel = 'info') => {
    setLogs(prev => [...prev.slice(-200), { id: nextLogId(), level, message }]);
  }, []);

  // ── Lecture vidéo ──────────────────────────────────────────────────────────
  const [isPlaying, setIsPlaying] = useState(false);

  // ── Onglets et patients (via hook) ─────────────────────────────────────────
  const {
    tabs, activeTabId, patients, activePatientName,
    activeTab, activeTabIdx, activePatientIdx,
    addTab, openBatchResultAsTab,
    switchTab, closeTab, updateActiveTab, updateTabById,
    setActiveTabId, setActivePatientName,
  } = useTabManager({ addLog, isPlaying, setIsPlaying });

  const handleFrameChange = useCallback((idx: number) => {
    updateActiveTab(t => ({ ...t, frameIdx: idx }));
  }, [updateActiveTab]);

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

  // ── Pipeline SSE ───────────────────────────────────────────────────────────
  const { status: analysisStatus, progress, startAnalysis, cancelAnalysis, lastResult }
    = usePipelineSSE(addLog);

  // Onglet pour lequel l'analyse a été lancée (ID stable, indépendant de l'onglet actif)
  const [analysisTargetTabId, setAnalysisTargetTabId] = useState<number>(-1);

  // Quand un résultat arrive, l'injecter dans l'onglet *cible* (pas nécessairement l'actif)
  useEffect(() => {
    if (!lastResult || analysisTargetTabId < 0) return;
    updateTabById(analysisTargetTabId, t => ({
      ...t,
      detectionsBy: { ...t.detectionsBy, original: lastResult.detectionsPerFrame },
      resultsBy:    { ...t.resultsBy,    original: lastResult.result },
    }));
  }, [lastResult, analysisTargetTabId, updateTabById]);

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
      const input = document.createElement('input');
      input.type = 'file';
      (input as any).webkitdirectory = true;
      (input as any).multiple = true;
      input.onchange = async () => {
        for (const file of Array.from(input.files ?? []).filter(isDicomFile)) {
          await doLoadFile(file);
        }
      };
      input.click();
    }
  }, [isElectron, doLoadPath, doLoadFile]);

  // Sélection manuelle de fichiers DICOM individuels
  const onLoadDicomFiles = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.onchange = async () => {
      for (const file of Array.from(input.files ?? []).filter(isDicomFile)) {
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

  // ── Raccourcis clavier ─────────────────────────────────────────────────────────────────
  useKeyboardShortcuts({
    activeTab, activePatientIdx, patients,
    switchTab, closeTab,
    onTogglePlay, onPrevFrame, onNextFrame, onResetVideo,
    onToggleViewMode, onResetView, updateActiveTab,
    setShowContrast, setShowBrightness,
  });

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


export default StarhePlugin;
