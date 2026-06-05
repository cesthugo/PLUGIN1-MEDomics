// components/OrthancBrowser.tsx — Navigateur hiérarchique Orthanc PACS
//
// Arborescence : Patients → Études → Séries → Instances
// Chaque instance US peut être chargée directement dans le visualiseur STARHE.
//
// Ce composant proxifie Orthanc via le serveur Go (/starhe/orthanc/*) pour
// éviter les contraintes CORS et assurer l'authentification côté serveur.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { getApiBase } from '../api';
import type { DicomData } from '../types';
import {
  SIDEBAR_BG, MAIN_BG, BLUE, SBAR_FG, SBAR_MUTED,
  CARD_BG, CARD_BORDER, CARD_SHADOW,
  SUCCESS_FG, DANGER_FG, WARN_FG,
} from '../colors';

// ── Types Orthanc REST API ────────────────────────────────────────────────────

interface OrthancSystem {
  Version?: string;
  Name?: string;
  DicomAet?: string;
}

interface OrthancPatient {
  ID: string;
  MainDicomTags: {
    PatientID?: string;
    PatientName?: string;
    PatientBirthDate?: string;
    PatientSex?: string;
  };
  Studies: string[];
}

interface OrthancStudy {
  ID: string;
  MainDicomTags: {
    StudyDate?: string;
    StudyDescription?: string;
    StudyInstanceUID?: string;
    InstitutionName?: string;
  };
  PatientMainDicomTags?: {
    PatientName?: string;
    PatientID?: string;
  };
  Series: string[];
}

interface OrthancSeriesInfo {
  ID: string;
  MainDicomTags: {
    Modality?: string;
    SeriesDescription?: string;
    SeriesDate?: string;
    SeriesNumber?: string;
  };
  ParentStudy: string;
  Instances: string[];
}

interface OrthancInstance {
  ID: string;
  MainDicomTags: {
    InstanceNumber?: string;
    NumberOfFrames?: string;
    SOPClassUID?: string;
    ContentDate?: string;
    ContentTime?: string;
  };
  Series: string;
}

interface OrthancStatusResponse {
  available: boolean;
  url: string;
  error?: string;
  system?: OrthancSystem;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(d?: string): string {
  if (!d || d.length !== 8) return d ?? '';
  return `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}`;
}

function fmtPatientName(raw?: string): string {
  if (!raw) return 'Anonyme';
  return raw.replace(/\^/g, ' ').trim();
}

async function orthancGet<T>(path: string): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`);
  if (!res.ok) {
    const txt = await res.text().catch(() => `HTTP ${res.status}`);
    throw new Error(txt);
  }
  return res.json() as Promise<T>;
}

// ── Sous-composants UI ────────────────────────────────────────────────────────

function StatusBadge({ available, url, system }: { available: boolean; url: string; system?: OrthancSystem }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 14px', fontSize: 11 }}>
      <span style={{
        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
        background: available ? SUCCESS_FG : DANGER_FG,
        boxShadow: available ? `0 0 6px ${SUCCESS_FG}` : undefined,
      }} />
      <span style={{ color: available ? SUCCESS_FG : DANGER_FG, fontWeight: 600 }}>
        {available ? 'Connecté' : 'Déconnecté'}
      </span>
      <span style={{ color: SBAR_MUTED }}>{url}</span>
      {available && system?.Version && (
        <span style={{ color: SBAR_MUTED }}>v{system.Version}</span>
      )}
    </div>
  );
}

function TreeRow({
  depth, expanded, onToggle, label, sublabel, badge, onLoad, loading,
}: {
  depth: number;
  expanded?: boolean;
  onToggle?: () => void;
  label: string;
  sublabel?: string;
  badge?: string;
  onLoad?: () => void;
  loading?: boolean;
}) {
  const [hover, setHover] = useState(false);
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center',
        paddingLeft: 10 + depth * 18,
        paddingRight: 10,
        paddingTop: 5, paddingBottom: 5,
        borderBottom: '1px solid #1a1d2a',
        background: hover ? '#111520' : 'transparent',
        cursor: onToggle ? 'pointer' : 'default',
        gap: 6,
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={onToggle}
    >
      {/* Chevron */}
      {onToggle ? (
        <span style={{ fontSize: 10, color: SBAR_MUTED, width: 12, flexShrink: 0, userSelect: 'none' }}>
          {expanded ? '▼' : '▶'}
        </span>
      ) : (
        <span style={{ width: 12, flexShrink: 0 }} />
      )}

      {/* Icône */}
      <span style={{ fontSize: 13, flexShrink: 0 }}>
        {depth === 0 ? '👤' : depth === 1 ? '📅' : depth === 2 ? '🗂' : '🖼'}
      </span>

      {/* Texte */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, color: SBAR_FG,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {label}
        </div>
        {sublabel && (
          <div style={{ fontSize: 10, color: SBAR_MUTED, marginTop: 1 }}>{sublabel}</div>
        )}
      </div>

      {/* Badge count */}
      {badge && (
        <span style={{
          fontSize: 10, color: '#93c5fd',
          background: '#0d1f3a', borderRadius: 8,
          padding: '1px 7px', flexShrink: 0,
        }}>
          {badge}
        </span>
      )}

      {/* Bouton Charger */}
      {onLoad && (
        <button
          disabled={loading}
          onClick={e => { e.stopPropagation(); onLoad(); }}
          style={{
            flexShrink: 0,
            background: loading ? '#1a2240' : BLUE,
            border: 'none', borderRadius: 4,
            color: '#fff', fontSize: 10, fontWeight: 700,
            padding: '3px 10px', cursor: loading ? 'wait' : 'pointer',
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? '…' : 'Charger'}
        </button>
      )}
    </div>
  );
}

// ── Composant instance ────────────────────────────────────────────────────────

function InstanceRow({
  instance, onLoad, loadingId,
}: {
  instance: OrthancInstance;
  onLoad: (id: string) => void;
  loadingId: string | null;
}) {
  const nf = instance.MainDicomTags.NumberOfFrames;
  const inst = instance.MainDicomTags.InstanceNumber;
  const label = `Instance ${inst ?? '?'}${nf ? ` — ${nf} frames` : ''}`;
  const sublabel = instance.MainDicomTags.ContentDate
    ? formatDate(instance.MainDicomTags.ContentDate)
    : undefined;
  return (
    <TreeRow
      depth={3}
      label={label}
      sublabel={sublabel}
      onLoad={() => onLoad(instance.ID)}
      loading={loadingId === instance.ID}
    />
  );
}

// ── Composant série ───────────────────────────────────────────────────────────

function SeriesRow({
  seriesId, onLoad, loadingId,
}: {
  seriesId: string;
  onLoad: (instanceId: string) => void;
  loadingId: string | null;
}) {
  const [expanded,  setExpanded]  = useState(false);
  const [instances, setInstances] = useState<OrthancInstance[] | null>(null);
  const [seriesInfo, setSeriesInfo] = useState<OrthancSeriesInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');

  const toggle = useCallback(async () => {
    if (expanded) { setExpanded(false); return; }
    setExpanded(true);
    if (instances !== null) return;
    setLoading(true);
    setError('');
    try {
      const data = await orthancGet<OrthancInstance[]>(
        `/starhe/orthanc/series/${seriesId}`);
      setInstances(data);
      // Aussi récupérer les infos de la série depuis la première instance
      if (data.length > 0) {
        // On a déjà seriesId, on peut afficher les informations depuis instances[0].MainDicomTags
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [expanded, instances, seriesId]);

  // On récupère les infos de la série séparément pour le label
  useEffect(() => {
    if (!seriesInfo) {
      // Utiliser les données des instances quand disponibles
    }
  }, [seriesInfo]);

  const modality = instances?.[0]?.MainDicomTags
    ? 'US' // on connaît la modality depuis le seriesId
    : '?';

  return (
    <>
      <TreeRow
        depth={2}
        expanded={expanded}
        onToggle={toggle}
        label={`Série ${seriesId.slice(0, 8)}…`}
        sublabel={instances ? `${instances.length} instance(s)` : undefined}
        badge={instances ? String(instances.length) : undefined}
      />
      {expanded && loading && (
        <div style={{ paddingLeft: 64, padding: '6px 14px 6px 64px', fontSize: 11, color: SBAR_MUTED }}>
          Chargement…
        </div>
      )}
      {expanded && error && (
        <div style={{ paddingLeft: 64, padding: '6px 14px 6px 64px', fontSize: 11, color: DANGER_FG }}>
          {error}
        </div>
      )}
      {expanded && instances && instances.map(inst => (
        <InstanceRow
          key={inst.ID}
          instance={inst}
          onLoad={onLoad}
          loadingId={loadingId}
        />
      ))}
    </>
  );
}

// ── Composant étude ───────────────────────────────────────────────────────────

function StudyRow({
  studyId, onLoad, loadingId,
}: {
  studyId: string;
  onLoad: (instanceId: string) => void;
  loadingId: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const [study,    setStudy]    = useState<OrthancStudy | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');

  const toggle = useCallback(async () => {
    if (expanded) { setExpanded(false); return; }
    setExpanded(true);
    if (study !== null) return;
    setLoading(true);
    setError('');
    try {
      const data = await orthancGet<OrthancStudy>(`/starhe/orthanc/studies/${studyId}`);
      setStudy(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [expanded, study, studyId]);

  const label = study
    ? (study.MainDicomTags.StudyDescription || `Étude ${formatDate(study.MainDicomTags.StudyDate)}`)
    : `Étude ${studyId.slice(0, 8)}…`;
  const sublabel = study
    ? formatDate(study.MainDicomTags.StudyDate)
    : undefined;

  return (
    <>
      <TreeRow
        depth={1}
        expanded={expanded}
        onToggle={toggle}
        label={label}
        sublabel={sublabel}
        badge={study ? String(study.Series.length) : undefined}
      />
      {expanded && loading && (
        <div style={{ padding: '6px 14px 6px 46px', fontSize: 11, color: SBAR_MUTED }}>
          Chargement…
        </div>
      )}
      {expanded && error && (
        <div style={{ padding: '6px 14px 6px 46px', fontSize: 11, color: DANGER_FG }}>
          {error}
        </div>
      )}
      {expanded && study && study.Series.map(sId => (
        <SeriesRow key={sId} seriesId={sId} onLoad={onLoad} loadingId={loadingId} />
      ))}
    </>
  );
}

// ── Composant patient ─────────────────────────────────────────────────────────

function PatientRow({
  patient, onLoad, loadingId,
}: {
  patient: OrthancPatient;
  onLoad: (instanceId: string) => void;
  loadingId: string | null;
}) {
  const [expanded, setExpanded] = useState(false);

  const name = fmtPatientName(patient.MainDicomTags.PatientName);
  const pid  = patient.MainDicomTags.PatientID ?? '';

  return (
    <>
      <TreeRow
        depth={0}
        expanded={expanded}
        onToggle={() => setExpanded(v => !v)}
        label={name}
        sublabel={pid}
        badge={String(patient.Studies.length)}
      />
      {expanded && patient.Studies.map(sId => (
        <StudyRow key={sId} studyId={sId} onLoad={onLoad} loadingId={loadingId} />
      ))}
    </>
  );
}

// ── Props du composant principal ──────────────────────────────────────────────

export interface OrthancLoadedResult {
  data:       DicomData;
  serverPath: string;
}

interface OrthancBrowserProps {
  onClose:  () => void;
  onLoaded: (result: OrthancLoadedResult) => void;
}

// ── Composant principal ───────────────────────────────────────────────────────

export function OrthancBrowser({ onClose, onLoaded }: OrthancBrowserProps) {
  const [status,     setStatus]     = useState<OrthancStatusResponse | null>(null);
  const [patients,   setPatients]   = useState<OrthancPatient[] | null>(null);
  const [loadingId,  setLoadingId]  = useState<string | null>(null);
  const [loadError,  setLoadError]  = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  // ── Vérification du statut Orthanc ────────────────────────────────────────
  const checkStatus = useCallback(async () => {
    setRefreshing(true);
    try {
      const s = await orthancGet<OrthancStatusResponse>('/starhe/orthanc/status');
      setStatus(s);
      if (s.available) {
        const pts = await orthancGet<OrthancPatient[]>('/starhe/orthanc/patients');
        setPatients(pts);
      }
    } catch (e: unknown) {
      setStatus({ available: false, url: '', error: e instanceof Error ? e.message : String(e) });
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { checkStatus(); }, [checkStatus]);

  // ── Fermeture par Escape ──────────────────────────────────────────────────
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  // ── Chargement d'une instance ─────────────────────────────────────────────
  const handleLoad = useCallback(async (instanceId: string) => {
    setLoadingId(instanceId);
    setLoadError('');
    try {
      const res = await fetch(`${getApiBase()}/starhe/orthanc/load`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ instance_id: instanceId, quality: 70, max_dim: 640 }),
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => `HTTP ${res.status}`);
        throw new Error(txt);
      }
      const json = await res.json();
      if (json.error) throw new Error(json.error);

      // Mappage de la réponse loader_cli.py → DicomData
      const serverPath = json.server_path ?? '';
      const data: DicomData = {
        fileName:          json.file_name          ?? instanceId,
        frameCount:        json.frame_count        ?? 0,
        rows:              json.rows               ?? 0,
        cols:              json.cols               ?? 0,
        modality:          json.modality           ?? 'US',
        pixelSpacing:      json.pixel_spacing      ?? null,
        baseFps:           json.base_fps           ?? 22,
        originalSensitive: json.original_sensitive ?? [],
        keptMetadata:      json.kept_metadata      ?? [],
        patientName:       json.patient_name       ?? 'Inconnu',
        studyDate:         json.study_date         ?? '',
        framesB64:         json.frames_b64         ?? [],
        serverPath,
      };
      onLoaded({ data, serverPath });
      onClose();
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingId(null);
    }
  }, [onLoaded, onClose]);

  // ── Rendu ─────────────────────────────────────────────────────────────────
  return (
    <div
      ref={overlayRef}
      style={{
        position: 'fixed', inset: 0, zIndex: 1100,
        background: 'rgba(0,0,0,0.72)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={e => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div style={{
        width: 680, maxWidth: '95vw',
        maxHeight: '85vh',
        background: SIDEBAR_BG,
        border: `1px solid #252a3f`,
        borderRadius: 8,
        boxShadow: `0 16px 48px rgba(0,0,0,0.6), 0 0 0 1px rgba(99,102,241,0.15)`,
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}>

        {/* ── En-tête ────────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 16px',
          borderBottom: '1px solid #1f2437',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 18 }}>🏥</span>
          <span style={{ fontSize: 15, fontWeight: 700, color: SBAR_FG, flex: 1 }}>
            Navigateur Orthanc PACS
          </span>
          <button
            onClick={checkStatus}
            disabled={refreshing}
            style={{
              background: 'none', border: `1px solid #2a3456`,
              borderRadius: 4, color: SBAR_MUTED,
              fontSize: 11, padding: '3px 10px', cursor: 'pointer',
              opacity: refreshing ? 0.5 : 1,
            }}
            title="Rafraîchir la liste des patients"
          >
            {refreshing ? '…' : '↺ Rafraîchir'}
          </button>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none',
              color: SBAR_MUTED, fontSize: 18,
              cursor: 'pointer', lineHeight: 1,
              padding: '0 4px',
            }}
            title="Fermer (Echap)"
          >
            ×
          </button>
        </div>

        {/* ── Statut Orthanc ─────────────────────────────────────────────── */}
        {status && (
          <StatusBadge
            available={status.available}
            url={status.url}
            system={status.system}
          />
        )}
        {status && !status.available && (
          <div style={{ padding: '4px 14px 8px', fontSize: 11, color: WARN_FG }}>
            Vérifiez qu'Orthanc est démarré sur {status.url}.
            Variables d'env : <code style={{ color: '#93c5fd' }}>ORTHANC_URL</code>,{' '}
            <code style={{ color: '#93c5fd' }}>ORTHANC_USER</code>,{' '}
            <code style={{ color: '#93c5fd' }}>ORTHANC_PASSWORD</code>.
          </div>
        )}

        {/* ── Message d'erreur de chargement ─────────────────────────────── */}
        {loadError && (
          <div style={{
            margin: '0 14px 6px',
            padding: '8px 12px',
            background: '#2d0a0a',
            border: `1px solid ${DANGER_FG}`,
            borderRadius: 4,
            fontSize: 11, color: DANGER_FG,
            flexShrink: 0,
          }}>
            ❌ {loadError}
          </div>
        )}

        {/* ── Arbre des patients ─────────────────────────────────────────── */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {!status && (
            <div style={{ padding: 20, textAlign: 'center', color: SBAR_MUTED, fontSize: 12 }}>
              Connexion à Orthanc…
            </div>
          )}
          {status?.available && !patients && (
            <div style={{ padding: 20, textAlign: 'center', color: SBAR_MUTED, fontSize: 12 }}>
              Chargement des patients…
            </div>
          )}
          {status?.available && patients && patients.length === 0 && (
            <div style={{ padding: 20, textAlign: 'center', color: SBAR_MUTED, fontSize: 12 }}>
              Aucun patient dans Orthanc.
            </div>
          )}
          {patients && patients.map(pt => (
            <PatientRow
              key={pt.ID}
              patient={pt}
              onLoad={handleLoad}
              loadingId={loadingId}
            />
          ))}
        </div>

        {/* ── Pied de page ───────────────────────────────────────────────── */}
        <div style={{
          padding: '8px 14px',
          borderTop: '1px solid #1f2437',
          fontSize: 10, color: SBAR_MUTED,
          flexShrink: 0, display: 'flex', justifyContent: 'space-between',
        }}>
          <span>
            {patients != null
              ? `${patients.length} patient(s) — ${patients.reduce((a, p) => a + p.Studies.length, 0)} étude(s)`
              : 'Non connecté'}
          </span>
          <span>Orthanc REST API v1 — proxifié par le serveur Go</span>
        </div>
      </div>
    </div>
  );
}
