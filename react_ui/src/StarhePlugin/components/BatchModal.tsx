// components/BatchModal.tsx — Analyse batch multi-fichiers STARHE
//
// Permet d'analyser plusieurs fichiers DICOM séquentiellement (un à la fois
// pour éviter les conflits mémoire du pipeline Python).
//
// Chaque entrée passe par les états :
//   waiting → loading → analyzing → done | error
//
// À la fin, un tableau récapitulatif affiche risk score + nb lésions / fichier.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { loadDicom, loadDicomFile, streamAnalysis } from '../api';
import type { AnalyzeRequest } from '../api';
import type { Detection } from '../types';
import {
  SIDEBAR_BG, MAIN_BG, BLUE, SBAR_FG, SBAR_MUTED,
  CARD_BG, CARD_BORDER, CARD_SHADOW,
  RISK_LOW_FG, RISK_HIGH_FG, SUCCESS_FG, DANGER_FG, WARN_FG,
} from '../colors';

// ── Types ─────────────────────────────────────────────────────────────────────

type ItemStatus = 'waiting' | 'loading' | 'analyzing' | 'done' | 'error';

interface BatchItem {
  id:        number;
  /** Nom affiché (nom de fichier ou chemin court) */
  name:      string;
  /** Chemin absolu côté serveur (rempli après loadDicom) */
  serverPath: string;
  /** File object si upload navigateur, undefined si chemin absolu */
  file?:     File;
  status:    ItemStatus;
  progress:  string;
  /** Résultats si status === 'done' */
  riskScore?: number;
  riskLabel?: string;
  detCount?:  number;
  /** Message d'erreur si status === 'error' */
  error?:    string;
}

let _id = 1;
const uid = () => _id++;

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusIcon(s: ItemStatus): string {
  switch (s) {
    case 'waiting':   return '⏳';
    case 'loading':   return '📂';
    case 'analyzing': return '🔬';
    case 'done':      return '✅';
    case 'error':     return '❌';
  }
}

function statusColor(s: ItemStatus): string {
  switch (s) {
    case 'done':      return SUCCESS_FG;
    case 'error':     return DANGER_FG;
    case 'analyzing': return BLUE;
    case 'loading':   return WARN_FG;
    default:          return SBAR_MUTED;
  }
}

function riskColor(label?: string): string {
  if (!label) return SBAR_MUTED;
  return /élevé|high/i.test(label) ? RISK_HIGH_FG : RISK_LOW_FG;
}

// ── Sous-composant : ligne de la queue ────────────────────────────────────────

function BatchRow({ item, onRemove }: { item: BatchItem; onRemove: () => void }) {
  const isActive = item.status === 'loading' || item.status === 'analyzing';
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '22px 1fr auto',
      alignItems: 'center',
      gap: 8,
      padding: '6px 10px',
      borderBottom: `1px solid ${CARD_BORDER}`,
      background: isActive ? '#0d1a2a' : 'transparent',
    }}>
      {/* Icône statut */}
      <span style={{ fontSize: 14 }}>{statusIcon(item.status)}</span>

      {/* Nom + progression */}
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontSize: 12, color: SBAR_FG, fontWeight: 600,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {item.name}
        </div>
        <div style={{ fontSize: 11, color: statusColor(item.status) }}>
          {item.status === 'done'
            ? `Risque : ${item.riskLabel ?? '—'}${item.riskScore !== undefined ? ` (${(item.riskScore * 100).toFixed(1)} %)` : ''} · ${item.detCount ?? 0} lésion(s)`
            : item.status === 'error'
            ? item.error
            : item.progress || '—'}
        </div>
      </div>

      {/* Bouton supprimer (uniquement si pas actif) */}
      {!isActive && (
        <button
          onClick={onRemove}
          title="Retirer de la liste"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: SBAR_MUTED, fontSize: 14, padding: 2,
          }}
        >✕</button>
      )}
    </div>
  );
}

// ── Composant principal ───────────────────────────────────────────────────────

export interface BatchModalProps {
  onClose:       () => void;
  /** Mode d'analyse par défaut (depuis les réglages globaux) */
  analysisMode:  'both' | 'risk_only' | 'detect_only';
  /** Callback pour ouvrir le fichier analysé dans un onglet principal */
  onOpenInTab:   (serverPath: string, name: string) => void;
}

export function BatchModal({ onClose, analysisMode: defaultMode, onOpenInTab }: BatchModalProps) {
  const [items,        setItems]        = useState<BatchItem[]>([]);
  const [running,      setRunning]      = useState(false);
  const [done,         setDone]         = useState(false);
  const [batchMode,    setBatchMode]    = useState<'both' | 'risk_only' | 'detect_only'>(defaultMode);
  const abortRef = useRef<(() => void) | null>(null);
  const cancelledRef = useRef(false);

  // Mise à jour d'un item par id
  const update = useCallback((id: number, patch: Partial<BatchItem>) => {
    setItems(prev => prev.map(it => it.id === id ? { ...it, ...patch } : it));
  }, []);

  // ── Ajout de fichiers (upload navigateur) ──────────────────────────────────
  const onFileDrop = useCallback((files: FileList | null) => {
    if (!files) return;
    const newItems: BatchItem[] = Array.from(files)
      .filter(f => !f.name.match(/\.(png|jpg|jpeg|gif|mp4|mov|avi)$/i))
      .map(f => ({
        id: uid(), name: f.name, serverPath: '', file: f,
        status: 'waiting' as ItemStatus, progress: 'En attente',
      }));
    setItems(prev => [...prev, ...newItems]);
    setDone(false);
  }, []);

  // ── Ajout par chemin absolu (Electron / saisie manuelle) ──────────────────
  const pathRef = useRef<HTMLInputElement>(null);
  const onAddPath = useCallback(() => {
    const val = pathRef.current?.value.trim();
    if (!val) return;
    const name = val.split('/').pop() ?? val;
    setItems(prev => [...prev, {
      id: uid(), name, serverPath: val, file: undefined,
      status: 'waiting', progress: 'En attente',
    }]);
    if (pathRef.current) pathRef.current.value = '';
    setDone(false);
  }, []);

  // ── Glisser-déposer ───────────────────────────────────────────────────────
  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); };
  const onDrop     = (e: React.DragEvent) => { e.preventDefault(); onFileDrop(e.dataTransfer.files); };

  // ── Lancer le batch ───────────────────────────────────────────────────────
  const runBatch = useCallback(async () => {
    cancelledRef.current = false;
    setRunning(true);
    setDone(false);

    const queue = items.filter(it => it.status === 'waiting' || it.status === 'error');

    for (const item of queue) {
      if (cancelledRef.current) break;

      // ── 1. Chargement DICOM ──────────────────────────────────────────────
      update(item.id, { status: 'loading', progress: 'Chargement DICOM…' });

      let serverPath = item.serverPath;
      try {
        if (item.file) {
          // Upload navigateur
          const data = await loadDicomFile(item.file);
          serverPath = data.serverPath || item.name;
          update(item.id, { serverPath });
        } else {
          // Chemin absolu
          await loadDicom(serverPath);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        update(item.id, { status: 'error', error: `Chargement échoué : ${msg}` });
        continue;
      }

      if (cancelledRef.current) break;

      // ── 2. Analyse SSE ───────────────────────────────────────────────────
      update(item.id, { status: 'analyzing', progress: 'Démarrage de l\'analyse…' });

      const req: AnalyzeRequest = {
        dicomPath:         serverPath,
        anonMode:          'hash',
        runRisk:           batchMode !== 'detect_only',
        runDetection:      batchMode !== 'risk_only',
        backScanConversion: true,
      };

      await new Promise<void>((resolve) => {
        let riskScore: number | undefined;
        let riskLabel: string | undefined;
        let detCount: number | undefined;

        const abort = streamAnalysis(
          req,
          (payload) => {
            const msg = payload.message ?? '';
            if (payload.level === 'progress' || payload.level === 'info') {
              update(item.id, { progress: msg });
            }
            if (payload.data?.risk) {
              const r = payload.data.risk;
              riskScore = r.score ?? r.risk_score ?? riskScore;
              riskLabel = r.label ?? r.risk_label ?? riskLabel;
            }
            if (payload.data?.detections_per_frame) {
              const dets = payload.data.detections_per_frame as Detection[][];
              detCount = dets.reduce((acc, fd) => acc + fd.length, 0);
            }
          },
          () => {
            // done
            update(item.id, {
              status: 'done',
              progress: 'Terminé',
              serverPath,
              riskScore,
              riskLabel,
              detCount: detCount ?? 0,
            });
            resolve();
          },
          (err) => {
            update(item.id, { status: 'error', error: err.message });
            resolve();
          },
        );
        abortRef.current = abort;
      });

      abortRef.current = null;
    }

    setRunning(false);
    setDone(true);
  }, [items, batchMode, update]);

  // ── Annuler ───────────────────────────────────────────────────────────────
  const cancel = useCallback(() => {
    cancelledRef.current = true;
    abortRef.current?.();
    abortRef.current = null;
    setRunning(false);
  }, []);

  // ── Retrait d'un item en attente ─────────────────────────────────────────
  const removeItem = useCallback((id: number) => {
    setItems(prev => prev.filter(it => it.id !== id));
  }, []);

  // Stats finales
  const doneCount  = items.filter(it => it.status === 'done').length;
  const errCount   = items.filter(it => it.status === 'error').length;
  const waitCount  = items.filter(it => it.status === 'waiting').length;

  // ── Export CSV ────────────────────────────────────────────────────────────
  const exportCSV = useCallback(() => {
    const analysisLabel =
      batchMode === 'both'        ? 'RISK + DETECT' :
      batchMode === 'risk_only'   ? 'RISK only' :
                                    'DETECT only';

    const header = [
      'Fichier',
      'Statut',
      'Risque CHC',
      'Score risque (%)',
      'Nombre de lésions détectées',
      'Mode analyse',
      'Date export',
    ];

    const now = new Date();
    const dateStr = now.toLocaleDateString('fr-FR') + ' ' + now.toLocaleTimeString('fr-FR');

    const rows = items.map(it => [
      it.name,
      it.status === 'done'  ? 'Terminé' :
      it.status === 'error' ? 'Erreur'  :
      it.status === 'analyzing' ? 'En cours' : 'En attente',
      it.riskLabel  ?? '',
      it.riskScore  !== undefined ? (it.riskScore * 100).toFixed(2) : '',
      it.status === 'done' ? String(it.detCount ?? 0) : '',
      analysisLabel,
      dateStr,
    ]);

    // Échappe les champs contenant des virgules, guillemets ou retours à la ligne
    const escape = (v: string) =>
      /[,"\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;

    const csv =
      [header, ...rows]
        .map(row => row.map(escape).join(','))
        .join('\r\n');

    // BOM UTF-8 pour que Excel l'ouvre directement sans problème d'encodage
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `starhe_batch_${now.toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [items, batchMode]);

  // Fermeture sur Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !running) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [running, onClose]);

  // ── Rendu ─────────────────────────────────────────────────────────────────
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}
      onClick={e => { if (e.target === e.currentTarget && !running) onClose(); }}
    >
      <div style={{
        background: CARD_BG, border: `1px solid ${CARD_BORDER}`,
        boxShadow: CARD_SHADOW, borderRadius: 8,
        width: 640, maxWidth: '95vw', maxHeight: '85vh',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>

        {/* ── En-tête ── */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 18px', borderBottom: `1px solid ${CARD_BORDER}`,
          background: SIDEBAR_BG, flexShrink: 0,
        }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: SBAR_FG }}>
            📋  Analyse batch
          </span>
          {/* Sélecteur de mode d'analyse */}
          <div style={{ display: 'flex', gap: 4 }}>
            {(['both', 'risk_only', 'detect_only'] as const).map(m => {
              const label = m === 'both' ? 'RISK + DETECT' : m === 'risk_only' ? 'RISK' : 'DETECT';
              const active = batchMode === m;
              return (
                <button
                  key={m}
                  onClick={() => !running && setBatchMode(m)}
                  disabled={running}
                  title={m === 'both' ? 'STARHE RISK + DETECT' : m === 'risk_only' ? 'STARHE RISK uniquement' : 'STARHE DETECT uniquement'}
                  style={{
                    background: active ? BLUE : 'transparent',
                    border: `1px solid ${active ? BLUE : CARD_BORDER}`,
                    borderRadius: 4, padding: '3px 10px',
                    color: active ? '#fff' : SBAR_MUTED,
                    fontSize: 11, fontWeight: active ? 700 : 400,
                    cursor: running ? 'not-allowed' : 'pointer',
                    transition: 'background 0.1s, color 0.1s',
                  }}
                >{label}</button>
              );
            })}
          </div>
          <button
            onClick={running ? undefined : onClose}
            disabled={running}
            style={{
              background: 'none', border: 'none', cursor: running ? 'not-allowed' : 'pointer',
              color: SBAR_MUTED, fontSize: 18, lineHeight: 1,
            }}
          >✕</button>
        </div>

        {/* ── Zone d'ajout ── */}
        <div style={{
          padding: '12px 18px 10px', borderBottom: `1px solid ${CARD_BORDER}`,
          background: MAIN_BG, flexShrink: 0,
        }}>
          {/* Drag & drop */}
          <div
            onDragOver={onDragOver}
            onDrop={onDrop}
            style={{
              border: `2px dashed ${CARD_BORDER}`, borderRadius: 6,
              padding: '12px 16px', marginBottom: 10, textAlign: 'center',
              color: SBAR_MUTED, fontSize: 12, cursor: 'pointer',
              background: '#0a0e18',
            }}
            onClick={() => {
              const inp = document.createElement('input');
              inp.type = 'file'; inp.multiple = true; inp.accept = '.dcm,*';
              inp.onchange = () => onFileDrop(inp.files);
              inp.click();
            }}
          >
            📂  Glisser-déposer des fichiers DICOM ici, ou cliquer pour sélectionner
          </div>

          {/* Saisie chemin absolu */}
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              ref={pathRef}
              type="text"
              placeholder="/chemin/absolu/fichier.dcm"
              onKeyDown={e => { if (e.key === 'Enter') onAddPath(); }}
              style={{
                flex: 1, background: '#0a0e18', border: `1px solid ${CARD_BORDER}`,
                borderRadius: 4, padding: '5px 10px', color: SBAR_FG,
                fontSize: 12, outline: 'none',
              }}
            />
            <button
              onClick={onAddPath}
              style={{
                background: BLUE, border: 'none', borderRadius: 4, padding: '5px 12px',
                color: '#fff', fontSize: 12, cursor: 'pointer', fontWeight: 600,
              }}
            >Ajouter</button>
          </div>
        </div>

        {/* ── Liste des fichiers ── */}
        <div style={{ flex: 1, overflowY: 'auto', background: MAIN_BG }}>
          {items.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: SBAR_MUTED, fontSize: 13 }}>
              Aucun fichier ajouté
            </div>
          ) : (
            items.map(item => (
              <BatchRow
                key={item.id}
                item={item}
                onRemove={() => removeItem(item.id)}
              />
            ))
          )}
        </div>

        {/* ── Pied de page ── */}
        <div style={{
          padding: '10px 18px', borderTop: `1px solid ${CARD_BORDER}`,
          background: SIDEBAR_BG, flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
        }}>
          {/* Stats */}
          <div style={{ fontSize: 12, color: SBAR_MUTED }}>
            {items.length > 0 && (
              <>
                <span style={{ color: SUCCESS_FG }}>{doneCount} ✓</span>
                {errCount > 0 && <span style={{ color: DANGER_FG }}> · {errCount} ✗</span>}
                {waitCount > 0 && <span> · {waitCount} en attente</span>}
              </>
            )}
            {done && errCount === 0 && doneCount > 0 && (
              <span style={{ color: SUCCESS_FG, marginLeft: 8 }}>Batch terminé !</span>
            )}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8 }}>
            {doneCount > 0 && !running && (
              <button
                onClick={exportCSV}
                title="Télécharger les résultats au format CSV"
                style={{
                  background: '#14532d', border: '1px solid #166534',
                  borderRadius: 4, padding: '6px 14px',
                  color: '#86efac', fontSize: 12, cursor: 'pointer', fontWeight: 600,
                }}
              >⬇  Générer CSV</button>
            )}
            {running ? (
              <button
                onClick={cancel}
                style={{
                  background: '#7f1d1d', border: 'none', borderRadius: 4,
                  padding: '6px 16px', color: '#fca5a5', fontSize: 12,
                  cursor: 'pointer', fontWeight: 600,
                }}
              >⏹  Annuler</button>
            ) : (
              <>
                <button
                  onClick={() => setItems([])}
                  disabled={items.length === 0}
                  style={{
                    background: 'transparent', border: `1px solid ${CARD_BORDER}`,
                    borderRadius: 4, padding: '6px 14px', color: SBAR_MUTED,
                    fontSize: 12, cursor: items.length === 0 ? 'not-allowed' : 'pointer',
                  }}
                >Vider</button>
                <button
                  onClick={runBatch}
                  disabled={items.filter(it => it.status === 'waiting' || it.status === 'error').length === 0}
                  style={{
                    background: BLUE, border: 'none', borderRadius: 4,
                    padding: '6px 18px', color: '#fff', fontSize: 12,
                    cursor: 'pointer', fontWeight: 700,
                    opacity: items.filter(it => it.status === 'waiting' || it.status === 'error').length === 0 ? 0.4 : 1,
                  }}
                >▶  Lancer le batch ({items.filter(it => it.status === 'waiting' || it.status === 'error').length})</button>
              </>
            )}
          </div>
        </div>

        {/* ── Tableau récap (affiché quand au moins un item terminé) ── */}
        {doneCount > 0 && (
          <div style={{
            borderTop: `1px solid ${CARD_BORDER}`, background: '#080c14',
            padding: '10px 18px 14px', flexShrink: 0, maxHeight: 220, overflowY: 'auto',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: SBAR_MUTED, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                Récapitulatif
              </span>
              {!running && (
                <button
                  onClick={exportCSV}
                  title="Télécharger les résultats au format CSV"
                  style={{
                    background: '#14532d', border: '1px solid #166534',
                    borderRadius: 3, padding: '2px 10px',
                    color: '#86efac', fontSize: 11, cursor: 'pointer', fontWeight: 600,
                  }}
                >⬇ CSV</button>
              )}
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ color: SBAR_MUTED }}>
                  <th style={{ textAlign: 'left', padding: '3px 6px', fontWeight: 600 }}>Fichier</th>
                  <th style={{ textAlign: 'center', padding: '3px 6px', fontWeight: 600 }}>Risque CHC</th>
                  <th style={{ textAlign: 'center', padding: '3px 6px', fontWeight: 600 }}>Score</th>
                  <th style={{ textAlign: 'center', padding: '3px 6px', fontWeight: 600 }}>Lésions</th>
                  <th style={{ textAlign: 'center', padding: '3px 6px', fontWeight: 600 }}>Ouvrir</th>
                </tr>
              </thead>
              <tbody>
                {items.filter(it => it.status === 'done').map(it => (
                  <tr key={it.id} style={{ borderTop: `1px solid ${CARD_BORDER}` }}>
                    <td style={{ padding: '3px 6px', color: SBAR_FG, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {it.name}
                    </td>
                    <td style={{ padding: '3px 6px', textAlign: 'center', fontWeight: 700, color: riskColor(it.riskLabel) }}>
                      {it.riskLabel ?? '—'}
                    </td>
                    <td style={{ padding: '3px 6px', textAlign: 'center', color: riskColor(it.riskLabel) }}>
                      {it.riskScore !== undefined ? `${(it.riskScore * 100).toFixed(1)} %` : '—'}
                    </td>
                    <td style={{ padding: '3px 6px', textAlign: 'center', color: it.detCount ? WARN_FG : SBAR_MUTED }}>
                      {it.detCount ?? 0}
                    </td>
                    <td style={{ padding: '3px 6px', textAlign: 'center' }}>
                      <button
                        onClick={() => onOpenInTab(it.serverPath, it.name)}
                        title="Ouvrir dans un onglet"
                        style={{
                          background: 'none', border: `1px solid ${CARD_BORDER}`,
                          borderRadius: 3, padding: '2px 8px', color: BLUE,
                          cursor: 'pointer', fontSize: 11,
                        }}
                      >→ Tab</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
