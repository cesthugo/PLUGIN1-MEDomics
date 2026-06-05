// types.ts — Types partagés du plugin STARHE

// ── Log ───────────────────────────────────────────────────────────────────────
export type LogLevel = 'info' | 'success' | 'warning' | 'error';

export interface LogEntry {
  id: number;
  level: LogLevel;
  message: string;
}

// ── DICOM ─────────────────────────────────────────────────────────────────────
export interface DicomData {
  fileName: string;
  frameCount: number;
  rows: number;
  cols: number;
  modality: string;
  /** [row_mm_per_px, col_mm_per_px] | null */
  pixelSpacing: [number, number] | null;
  baseFps: number;
  /** [[TagName, OriginalValue], …] avant anonymisation */
  originalSensitive: [string, string][];
  /** [[Label, Value], …] métadonnées conservées */
  keptMetadata: [string, string][];
  patientName: string;
  studyDate: string;
  /** Frames encodées en JPEG base64 (toutes) */
  framesB64: string[];
  /**
   * Chemin du fichier sur le serveur Go.
   * - Mode Electron : chemin absolu d'origine (ex: /data/patient.dcm)
   * - Mode navigateur upload : chemin du fichier temporaire serveur (ex: /tmp/starhe_upload_XYZ.dcm)
   * Ce champ est utilisé pour lancer l'analyse STARHE.
   */
  serverPath: string;
}

// ── Détection ────────────────────────────────────────────────────────────────
export interface Detection {
  /** [x0, y0, x1, y1] en coordonnées image originale */
  bbox: [number, number, number, number];
  label: string;
  score: number;
}

// ── Résultats IA ──────────────────────────────────────────────────────────────
export interface AnalysisResult {
  riskText: string;
  riskFg: string;
  detText: string;
  detFg: string;
}

// ── Mesures ───────────────────────────────────────────────────────────────────
export interface Measure {
  /** Deux points en coordonnées image */
  pts: [[number, number], [number, number]];  /**
   * Décalage du label depuis le milieu du segment, en coordonnées image.
   * `undefined` = position perp. automatique calculée à l’affichaçage.
   */
  labelOffset?: [number, number];}

// ── Mode d'interaction canvas ─────────────────────────────────────────────────
export type ViewMode = 'normal' | 'pan' | 'measure' | 'series';

// ── Onglet ────────────────────────────────────────────────────────────────────
export interface TabState {
  id: number;              // identifiant unique (auto-incrémenté)
  label: string;           // libellé affiché dans la barre d'onglets
  patientName: string;
  dicomPath: string;
  /** true si cet onglet contient une vidéo MP4 (pas un DICOM) */
  isMp4?: boolean;
  data: DicomData | null;  // null si chargement en cours

  frameIdx: number;
  /** mode→par-frame détections */
  detectionsBy: Partial<Record<'original' | 'backscan', Detection[][]>>;
  resultsBy:    Partial<Record<'original' | 'backscan', AnalysisResult>>;
  /** mesures par frame (en coords image) */
  measuresByFrame: Record<number, Measure[]>;
  selectedMeasure: number | null; // index dans measuresByFrame[frameIdx]

  zoom:       number;
  panX:       number;
  panY:       number;
  contrast:   number;  // 0.1 – 3.0
  brightness: number;  // -100 – +100
  viewMode:   ViewMode;
  speedMult:  number;  // multiplicateur de lecture
  loop:       boolean;
}

// ── Patient ───────────────────────────────────────────────────────────────────
export interface Patient {
  name: string;
  tabIds: number[]; // IDs des onglets (pas des indices)
}

// ── SSE pipeline ──────────────────────────────────────────────────────────────
export interface SSEPayload {
  level: string;
  message: string;
  data?: {
    step?: number;
    total?: number;
    percent?: number;
    risk?: {
      score?: number; label?: string;          // camelCase (réservé)
      risk_score?: number; risk_label?: string; // snake_case retourné par Python
    };
    detections_per_frame?: Detection[][];
    n_frames_with_det?: number;
    [key: string]: unknown;
  };
}

// ── Context menu item ─────────────────────────────────────────────────────────
export interface ContextMenuItem {
  label: string;
  onClick: () => void;
  checked?: boolean;
  separator?: boolean;
}
