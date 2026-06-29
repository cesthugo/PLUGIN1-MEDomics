// components/DetectionGallery.tsx — Panneau droit : galerie des frames détectées
//
// Affiche la liste scrollable des frames où STARHE-DETECT a trouvé une lésion,
// avec l'image miniature et les bounding boxes en superposition SVG.
// Cliquer sur une frame navigue directement vers elle.

import React from 'react';
import type { Detection } from '../../utilities/starhe/types';
import { SIDEBAR_BG, BLUE, SBAR_MUTED } from '../../utilities/starhe/colors';

// ── Miniature d'une frame avec bbox SVG overlay ───────────────────────────────

interface ThumbProps {
  b64:      string;
  dets:     Detection[];
  frameIdx: number;
  imgW:     number; // cols DICOM (largeur image)
  imgH:     number; // rows DICOM (hauteur image)
  onClick:  () => void;
}

function FrameThumb({ b64, dets, frameIdx, imgW, imgH, onClick }: ThumbProps) {
  return (
    <div
      onClick={onClick}
      title={`Frame ${frameIdx + 1} — ${dets.length} lesion(s)`}
      style={{
        margin: '5px 7px',
        cursor: 'pointer',
        borderRadius: 4,
        border: '1px solid #1e2d40',
        overflow: 'hidden',
        background: '#0a0a14',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = '#2563eb')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = '#1e2d40')}
    >
      {/* Image + bboxes en position relative */}
      <div style={{ position: 'relative', display: 'block', lineHeight: 0 }}>
        <img
          src={`data:image/jpeg;base64,${b64}`}
          alt={`Frame ${frameIdx + 1}`}
          style={{ width: '100%', display: 'block' }}
          loading="lazy"
        />
        {/* SVG overlay positionné en absolu par-dessus l'image */}
        <svg
          viewBox={`0 0 ${imgW} ${imgH}`}
          style={{
            position: 'absolute',
            top: 0, left: 0,
            width: '100%', height: '100%',
            pointerEvents: 'none',
          }}
        >
          {dets.map((det, i) => {
            const [x0, y0, x1, y1] = det.bbox;
            return (
              <g key={i}>
                <rect
                  x={x0} y={y0}
                  width={x1 - x0} height={y1 - y0}
                  fill="none"
                  stroke="#f59e0b"
                  strokeWidth={Math.max(2, imgW / 100)}
                />
                {/* Label score en haut à gauche de la bbox */}
                <rect
                  x={x0} y={y0 - Math.max(14, imgH * 0.018)}
                  width={Math.max(40, imgW * 0.06)}
                  height={Math.max(14, imgH * 0.018)}
                  fill="rgba(245,158,11,0.85)"
                />
                <text
                  x={x0 + 2}
                  y={y0 - 2}
                  fill="#000"
                  fontSize={Math.max(10, imgH * 0.015)}
                  fontWeight="bold"
                  fontFamily="monospace"
                >
                  {(det.score * 100).toFixed(0)}%
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Pied de carte */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '3px 7px',
        background: '#0d0d1a',
      }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: '#60a5fa' }}>
          Frame {frameIdx + 1}
        </span>
        <span style={{ fontSize: 10, color: '#f59e0b' }}>
          {dets.length} lesion{dets.length > 1 ? 's' : ''}
        </span>
      </div>
    </div>
  );
}

// ── Composant principal ───────────────────────────────────────────────────────

export interface DetectionGalleryProps {
  framesB64:   string[];
  detections:  Detection[][];   // tableau[frame] → liste de détections
  imgW:        number;          // cols DICOM
  imgH:        number;          // rows DICOM
  onGotoFrame: (idx: number) => void;
  sidebarBg?:  string;
  textColor?:  string;
}

export function DetectionGallery({
  framesB64,
  detections,
  imgW,
  imgH,
  onGotoFrame,
  sidebarBg,
  textColor,
}: DetectionGalleryProps) {
  // Filtre : seulement les frames avec au moins une détection
  const detFrames = detections
    .map((dets, i) => ({ i, dets }))
    .filter(x => x.dets.length > 0);

  return (
    <div style={{
      width: 190,
      minWidth: 190,
      maxWidth: 190,
      background: sidebarBg ?? SIDEBAR_BG,
      display: 'flex',
      flexDirection: 'column',
      borderLeft: '1px solid #0a0a14',
      flexShrink: 0,
    }}>
      {/* ── En-tête ──────────────────────────────────────────────────────── */}
      <div style={{
        padding: '10px 10px 8px',
        borderBottom: '1px solid #0d0d1a',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 3, height: 14, background: BLUE, borderRadius: 2, flexShrink: 0 }} />
          <span style={{
            fontSize: 11, fontWeight: 700,
            color: textColor ?? '#9ca3af',
            letterSpacing: '0.05em', textTransform: 'uppercase',
          }}>
            Detected frames
          </span>
        </div>
        <div style={{ fontSize: 10, color: SBAR_MUTED, marginTop: 4, paddingLeft: 9 }}>
          {detFrames.length === 0
            ? 'No lesion detected'
            : `${detFrames.length} frame${detFrames.length > 1 ? 's' : ''} with lesion${detFrames.length > 1 ? 's' : ''}`}
        </div>
      </div>

      {/* ── Liste scrollable ─────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
        {detFrames.length === 0 ? (
          <div style={{
            padding: '20px 12px',
            fontSize: 11,
            color: SBAR_MUTED,
            textAlign: 'center',
            lineHeight: 1.6,
          }}>
            Run STARHE DETECT<br />analysis to see<br />results.
          </div>
        ) : (
          detFrames.map(({ i, dets }) => (
            <FrameThumb
              key={i}
              b64={framesB64[i] ?? ''}
              dets={dets}
              frameIdx={i}
              imgW={imgW || 512}
              imgH={imgH || 512}
              onClick={() => onGotoFrame(i)}
            />
          ))
        )}
      </div>
    </div>
  );
}
