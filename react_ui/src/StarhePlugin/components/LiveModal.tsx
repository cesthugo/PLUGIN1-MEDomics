// components/LiveModal.tsx — Porte React de l'onglet "Analyse en direct"
//
// Réplique LiveTab (live_tab.py) avec les 3 sources :
//   - 📡  C-STORE DICOM  (port configurable)
//   - 📂  Dossier (polling, .dcm)
//   - 🎥  HDMI (carte de capture)
//
// Toutes les opérations backend sont déléguées au serveur Go via SSE.
// Le serveur Go lance live_pipeline.py dans un subprocess avec la source choisie.

import React, { useCallback, useRef, useState } from 'react';
import { API_BASE } from '../api';
import type { Detection, LogLevel } from '../types';
import {
  SIDEBAR_BG, MAIN_BG, CANVAS_BG, BLUE, BLUE_TEXT,
  SBAR_FG, SBAR_MUTED, CARD_BG, CARD_BORDER, CARD_SHADOW,
  RISK_LOW_FG, RISK_HIGH_FG, RISK_MED_FG, WARN_FG, SUCCESS_FG, DANGER_FG,
} from '../colors';

// Colors that live_tab.py defines but colors.ts doesn't yet
const RISK_MED = '#fbbf24';

// ── Types ─────────────────────────────────────────────────────────────────────

type LiveSource = 'cstore' | 'folder' | 'hdmi';

interface LiveState {
  running: boolean;
  fps:     number;
  frames:  number;
  riskText: string;
  riskFg:   string;
  detText:  string;
  detFg:    string;
  lastFrameB64: string | null;
  lastDets:     Detection[];
}

// ── Bouton sidebar ──────────────────────────────────────────────────────────

function LBtn({
  children, onClick, primary = false, disabled = false,
}: { children: React.ReactNode; onClick: () => void; primary?: boolean; disabled?: boolean }) {
  const bg = primary ? BLUE : '#000';
  return (
    <button
      onClick={disabled ? undefined : onClick}
      style={{
        display: 'block', width: '100%', textAlign: 'left',
        background: disabled ? '#1a1a2a' : bg,
        color: disabled ? '#555' : '#fff',
        border: 'none', cursor: disabled ? 'default' : 'pointer',
        padding: '7px 14px', fontSize: 13, fontWeight: 700,
        fontFamily: "'Segoe UI', system-ui, sans-serif",
      }}
    >
      {children}
    </button>
  );
}

function SH({ title }: { title: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'stretch', padding: '14px 10px 4px', gap: 6 }}>
      <div style={{ width: 3, background: BLUE, borderRadius: 2 }} />
      <span style={{ fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase', paddingLeft: 4 }}>
        {title}
      </span>
    </div>
  );
}

// ── Composant principal ───────────────────────────────────────────────────────

export interface LiveModalProps {
  onClose: () => void;
  addLog:  (msg: string, level: LogLevel) => void;
}

export function LiveModal({ onClose, addLog }: LiveModalProps) {
  const [source,    setSource]   = useState<LiveSource>('cstore');
  const [cstorePort, setCstorePort] = useState('11112');
  const [folderPath, setFolderPath] = useState('');
  const [hdmiDevice, setHdmiDevice] = useState('0');
  const [state, setState] = useState<LiveState>({
    running: false, fps: 0, frames: 0,
    riskText: '—', riskFg: SBAR_MUTED,
    detText: '—', detFg: SBAR_MUTED,
    lastFrameB64: null, lastDets: [],
  });

  const abortRef = useRef<AbortController | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // ── Dessin du frame live ────────────────────────────────────────────────────

  const drawLiveFrame = useCallback((b64: string, dets: Detection[]) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const img = new Image();
    img.onload = () => {
      canvas.width  = img.naturalWidth;
      canvas.height = img.naturalHeight;
      ctx.drawImage(img, 0, 0);
      for (const det of dets) {
        const [x0, y0, x1, y1] = det.bbox;
        const isTumor = det.label.includes('tumor');
        ctx.strokeStyle = isTumor ? 'rgb(255,80,80)' : 'rgb(80,200,80)';
        ctx.lineWidth = 2;
        ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
        ctx.fillStyle = isTumor ? 'rgb(255,80,80)' : 'rgb(80,200,80)';
        ctx.font = '13px sans-serif';
        ctx.fillText(`${det.label} ${det.score.toFixed(2)}`, x0, Math.max(y0 - 4, 12));
      }
    };
    img.src = `data:image/jpeg;base64,${b64}`;
  }, []);

  // ── Démarrage de l'analyse live ────────────────────────────────────────────

  const startLive = useCallback(async () => {
    if (state.running) return;
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const body: Record<string, string | number> = { source };
    if (source === 'cstore')  body.port        = Number(cstorePort);
    if (source === 'folder')  body.folder_path = folderPath;
    if (source === 'hdmi')    body.device      = Number(hdmiDevice);

    setState(s => ({ ...s, running: true, fps: 0, frames: 0 }));
    addLog('Démarrage de l\'analyse en direct…', 'info');

    try {
      const res = await fetch(`${API_BASE}/starhe/live`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
        signal:  ctrl.signal,
      });
      if (!res.ok || !res.body) {
        const j = await res.json().catch(() => ({}));
        throw new Error((j as any).error ?? `HTTP ${res.status}`);
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';
      let   frameCount = 0;
      let   lastFpsTs  = Date.now();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') { setState(s => ({ ...s, running: false })); return; }
          try {
            const payload = JSON.parse(raw);
            if (payload.data?.frame_b64) {
              frameCount++;
              const now = Date.now();
              const fps = now - lastFpsTs > 0 ? Math.round(1000 / (now - lastFpsTs)) : 0;
              lastFpsTs = now;
              const dets: Detection[] = payload.data.detections ?? [];
              drawLiveFrame(payload.data.frame_b64, dets);
              const nDet = dets.length;
              setState(s => ({
                ...s,
                fps,
                frames: frameCount,
                lastFrameB64: payload.data.frame_b64,
                lastDets: dets,
                detText: `${nDet} détection(s)`,
                detFg:   nDet > 0 ? WARN_FG : SUCCESS_FG,
              }));
            }
            if (payload.data?.risk) {
              const { score, label } = payload.data.risk;
              const riskFg = /élevé|high/i.test(label) ? RISK_HIGH_FG : RISK_LOW_FG;
              setState(s => ({ ...s, riskText: `${label} (${(score * 100).toFixed(1)} %)`, riskFg }));
            }
            if (payload.level === 'error') {
              addLog(payload.message, 'error');
            }
          } catch { /* ligne malformée */ }
        }
      }
    } catch (err: unknown) {
      if ((err as Error)?.name !== 'AbortError') {
        addLog(`Erreur live : ${(err as Error).message}`, 'error');
      }
    } finally {
      setState(s => ({ ...s, running: false }));
    }
  }, [source, cstorePort, folderPath, hdmiDevice, addLog, drawLiveFrame, state.running]);

  const stopLive = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState(s => ({ ...s, running: false }));
    addLog('Analyse en direct arrêtée.', 'info');
  }, [addLog]);

  // ── Rendu ─────────────────────────────────────────────────────────────────

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.55)',
        zIndex: 8000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: MAIN_BG,
          borderRadius: 8,
          width: '90vw', maxWidth: 960,
          height: '80vh',
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 16px 48px rgba(0,0,0,0.7)',
        }}
      >
        {/* En-tête */}
        <div
          style={{
            background: '#151521',
            padding: '10px 16px',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            borderBottom: '1px solid #0a0a14',
          }}
        >
          <span style={{ color: SBAR_FG, fontWeight: 700, fontSize: 14, fontFamily: "'Segoe UI', sans-serif" }}>
            📡 STARHE — Analyse en direct
          </span>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: SBAR_MUTED, fontSize: 20, lineHeight: 1,
            }}
          >×</button>
        </div>

        {/* Corps */}
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

          {/* Panneau gauche */}
          <div
            style={{
              width: 260, background: SIDEBAR_BG, overflowY: 'auto',
              fontFamily: "'Segoe UI', system-ui, sans-serif",
            }}
          >
            <SH title="Source" />
            <div style={{ padding: '4px 10px 8px' }}>
              {(['cstore', 'folder', 'hdmi'] as LiveSource[]).map(src => (
                <label
                  key={src}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '5px 4px', cursor: 'pointer', fontSize: 12, color: SBAR_FG,
                  }}
                >
                  <input
                    type="radio" name="live-source" value={src}
                    checked={source === src}
                    onChange={() => setSource(src)}
                    style={{ accentColor: BLUE }}
                  />
                  {src === 'cstore' ? '📡  C-STORE DICOM'
                    : src === 'folder' ? '📂  Dossier'
                    : '🎥  HDMI (capture)'}
                </label>
              ))}
            </div>

            {/* Paramètres selon la source */}
            {source === 'cstore' && (
              <>
                <SH title="Port C-STORE" />
                <div style={{ padding: '4px 10px 8px' }}>
                  <input
                    type="number" value={cstorePort}
                    onChange={e => setCstorePort(e.target.value)}
                    style={{
                      width: '100%', boxSizing: 'border-box',
                      padding: '5px 8px', fontSize: 12,
                      background: '#1e1d2f', color: SBAR_FG,
                      border: '1px solid #2a2a4e', borderRadius: 4,
                    }}
                  />
                  <div style={{ fontSize: 10, color: SBAR_MUTED, marginTop: 4 }}>
                    AE Title : STARHE_LIVE
                  </div>
                </div>
              </>
            )}

            {source === 'folder' && (
              <>
                <SH title="Dossier à surveiller" />
                <div style={{ padding: '4px 10px 8px' }}>
                  <input
                    type="text" value={folderPath}
                    onChange={e => setFolderPath(e.target.value)}
                    placeholder="/chemin/vers/dossier"
                    style={{
                      width: '100%', boxSizing: 'border-box',
                      padding: '5px 8px', fontSize: 12,
                      background: '#1e1d2f', color: SBAR_FG,
                      border: '1px solid #2a2a4e', borderRadius: 4,
                    }}
                  />
                </div>
              </>
            )}

            {source === 'hdmi' && (
              <>
                <SH title="Périphérique HDMI" />
                <div style={{ padding: '4px 10px 8px' }}>
                  <input
                    type="number" value={hdmiDevice}
                    onChange={e => setHdmiDevice(e.target.value)}
                    style={{
                      width: '100%', boxSizing: 'border-box',
                      padding: '5px 8px', fontSize: 12,
                      background: '#1e1d2f', color: SBAR_FG,
                      border: '1px solid #2a2a4e', borderRadius: 4,
                    }}
                  />
                  <div style={{ fontSize: 10, color: SBAR_MUTED, marginTop: 4 }}>
                    Index cv2.VideoCapture
                  </div>
                </div>
              </>
            )}

            <SH title="Contrôles" />
            <div style={{ padding: '4px 10px 8px' }}>
              {!state.running
                ? <LBtn onClick={startLive} primary>▶   Démarrer</LBtn>
                : <LBtn onClick={stopLive}>⏹   Arrêter</LBtn>
              }
            </div>

            <SH title="Statistiques" />
            <div style={{ padding: '4px 14px 8px', fontSize: 11, color: SBAR_FG, lineHeight: 2, fontFamily: "'Consolas', monospace" }}>
              FPS    : <span style={{ color: SUCCESS_FG }}>{state.fps}</span>{'\n'}
              Frames : {state.frames}
            </div>

            <SH title="Résultats" />
            <div style={{ padding: '4px 14px 8px' }}>
              <div style={{ fontSize: 11, color: SBAR_MUTED }}>
                Risque CHC :{' '}
                <span style={{ fontSize: 12, fontWeight: 700, color: state.riskFg }}>
                  {state.riskText}
                </span>
              </div>
              <div style={{ fontSize: 11, color: SBAR_MUTED, marginTop: 4 }}>
                Lésions : <span style={{ fontSize: 12, fontWeight: 700, color: state.detFg }}>{state.detText}</span>
              </div>
            </div>
          </div>

          {/* Zone canvas */}
          <div
            style={{
              flex: 1, background: CANVAS_BG,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              overflow: 'hidden',
            }}
          >
            {state.running || state.lastFrameB64 ? (
              <canvas
                ref={canvasRef}
                style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
              />
            ) : (
              <div
                style={{
                  color: '#2a2a3e',
                  fontSize: 14,
                  fontFamily: "'Segoe UI', sans-serif",
                  textAlign: 'center',
                }}
              >
                {state.running
                  ? '⏳ En attente du premier frame…'
                  : 'Lancez l\'analyse pour voir le flux en direct'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
