/**
 * DicomUploader.tsx
 *
 * Composant d'import DICOM unifié offrant deux modes dans une seule zone d'action :
 *
 *   1. CLIC  → déclenche un <input type="file" multiple> natif.
 *   2. DRAG & DROP → scan récursif du/des dossier(s) déposé(s) via l'API
 *      `DataTransferItem.webkitGetAsEntry()` (Chrome, Firefox 50+, Edge, Safari 11.1+).
 *
 * ── STRATÉGIE UPLOAD VERS UN BACKEND PYTHON (FastAPI / Flask) ─────────────────
 *
 * Pour un tableau File[], la solution standard est FormData :
 *
 *   const form = new FormData();
 *   files.forEach(f => form.append('dicom_files', f, f.name));
 *   await fetch('/api/upload', { method: 'POST', body: form });
 *
 * FastAPI :  async def upload(dicom_files: List[UploadFile] = File(...))
 * Flask    :  request.files.getlist('dicom_files')
 *
 * Pour des volumes importants (> 50 fichiers / > 500 MB), deux stratégies :
 *
 *   A. Parallel batching — grouper les fichiers par tranches de N et lancer
 *      N requêtes en parallèle avec Promise.all() :
 *
 *        const BATCH = 5;
 *        for (let i = 0; i < files.length; i += BATCH) {
 *          const slice = files.slice(i, i + BATCH);
 *          const form  = new FormData();
 *          slice.forEach(f => form.append('dicom_files', f));
 *          await fetch('/api/upload', { method: 'POST', body: form });
 *        }
 *
 *   B. Resumable uploads — protocole TUS (tus.io) pour reprendre après
 *      interruption réseau ; librairie cliente : `tus-js-client`.
 *
 * ────────────────────────────────────────────────────────────────────────────────
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';

// ── Palette (cohérente avec le projet MEDomics) ───────────────────────────────
const MAIN_BG     = '#0a0e18';
const CARD_BORDER = '#1f2937';
const BLUE        = '#2563eb';
const BLUE_HOVER  = '#1d4ed8';
const BLUE_DIM    = 'rgba(37,99,235,0.10)';
const SBAR_FG     = '#e2e8f0';
const SBAR_MUTED  = '#64748b';
const SUCCESS_FG  = '#4ade80';
const SUCCESS_BG  = 'rgba(5,46,22,0.60)';
const SUCCESS_BD  = '#166534';

// ── CSS keyframes injectés une seule fois dans <head> ────────────────────────
const SPIN_KEYFRAMES = `@keyframes __dicom-spin { to { transform: rotate(360deg); } }`;

function injectSpinKeyframes() {
  if (document.getElementById('__dicom-spin-style')) return;
  const s = document.createElement('style');
  s.id        = '__dicom-spin-style';
  s.textContent = SPIN_KEYFRAMES;
  document.head.appendChild(s);
}

// ── Types publics ─────────────────────────────────────────────────────────────
export interface DicomUploaderProps {
  /** Appelé à chaque changement de la liste de fichiers (sélection ou drop). */
  onFilesChange: (files: File[]) => void;
  /** Nombre max de fichiers affichés dans l'aperçu (défaut : 5). */
  maxPreview?: number;
  /** Classe CSS optionnelle pour le conteneur racine. */
  className?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Retourne `true` si le fichier est probablement un DICOM :
 * extension `.dcm` / `.dicom`, type MIME `application/dicom`,
 * ou absence d'extension (format courant pour les séries DICOM sans suffixe).
 */
const isDicom = (file: File): boolean => {
  const lower = file.name.toLowerCase();
  return (
    lower.endsWith('.dcm')           ||
    lower.endsWith('.dicom')         ||
    file.type === 'application/dicom'||
    !lower.includes('.')              // ex: "IM-0001-0023", "A0000"
  );
};

/**
 * Parcourt récursivement une `FileSystemEntry` (fichier ou répertoire)
 * et résout avec la liste plate de tous les fichiers DICOM trouvés.
 *
 * ⚠️  `FileSystemDirectoryReader.readEntries()` renvoie au plus 100 entrées
 * par appel — on reboucle jusqu'à obtenir un tableau vide.
 */
const traverseEntry = (entry: FileSystemEntry): Promise<File[]> =>
  new Promise((resolve) => {
    if (entry.isFile) {
      (entry as FileSystemFileEntry).file(
        (file) => resolve(isDicom(file) ? [file] : []),
        ()     => resolve([]),
      );
      return;
    }

    if (entry.isDirectory) {
      const reader    = (entry as FileSystemDirectoryEntry).createReader();
      const collected: File[] = [];

      const readBatch = () => {
        reader.readEntries(
          async (entries) => {
            if (entries.length === 0) {
              resolve(collected);
              return;
            }
            const batches = await Promise.all(entries.map(traverseEntry));
            batches.forEach((batch) => collected.push(...batch));
            readBatch(); // continuer jusqu'au dernier batch vide
          },
          () => resolve(collected),
        );
      };

      readBatch();
      return;
    }

    resolve([]);
  });

// ── Sous-composants ───────────────────────────────────────────────────────────

/** Indicateur de chargement tournant (CSS animation, sans dépendance externe). */
const Spinner: React.FC = () => {
  useEffect(() => { injectSpinKeyframes(); }, []);
  return (
    <div
      aria-label="Loading"
      style={{
        width: 30, height: 30,
        border: `3px solid ${CARD_BORDER}`,
        borderTopColor: BLUE,
        borderRadius: '50%',
        animation: '__dicom-spin 0.75s linear infinite',
        flexShrink: 0,
      }}
    />
  );
};

/** Liste condensée des N premiers fichiers avec taille en KB. */
const FilePreview: React.FC<{ files: File[]; max: number }> = ({ files, max }) => {
  const shown = files.slice(0, max);
  const rest  = files.length - max;
  return (
    <ul style={{
      listStyle: 'none', padding: 0, margin: '6px 0 0',
      width: '100%', maxWidth: 380,
    }}>
      {shown.map((f) => (
        <li
          key={`${f.name}-${f.size}`}
          style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '2px 0', overflow: 'hidden',
          }}
        >
          <span style={{
            fontSize: 11, color: SBAR_MUTED,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            flex: 1,
          }}>
            {f.name}
          </span>
          <span style={{
            fontSize: 10, color: '#475569',
            flexShrink: 0, marginLeft: 8,
          }}>
            {(f.size / 1024).toFixed(0)} KB
          </span>
        </li>
      ))}
      {rest > 0 && (
        <li style={{ fontSize: 11, color: '#475569', paddingTop: 3 }}>
          … and {rest} more
        </li>
      )}
    </ul>
  );
};

// ── Composant principal ───────────────────────────────────────────────────────

const DicomUploader: React.FC<DicomUploaderProps> = ({
  onFilesChange,
  maxPreview = 5,
  className,
}) => {
  const [files,      setFiles]      = useState<File[]>([]);
  const [loading,    setLoading]    = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  // ── Validation et commit de la liste finale ──────────────────────────────
  const commit = useCallback((raw: File[]) => {
    const sorted = [...raw].sort((a, b) => a.name.localeCompare(b.name));
    setFiles(sorted);
    onFilesChange(sorted);
  }, [onFilesChange]);

  // ── Clic → sélection via <input> ────────────────────────────────────────
  const handleClick = () => {
    if (!loading) inputRef.current?.click();
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []).filter(isDicom);
    commit(selected);
    e.target.value = ''; // reset pour permettre une re-sélection identique
  };

  // ── Drag & Drop ──────────────────────────────────────────────────────────
  const onDragOver  = (e: React.DragEvent) => { e.preventDefault(); setIsDragOver(true);  };
  const onDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragOver(false); };

  const onDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    setLoading(true);

    const items = Array.from(e.dataTransfer.items);

    // Récupérer les FileSystemEntry (fichiers ET dossiers)
    const entries = items
      .map((item) => item.webkitGetAsEntry?.() ?? null)
      .filter((entry): entry is FileSystemEntry => entry !== null);

    if (entries.length === 0) {
      // Fallback : navigateur sans API FileSystem → File objects directs
      const fallback = Array.from(e.dataTransfer.files).filter(isDicom);
      setLoading(false);
      commit(fallback);
      return;
    }

    // Traversée asynchrone de tous les nœuds racine en parallèle
    const batches = await Promise.all(entries.map(traverseEntry));
    const all     = batches.flat();

    setLoading(false);
    commit(all);
  }, [commit]);

  // ── Styles dynamiques ────────────────────────────────────────────────────
  const hasFiles   = files.length > 0;
  const borderColor = isDragOver ? BLUE : hasFiles ? SUCCESS_BD : CARD_BORDER;
  const bgColor     = isDragOver ? BLUE_DIM : hasFiles ? SUCCESS_BG : MAIN_BG;

  const zoneStyle: React.CSSProperties = {
    border:         `2px dashed ${borderColor}`,
    borderRadius:   10,
    background:     bgColor,
    padding:        '32px 28px',
    cursor:         loading ? 'default' : 'pointer',
    transition:     'border-color 0.15s ease, background 0.15s ease',
    display:        'flex',
    flexDirection:  'column',
    alignItems:     'center',
    gap:            10,
    userSelect:     'none',
    outline:        'none',
    minHeight:      160,
    justifyContent: 'center',
  };

  // ── Rendu ────────────────────────────────────────────────────────────────
  return (
    <div className={className} style={{ fontFamily: 'inherit', width: '100%' }}>
      {/* Input masqué — webkitdirectory NON activé pour permettre la sélection
          de fichiers individuels. La lecture de dossier passe par le Drop. */}
      <input
        ref={inputRef}
        type="file"
        multiple
        style={{ display: 'none' }}
        onChange={handleInputChange}
      />

      {/* ── Zone unifiée ── */}
      <div
        role="button"
        tabIndex={0}
        aria-label="DICOM import area — click or drag & drop"
        aria-busy={loading}
        style={zoneStyle}
        onClick={handleClick}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleClick(); }
        }}
      >

        {/* ── État : scan en cours ── */}
        {loading && (
          <>
            <Spinner />
            <span style={{ color: SBAR_FG, fontSize: 13, fontWeight: 600 }}>
              Scanning…
            </span>
            <span style={{ color: SBAR_MUTED, fontSize: 11 }}>
              Recursively reading subfolders
            </span>
          </>
        )}

        {/* ── État : fichiers chargés ── */}
        {!loading && hasFiles && (
          <>
            <span style={{ fontSize: 26, lineHeight: 1 }}>✅</span>
            <span style={{ color: SUCCESS_FG, fontSize: 14, fontWeight: 700 }}>
              {files.length} DICOM file{files.length > 1 ? 's' : ''} loaded
            </span>
            <FilePreview files={files} max={maxPreview} />
            <span style={{ color: SBAR_MUTED, fontSize: 10, marginTop: 4 }}>
              Click or drop again to replace
            </span>
          </>
        )}

        {/* ── État : par défaut / vide ── */}
        {!loading && !hasFiles && (
          <>
            <span
              style={{ fontSize: 36, lineHeight: 1, filter: isDragOver ? 'brightness(1.4)' : 'none' }}
              aria-hidden="true"
            >
              {isDragOver ? '📥' : '📂'}
            </span>

            <span style={{ color: SBAR_FG, fontSize: 14, fontWeight: 600, textAlign: 'center' }}>
              {isDragOver
                ? 'Release to import folder'
                : 'Drop a folder or select files'}
            </span>

            <span style={{ color: SBAR_MUTED, fontSize: 11, textAlign: 'center', lineHeight: 1.6 }}>
              Fichiers{' '}
              <code style={{
                background: 'rgba(147,197,253,0.10)', color: '#93c5fd',
                borderRadius: 3, padding: '1px 4px', fontSize: 10,
              }}>.dcm</code>
              {' '}· Entire folders with recursive subfolders
            </span>

            {/* Bouton principal (stopPropagation pour éviter le double déclenchement) */}
            <UploadButton
              label="Select files"
              onClick={(e) => { e.stopPropagation(); handleClick(); }}
            />

            <span style={{ color: '#334155', fontSize: 10 }}>
              or drag & drop a DICOM folder here
            </span>
          </>
        )}

      </div>
    </div>
  );
};

// ── Bouton stylisé avec hover géré via state (pas de CSS class) ───────────────
const UploadButton: React.FC<{
  label: string;
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void;
}> = ({ label, onClick }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        marginTop:    4,
        background:   hovered ? BLUE_HOVER : BLUE,
        border:       'none',
        borderRadius: 6,
        padding:      '7px 22px',
        color:        '#fff',
        fontSize:     12,
        fontWeight:   700,
        cursor:       'pointer',
        letterSpacing:'0.03em',
        transition:   'background 0.12s ease',
        boxShadow:    hovered ? `0 0 0 3px rgba(37,99,235,0.30)` : 'none',
      }}
    >
      {label}
    </button>
  );
};

export default DicomUploader;
