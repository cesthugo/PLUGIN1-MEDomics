// types.ts — Shared types of the STARHE plugin

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
  /** [[TagName, OriginalValue], …] before anonymization */
  originalSensitive: [string, string][];
  /** [[Label, Value], …] kept metadata */
  keptMetadata: [string, string][];
  patientName: string;
  studyDate: string;
  /** Frames encoded as base64 JPEG (all of them) */
  framesB64: string[];
  /**
   * File path on the Go server.
   * - Electron mode: original absolute path (e.g. /data/patient.dcm)
   * - Browser upload mode: server temporary file path (e.g. /tmp/starhe_upload_XYZ.dcm)
   * This field is used to launch the STARHE analysis.
   */
  serverPath: string;
}

// ── Detection ─────────────────────────────────────────────────────────────────
export interface Detection {
  /** [x0, y0, x1, y1] in original image coordinates */
  bbox: [number, number, number, number];
  label: string;
  score: number;
}

// ── AI results ────────────────────────────────────────────────────────────────
export interface AnalysisResult {
  riskText: string;
  riskFg: string;
  detText: string;
  detFg: string;
}

// ── Measures ──────────────────────────────────────────────────────────────────
export interface Measure {
  /** Two points in image coordinates */
  pts: [[number, number], [number, number]];  /**
   * Offset of the label from the segment midpoint, in image coordinates.
   * `undefined` = automatic perpendicular position computed at display time.
   */
  labelOffset?: [number, number];}

// ── Mode d'interaction canvas ─────────────────────────────────────────────────
export type ViewMode = 'normal' | 'pan' | 'measure' | 'series';

// ── Tab ───────────────────────────────────────────────────────────────────────
export interface TabState {
  id: number;              // unique identifier (auto-incremented)
  label: string;           // label shown in the tab bar
  patientName: string;
  dicomPath: string;
  /** true if this tab contains an MP4 video (not a DICOM) */
  isMp4?: boolean;
  data: DicomData | null;  // null while loading

  frameIdx: number;
  /** mode→per-frame detections */
  detectionsBy: Partial<Record<'original' | 'backscan', Detection[][]>>;
  resultsBy:    Partial<Record<'original' | 'backscan', AnalysisResult>>;
  /** measures per frame (in image coords) */
  measuresByFrame: Record<number, Measure[]>;
  selectedMeasure: number | null; // index into measuresByFrame[frameIdx]

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
  tabIds: number[]; // tab IDs (not indices)
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
      score?: number; label?: string;          // camelCase (reserved)
      risk_score?: number; risk_label?: string; // snake_case returned by Python
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
