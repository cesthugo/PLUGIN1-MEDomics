// components/Sidebar.tsx — MEDomics STARHE-style left side panel
//
// Fully replicates the sidebar of prototype_tkinter.py:
//   - DICOM FILE  : loading, info, file label
//   - NAVIGATION  : ◀/▶, counter, scrubbar, play/pause, loop, speed, reset
//   - AI ANALYSIS : run / reset / live
//   - RESULTS     : mode, HCC risk, lesions, frames with tumor (clickable)
//   - METADATA    : kept + anonymized tags

import React, { useRef, useState } from 'react';
import type { TabState, LogLevel, Patient } from '../../utilities/starhe/types';
import type { AnalysisStatus } from '../../utilities/starhe/hooks/usePipelineSSE';
import {
  SIDEBAR_BG, BLUE, SBAR_FG, SBAR_MUTED,
  SUCCESS_FG, DANGER_FG, RISK_LOW_FG, RISK_HIGH_FG,
} from '../../utilities/starhe/colors';

// ── Helpers de style ──────────────────────────────────────────────────────────

const S: Record<string, React.CSSProperties> = {
  sidebar: {
    width: 270, minWidth: 270, background: SIDEBAR_BG,
    display: 'flex', flexDirection: 'column', overflowY: 'auto', flexShrink: 0,
    fontFamily: "'Segoe UI', system-ui, sans-serif",
    userSelect: 'none',
  },
  scrollArea: { flex: 1, overflowY: 'auto', overflowX: 'hidden' },
  footer: {
    borderTop: '1px solid #0d0d1a', background: '#0d0d1a',
    flexShrink: 0,
  },
  sectionHeader: {
    display: 'flex', alignItems: 'stretch',
    padding: '16px 10px 4px', gap: 6,
  },
  sectionAccent: { width: 3, background: BLUE, borderRadius: 2, alignSelf: 'stretch' },
  sectionTitle: {
    fontSize: 11, fontWeight: 700, color: '#9ca3af',
    letterSpacing: '0.05em', textTransform: 'uppercase',
    paddingLeft: 4,
  },
  label: { fontSize: 11, color: SBAR_MUTED, padding: '2px 14px' },
  muted: { fontSize: 11, color: SBAR_MUTED, fontFamily: "'Consolas', monospace" },
  mono: {
    fontFamily: "'Consolas', monospace", fontSize: 11,
    background: '#111827', color: '#6ee7b7',
    padding: '4px 10px', margin: '2px 10px 4px',
    borderRadius: 4, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
    maxHeight: 160, overflowY: 'auto',
  },
  monoRed: {
    fontFamily: "'Consolas', monospace", fontSize: 11,
    background: '#1a0a0a', color: DANGER_FG,
    padding: '4px 10px', margin: '2px 10px 4px',
    borderRadius: 4, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
    maxHeight: 180, overflowY: 'auto',
  },
};

// ── Bouton MEDomics (fond noir, texte blanc, hover sombre) ───────────────────

function SBtn({
  children, onClick, disabled = false, primary = false,
  accent = false, small = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
  accent?: boolean;
  small?: boolean;
}) {
  const bg = primary ? '#000000' : accent ? '#0d4f8c' : '#000000';
  return (
    <button
      onClick={disabled ? undefined : onClick}
      style={{
        display: 'block', width: '100%', textAlign: 'left',
        background: disabled ? '#1a1a2a' : bg,
        color: disabled ? '#555' : '#ffffff',
        border: 'none', cursor: disabled ? 'default' : 'pointer',
        padding: small ? '5px 14px' : primary ? '9px 14px' : '6px 14px',
        fontSize: small ? 11 : 13,
        fontWeight: 700,
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        borderRadius: 0,
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => { if (!disabled) (e.target as HTMLElement).style.background = '#1e1e2e'; }}
      onMouseLeave={e => { if (!disabled) (e.target as HTMLElement).style.background = bg; }}
    >
      {children}
    </button>
  );
}

// ── Navigation icon button ────────────────────────────────────────────────────

function NavBtn({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: '#000', color: '#fff', border: 'none',
        cursor: 'pointer', fontSize: 16, fontWeight: 700,
        padding: '4px 8px', borderRadius: 3,
        fontFamily: "'Segoe UI', sans-serif",
      }}
    >
      {children}
    </button>
  );
}

// ── Section header ────────────────────────────────────────────────────────────

function SH({ title }: { title: string }) {
  return (
    <div style={S.sectionHeader}>
      <div style={S.sectionAccent} />
      <span style={S.sectionTitle}>{title}</span>
    </div>
  );
}

// ── Result row (label + colored value) ────────────────────────────────────────

function ResultRow({ label, value, fg }: { label: string; value: string; fg: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', padding: '2px 14px', gap: 6 }}>
      <span style={{ fontSize: 11, color: SBAR_MUTED, flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 700, color: fg }}>{value}</span>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface SidebarProps {
  tab:            TabState | null;
  analysisStatus: AnalysisStatus;
  darkMode:       boolean;
  /** Sidebar background color (from the display settings) */
  sidebarBg?:     string;
  /** Main text color (from the display settings) */
  textColor?:     string;
  /** AI models to run (from the display settings) */
  analysisMode?:  'both' | 'risk_only' | 'detect_only';
  /** Callback to change the analysis mode from the sidebar */
  onAnalysisModeChange?: (mode: 'both' | 'risk_only' | 'detect_only') => void;

  onLoadDicom:      () => void;
  /** Manual selection of individual DICOM files */
  onLoadDicomFiles: () => void;
  /** Direct loading of an MP4 file */
  onLoadMp4?:       () => void;
  /** Direct loading by absolute path (browser dev mode, outside Electron) */
  onLoadPath:       (path: string) => void;
  onPrevFrame:      () => void;
  onNextFrame:      () => void;
  onTogglePlay:     () => void;
  isPlaying:        boolean;
  onFrameScale:     (idx: number) => void;
  onSpeedChange:    (v: number) => void;
  onLoopChange:     (v: boolean) => void;
  onResetVideo:     () => void;
  onRunPipeline:    () => void;
  onResetAnalysis:  () => void;
  onOpenLive:       () => void;
  onOpenBatch:      () => void;
  onGotoFrame:      (idx: number) => void;
  onToggleTheme:    () => void;
}


export function Sidebar({
  tab,
  analysisStatus,
  darkMode,
  sidebarBg,
  textColor,
  analysisMode = 'both',
  onAnalysisModeChange,
  onLoadDicom,
  onLoadDicomFiles,
  onLoadMp4,
  onLoadPath,
  onPrevFrame,
  onNextFrame,
  onTogglePlay,
  isPlaying,
  onFrameScale,
  onSpeedChange,
  onLoopChange,
  onResetVideo,
  onRunPipeline,
  onResetAnalysis,
  onOpenLive,
  onOpenBatch,
  onGotoFrame,
  onToggleTheme,
}: SidebarProps) {
  const [pathInput,       setPathInput]       = useState('');
  const [showModelPicker, setShowModelPicker] = useState(false);
  // Electron detection: via the preload API (reliable method with contextIsolation)
  const isElectron = typeof window !== 'undefined' &&
    (window.electronAPI !== undefined ||
     navigator.userAgent.includes('Electron'));
  const data      = tab?.data ?? null;
  const frameIdx  = tab?.frameIdx ?? 0;
  const frameCount = data?.frameCount ?? 0;
  const speed     = tab?.speedMult ?? 1.0;
  const loop      = tab?.loop ?? true;

  const speedRef = useRef<HTMLInputElement>(null);

  // AI results
  const mode        = tab ? (tab.detectionsBy.original ? 'original' : null) : null;
  const result      = mode ? tab?.resultsBy[mode] : null;

  // Metadata
  const keptMeta       = data?.keptMetadata ?? [];
  const origSensitive  = data?.originalSensitive ?? [];

  return (
    <div style={{ ...S.sidebar, background: sidebarBg ?? S.sidebar.background, ...(textColor ? { color: textColor } : {}) }}>
      {/* ── Zone scrollable ──────────────────────────────────────────────── */}
      <div style={S.scrollArea}>

        {/* FICHIER DICOM */}
        <SH title="DICOM file" />
        <div style={{ padding: '6px 10px 3px' }}>
          {/* Bouton fractionné : dossier entier | fichiers individuels */}
          <div style={{ display: 'flex', width: '100%', gap: 0 }}>
            <button
              onClick={onLoadDicom}
              title="Select a folder — loads all DICOM files inside"
              style={{
                flex: 1, display: 'flex', alignItems: 'center', gap: 6,
                background: '#131f2e', border: '1px solid #1e2d45',
                borderRight: 'none', borderRadius: '5px 0 0 5px',
                color: '#7eb8f7', fontSize: 12, fontWeight: 600,
                padding: '6px 10px', cursor: 'pointer',
                transition: 'background 0.12s, border-color 0.12s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = '#1a2d44'; (e.currentTarget as HTMLButtonElement).style.borderColor = '#2563eb'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = '#131f2e'; (e.currentTarget as HTMLButtonElement).style.borderColor = '#1e2d45'; }}
            >
              <span style={{ fontSize: 14 }}>📁</span> DICOM Folder
            </button>
            <div style={{ width: 1, background: '#1e2d45', flexShrink: 0 }} />
            <button
              onClick={onLoadDicomFiles}
              title="Manually select one or more DICOM files"
              style={{
                flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: '#131f2e', border: '1px solid #1e2d45',
                borderLeft: 'none', borderRadius: '0 5px 5px 0',
                color: '#7eb8f7', fontSize: 13, padding: '6px 9px', cursor: 'pointer',
                transition: 'background 0.12s, border-color 0.12s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = '#1a2d44'; (e.currentTarget as HTMLButtonElement).style.borderColor = '#2563eb'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = '#131f2e'; (e.currentTarget as HTMLButtonElement).style.borderColor = '#1e2d45'; }}
            >
              🗂️
            </button>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 2px 0' }}>
            <span style={{ fontSize: 9, color: '#475569', flex: 1, textAlign: 'center' }}>Entire folder</span>
            <span style={{ fontSize: 9, color: '#475569', width: 36, textAlign: 'center' }}>Files</span>
          </div>
          {/* Bouton MP4 */}
          {onLoadMp4 && (
            <div style={{ marginTop: 5 }}>
              <button
                onClick={onLoadMp4}
                title="Load an MP4 file directly (without DICOM)"
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 6,
                  background: '#141e14', border: '1px solid #1e3d1e',
                  borderRadius: 5, color: '#7ed87e', fontSize: 12, fontWeight: 600,
                  padding: '6px 10px', cursor: 'pointer',
                  transition: 'background 0.12s, border-color 0.12s',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = '#1a3020'; (e.currentTarget as HTMLButtonElement).style.borderColor = '#22c55e'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = '#141e14'; (e.currentTarget as HTMLButtonElement).style.borderColor = '#1e3d1e'; }}
              >
                <span style={{ fontSize: 14 }}>📹</span> Load MP4
              </button>
            </div>
          )}
        </div>
        {/* Saisie chemin direct — visible uniquement hors Electron (dev navigateur) */}
        {!isElectron && (
          <div style={{ padding: '2px 10px 6px' }}>
            <form
              onSubmit={e => {
                e.preventDefault();
                const p = pathInput.trim();
                if (p) { onLoadPath(p); setPathInput(''); }
              }}
              style={{ display: 'flex', gap: 4 }}
            >
              <input
                value={pathInput}
                onChange={e => setPathInput(e.target.value)}
                placeholder="/absolute/path/file.dcm"
                style={{
                  flex: 1, background: '#0d0d14', border: '1px solid #2a3245',
                  borderRadius: 3, color: SBAR_FG, fontSize: 10,
                  padding: '3px 6px', outline: 'none',
                }}
                title="Dev mode — enter the absolute path of the DICOM file"
              />
              <button
                type="submit"
                style={{
                  background: '#1a2240', border: '1px solid #2a3245',
                  borderRadius: 3, color: SBAR_FG, cursor: 'pointer',
                  fontSize: 11, padding: '2px 7px',
                }}
              >↵</button>
            </form>
          </div>
        )}
        <div style={{ padding: '2px 14px 0', fontSize: 11, color: data ? SBAR_FG : SBAR_MUTED, wordBreak: 'break-all' }}>
          {data ? data.fileName : 'No file selected'}
        </div>
        {data && (
          <div style={{ padding: '2px 14px 6px', fontSize: 11, color: SBAR_MUTED, fontFamily: "'Consolas', monospace", lineHeight: 1.7 }}>
            Modality : {data.modality}{'\n'}
            Size     : {data.rows}×{data.cols}{'\n'}
            Frames   : {data.frameCount}{'\n'}
            Pixel    : {data.pixelSpacing ? `${data.pixelSpacing[0].toFixed(3)} mm/px` : 'N/A'}
          </div>
        )}

        {/* NAVIGATION */}
        <SH title="Navigation" />
        <div style={{ display: 'flex', alignItems: 'center', padding: '6px 10px 2px', gap: 6 }}>
          <NavBtn onClick={onPrevFrame}>◀</NavBtn>
          <span style={{ flex: 1, textAlign: 'center', fontSize: 18, fontWeight: 700, color: '#fff' }}>
            {frameCount > 0 ? `${frameIdx + 1} / ${frameCount}` : '— / —'}
          </span>
          <NavBtn onClick={onNextFrame}>▶</NavBtn>
        </div>

        {/* Scrubbar */}
        <div style={{ padding: '0 10px 2px' }}>
          <input
            ref={speedRef}
            type="range"
            min={0}
            max={Math.max(1, frameCount - 1)}
            value={frameIdx}
            step={1}
            style={{ width: '100%', accentColor: BLUE }}
            onChange={e => onFrameScale(Number(e.target.value))}
          />
        </div>

        <div style={{ padding: '2px 10px 2px' }}>
          <SBtn onClick={onTogglePlay}>
            {isPlaying ? '⏸   Pause' : '▶   Play'}
          </SBtn>
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '2px 16px', fontSize: 11, color: SBAR_FG, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={loop}
            onChange={e => onLoopChange(e.target.checked)}
            style={{ accentColor: BLUE }}
          />
          Loop
        </label>

        <div style={{ padding: '2px 10px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0 4px', fontSize: 11, color: SBAR_MUTED }}>
            <span>Speed:</span>
            <span style={{ color: SBAR_FG }}>×{speed.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0.25}
            max={3.0}
            step={0.25}
            value={speed}
            style={{ width: '100%', accentColor: BLUE }}
            onChange={e => onSpeedChange(Number(e.target.value))}
          />
        </div>

        <div style={{ padding: '0 10px 6px' }}>
          <SBtn onClick={onResetVideo} small>⏮   Go to start</SBtn>
        </div>

        {/* ANALYSE IA */}
        <SH title="AI Analysis" />

        {/* ── Sélecteur de modèles (dropdown) ────────────────────────── */}
        <div style={{ padding: '6px 10px 2px' }}>
          <button
            onClick={() => setShowModelPicker(v => !v)}
            style={{
              width: '100%', display: 'flex', alignItems: 'center',
              justifyContent: 'space-between',
              background: showModelPicker ? '#0d1f3a' : '#0d0d14',
              border: `1px solid ${showModelPicker ? BLUE : '#2a3245'}`,
              borderRadius: 4, padding: '5px 10px',
              color: SBAR_FG, fontSize: 11, cursor: 'pointer',
            }}
          >
            <span>
              🤖&nbsp;&nbsp;Models&nbsp;:
              <span style={{ color: '#93c5fd', marginLeft: 6, fontWeight: 700 }}>
                {analysisMode === 'both'        ? 'RISK + DETECT'
                 : analysisMode === 'risk_only' ? 'RISK'
                 :                               'DETECT'}
              </span>
            </span>
            <span style={{ fontSize: 9, color: SBAR_MUTED }}>{showModelPicker ? '▲' : '▼'}</span>
          </button>

          {showModelPicker && (
            <div style={{
              background: '#0d1117', border: `1px solid ${BLUE}`,
              borderTop: 'none', borderRadius: '0 0 4px 4px',
              padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 8,
            }}>
              {([
                { key: 'risk',   label: 'STARHE RISK',   desc: 'HCC risk (C3D)' },
                { key: 'detect', label: 'STARHE DETECT', desc: 'Lesion detection (RTMDet)' },
              ] as const).map(({ key, label, desc }) => {
                const checked = key === 'risk'
                  ? analysisMode !== 'detect_only'
                  : analysisMode !== 'risk_only';
                return (
                  <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={checked}
                      style={{ accentColor: BLUE, width: 14, height: 14, flexShrink: 0 }}
                      onChange={e => {
                        if (!onAnalysisModeChange) return;
                        const nowRisk   = key === 'risk'   ? e.target.checked : analysisMode !== 'detect_only';
                        const nowDetect = key === 'detect' ? e.target.checked : analysisMode !== 'risk_only';
                        // Prevents unchecking both
                        if (!nowRisk && !nowDetect) return;
                        onAnalysisModeChange(
                          nowRisk && nowDetect ? 'both'
                          : nowRisk            ? 'risk_only'
                          :                     'detect_only'
                        );
                      }}
                    />
                    <div>
                      <div style={{ color: checked ? '#93c5fd' : SBAR_FG, fontSize: 11, fontWeight: 700 }}>{label}</div>
                      <div style={{ color: SBAR_MUTED, fontSize: 10 }}>{desc}</div>
                    </div>
                  </label>
                );
              })}
            </div>
          )}
        </div>

        <div style={{ padding: '4px 10px 4px' }}>
          <SBtn
            onClick={onRunPipeline}
            disabled={!data || analysisStatus === 'running'}
            primary
          >
            {'\uD83E\uDDE0\u2003'}
            {analysisMode === 'both'        ? 'Run STARHE RISK + DETECT' :
             analysisMode === 'risk_only'   ? 'Run STARHE RISK' :
                                             'Run STARHE DETECT'}
          </SBtn>
        </div>
        <div style={{ padding: '0 10px 4px' }}>
          <SBtn onClick={onResetAnalysis} disabled={!data} small>
            🗑   Reset analysis
          </SBtn>
        </div>
        <div style={{ padding: '0 10px 4px' }}>
          <SBtn onClick={onOpenLive} accent>📡   Live analysis</SBtn>
        </div>
        <div style={{ padding: '0 10px 10px' }}>
          <SBtn onClick={onOpenBatch} accent>📋   Batch analysis</SBtn>
        </div>

        {/* RÉSULTATS */}
        <SH title="Results" />
        <ResultRow
          label="Mode :"
          value={
            !mode ? '—'
              : analysisMode === 'risk_only'   ? 'STARHE RISK'
              : analysisMode === 'detect_only' ? 'STARHE DETECT'
              : 'STARHE RISK + DETECT'
          }
          fg={mode ? '#93c5fd' : SBAR_MUTED}
        />
        {analysisMode !== 'detect_only' && (
          <ResultRow
            label="HCC Risk (STARHE RISK):"
            value={result?.riskText || (mode ? '—' : '—')}
            fg={result?.riskFg ?? SBAR_MUTED}
          />
        )}
        {analysisMode !== 'risk_only' && (
          <ResultRow
            label="Lesions (STARHE DETECT):"
            value={result?.detText ?? (analysisStatus === 'running' ? '⏳ analyzing…' : '—')}
            fg={result?.detFg ?? SBAR_MUTED}
          />
        )}

        {/* MÉTADONNÉES CONSERVÉES */}
        <SH title="Preserved metadata" />
        <div style={S.mono}>
          {keptMeta.length === 0
            ? '  (no metadata found)'
            : keptMeta.map(([lbl, val]) => {
              const valS = val.length > 24 ? val.slice(0, 21) + '…' : val;
              return `  ${lbl.padEnd(14)} ${valS}\n`;
            }).join('')}
        </div>

        {/* TAGS ANONYMISÉS */}
        <SH title="Anonymized tags" />
        <div style={S.monoRed}>
          {origSensitive.length === 0
            ? '  (no sensitive tag found)'
            : origSensitive.map(([name, val]) => {
              const valS = val.length > 22 ? val.slice(0, 19) + '…' : val;
              return `  ✗ ${name.padEnd(20)} ${valS}\n`;
            }).join('')}
        </div>

      </div>{/* end scrollArea */}

      {/* ── Pied de sidebar : thème ──────────────────────────────────────── */}
      <div style={S.footer}>
        <SBtn onClick={onToggleTheme} small>
          {darkMode ? '☀   Light theme' : '🌙   Dark theme'}
        </SBtn>
      </div>
    </div>
  );
}
