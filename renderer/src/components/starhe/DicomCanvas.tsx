// components/DicomCanvas.tsx — Visionneuse DICOM avec canvas HTML5
//
// Fonctionnalités portées depuis prototype_tkinter.py :
//  - Affichage des frames JPEG avec pan / zoom centré sur curseur
//  - Superposition des bboxes de détection (dessin canvas)
//  - Outil de mesure en mm (dessin canvas, overlay SVG pour les terminaisons)
//  - Mode série (drag vertical = scroll frames)
//  - Clic droit maintenu = contraste (X) / luminosité (Y)
//  - Molette = zoom centré sur le curseur
//  - Barre de mode ("ORIGINAL" / "ANALYSE STARHE")
//  - Prévisualisation mesure en cours de dessin

import React, {
  useCallback, useEffect, useLayoutEffect, useRef, useState,
} from 'react';

import {
  computeTransform, imgToScreen, screenToImg,
  getMeasureLabelScreenPos,
  useCanvasInteractions,
} from '../../utilities/starhe/hooks/useCanvasInteractions';
import type { Transform } from '../../utilities/starhe/hooks/useCanvasInteractions';
import type { TabState, ViewMode, Measure, Detection } from '../../utilities/starhe/types';
import { BLUE, CANVAS_BG, SBAR_MUTED } from '../../utilities/starhe/colors';

// ── Dessine les bboxes de détection ──────────────────────────────────────────

function drawDetections(
  ctx:        CanvasRenderingContext2D,
  detections: Detection[],
  scale:      number,
  offX:       number,
  offY:       number,
): void {
  for (const det of detections) {
    const [ix0, iy0, ix1, iy1] = det.bbox;
    const sx0 = ix0 * scale + offX, sy0 = iy0 * scale + offY;
    const sx1 = ix1 * scale + offX, sy1 = iy1 * scale + offY;
    const isTumor = det.label.includes('tumor');
    ctx.strokeStyle = isTumor ? 'rgb(255,80,80)' : 'rgb(80,200,80)';
    ctx.lineWidth = 2;
    ctx.strokeRect(sx0, sy0, sx1 - sx0, sy1 - sy0);
    ctx.font = '13px "Segoe UI", sans-serif';
    ctx.fillStyle = isTumor ? 'rgb(255,80,80)' : 'rgb(80,200,80)';
    ctx.fillText(`${det.label} ${det.score.toFixed(2)}`, sx0, Math.max(sy0 - 4, 12));
  }
}

// ── Dessine un segment de mesure ──────────────────────────────────────────────

function drawMeasureSegment(
  ctx:          CanvasRenderingContext2D,
  p1:           [number, number],
  p2:           [number, number],
  t:            Transform,
  canvasW:      number,
  canvasH:      number,
  selected:     boolean,
  pixelSpacing: [number, number] | null,
  labelOffset?: [number, number],
): void {
  const sx1 = p1[0] * t.scale + t.offX, sy1 = p1[1] * t.scale + t.offY;
  const sx2 = p2[0] * t.scale + t.offX, sy2 = p2[1] * t.scale + t.offY;

  const color = selected ? '#ff9900' : '#ffff00';
  const r     = 3;

  // Segment principal
  ctx.setLineDash([5, 3]);
  ctx.strokeStyle = color;
  ctx.lineWidth   = 2;
  ctx.beginPath();
  ctx.moveTo(sx1, sy1);
  ctx.lineTo(sx2, sy2);
  ctx.stroke();
  ctx.setLineDash([]);

  // Points terminaux
  ctx.fillStyle = color;
  ctx.beginPath(); ctx.arc(sx1, sy1, r, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.arc(sx2, sy2, r, 0, Math.PI * 2); ctx.fill();

  // Label distance
  const dxImg = Math.abs(p2[0] - p1[0]), dyImg = Math.abs(p2[1] - p1[1]);
  let distLabel: string;
  if (pixelSpacing) {
    const mm = Math.hypot(dxImg * pixelSpacing[1], dyImg * pixelSpacing[0]);
    distLabel = `${mm.toFixed(1)} mm`;
  } else {
    distLabel = `${Math.hypot(dxImg, dyImg).toFixed(1)} px (pas calibration)`;
  }

  // Position du label (perpendiculaire par defaut, ou personnalisee si labelOffset)
  const mx = (sx1 + sx2) / 2, my = (sy1 + sy2) / 2;
  const [lx, ly] = getMeasureLabelScreenPos(p1, p2, labelOffset, t, canvasW, canvasH);

  // Ligne de liaison en pointilles (milieu segment -> label)
  ctx.setLineDash([3, 3]);
  ctx.strokeStyle = color + '99';
  ctx.lineWidth   = 1;
  ctx.beginPath();
  ctx.moveTo(mx, my);
  ctx.lineTo(lx, ly);
  ctx.stroke();
  ctx.setLineDash([]);

  // Label
  ctx.font      = 'bold 13px "Segoe UI", sans-serif';
  ctx.fillStyle = '#1a1a2e';
  ctx.fillText(distLabel, lx + 1, ly + 1);
  ctx.fillStyle = color;
  ctx.fillText(distLabel, lx, ly);
}

// ── Composant ─────────────────────────────────────────────────────────────────

export interface DicomCanvasProps {
  tab:              TabState | null;
  onZoomPan:        (zoom: number, panX: number, panY: number) => void;
  /** Appelé à chaque redimensionnement du canvas pour forcer le recentrage de TOUS les
   *  panneaux (multi-panneaux). Si absent, on replie sur onZoomPan(zoom,0,0) (vue simple). */
  onPanReset?:      () => void;
  onContrastBright: (contrast: number, brightness: number) => void;
  onFrameChange:    (idx: number) => void;
  onMeasureAdd:     (frameIdx: number, measure: Measure) => void;
  onMeasureMove:    (frameIdx: number, segIdx: number, newPts: [[number, number], [number, number]]) => void;
  onMeasureSelect:  (frameIdx: number, segIdx: number | null) => void;
  onMeasureLabelMove: (frameIdx: number, segIdx: number, labelOffset: [number, number]) => void;
  onContextMenu:    (x: number, y: number) => void;
}

export function DicomCanvas({
  tab,
  onZoomPan,
  onPanReset,
  onContrastBright,
  onFrameChange,
  onMeasureAdd,
  onMeasureMove,
  onMeasureSelect,
  onMeasureLabelMove,
  onContextMenu,
}: DicomCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef   = useRef<HTMLDivElement>(null);
  const imgCacheRef  = useRef<Map<string, HTMLImageElement>>(new Map());
  // Compteur de génération : chaque invocation de l'effet draw incrémente ce compteur.
  // Les callbacks img.onload vérifient qu'ils correspondent à la génération courante avant
  // de dessiner, évitant qu'un chargement différé écrase le canvas d'un autre onglet.
  const drawGenRef = useRef(0);

  // Preview segment en cours de dessin
  const [measurePreview, setMeasurePreview] = useState<
    [[number, number], [number, number]] | null
  >(null);

  // Taille courante du canvas (px)
  // canvasSizeRef : toujours à jour (mis à jour synchroniquement dans le ResizeObserver)
  // canvasSize    : état React (déclenche le re-render et la mise à jour des attributs canvas)
  const canvasSizeRef = useRef({ w: 640, h: 480 });
  const [canvasSize, setCanvasSize] = useState({ w: 640, h: 480 });

  // Observer de taille
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        const newSize = { w: e.contentRect.width, h: e.contentRect.height };
        canvasSizeRef.current = newSize;   // synchrone : utilisé par getState() tout de suite
        setCanvasSize(newSize);            // asynchrone : déclenche le re-render React
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Refs stables pour l'effet de recentrage — mis à jour à chaque render,
  // utilisés dans un effect qui n'a que canvasSize dans ses dépendances.
  const onZoomPanRef = useRef(onZoomPan);
  onZoomPanRef.current = onZoomPan;
  const onPanResetRef = useRef(onPanReset);
  onPanResetRef.current = onPanReset;
  const tabZoomRef = useRef(tab?.zoom ?? 1);
  tabZoomRef.current = tab?.zoom ?? 1;
  const hasDataRef = useRef(!!tab?.data);
  hasDataRef.current = !!tab?.data;

  // Quand le canvas est redimensionné en mode vue simple (ex. resize fenêtre),
  // réinitialise panX=0 / panY=0 pour recentrer l'image.
  // En mode multi-panneaux (onPanReset fourni) on ne fait rien : le pan doit
  // être préservé pendant et après le déplacement du séparateur.
  const isFirstSizeRef = useRef(true);
  useEffect(() => {
    if (!hasDataRef.current) return;
    if (onPanResetRef.current) return; // multi-panel : conserver le pan
    // Single panel : skip the very first size measurement to preserve user pan/zoom.
    if (isFirstSizeRef.current) { isFirstSizeRef.current = false; return; }
    onZoomPanRef.current(tabZoomRef.current, 0, 0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvasSize.w, canvasSize.h]);

  // État pour le hook d'interactions
  // canvasSizeRef est utilisé (pas canvasSize) pour que les handlers de zoom/pan
  // voient toujours les dimensions courantes, même pendant le redimensionnement
  // du séparateur (avant que React ait rerenderé avec les nouvelles props).
  const getState = useCallback(() => ({
    viewMode:        tab?.viewMode          ?? 'normal',
    zoom:            tab?.zoom              ?? 1,
    panX:            tab?.panX              ?? 0,
    panY:            tab?.panY              ?? 0,
    contrast:        tab?.contrast          ?? 1,
    brightness:      tab?.brightness        ?? 0,
    frameIdx:        tab?.frameIdx         ?? 0,
    frameCount:      tab?.data?.frameCount ?? 0,
    imgW:            tab?.data?.cols       ?? 0,
    imgH:            tab?.data?.rows       ?? 0,
    canvasW:         canvasSizeRef.current.w,
    canvasH:         canvasSizeRef.current.h,
    measuresByFrame: tab?.measuresByFrame  ?? {},
    selectedMeasure: tab?.selectedMeasure  ?? null,
    pixelSpacing:    tab?.data?.pixelSpacing ?? null,
  }), [tab]);  // pas besoin de dépendre de canvasSize : la ref est toujours à jour

  const interactions = useCanvasInteractions(getState, {
    onZoomPan,
    onContrastBright,
    onFrameChange,
    onMeasureAdd,
    onMeasureMove,
    onMeasureSelect,
    onMeasureLabelMove,
    onContextMenu,
  });

  // Branche le setter de preview
  useEffect(() => {
    interactions.setMeasurePreview(setMeasurePreview);
  }, [interactions]);

  // Écoute Delete / Backspace sur le canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.addEventListener('keydown', interactions.onKeyDown);
    return () => canvas.removeEventListener('keydown', interactions.onKeyDown);
  }, [interactions.onKeyDown]);

  // ── Rendu canvas ───────────────────────────────────────────────────────────

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvasSize.w, canvasSize.h);
    ctx.fillStyle = CANVAS_BG;
    ctx.fillRect(0, 0, canvasSize.w, canvasSize.h);

    if (!tab?.data) {
      // Texte d'accueil
      ctx.fillStyle = '#2a2a3e';
      ctx.font = '14px "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(
        'Aucun DICOM chargé — utilisez « Charger un fichier DICOM » dans le panneau latéral',
        canvasSize.w / 2, canvasSize.h / 2,
      );
      ctx.textAlign = 'left';
      return;
    }

    const { frameIdx, data, zoom, panX, panY, contrast, brightness,
            measuresByFrame, selectedMeasure, detectionsBy } = tab;
    const frames = data.framesB64;
    if (!frames?.length) return;
    const b64 = frames[Math.min(frameIdx, frames.length - 1)];
    // Clé namespaced par tab.id : empêche la collision entre fichiers ayant le même
    // header JPEG identique (tous commencent par /9j/4AAQSkZJRgABAQAA en base64).
    const cacheKey = `${tab.id}-${frameIdx}`;
    const gen = ++drawGenRef.current;

    const drawFrame = (img: HTMLImageElement) => {
      // Utilise TOUJOURS les dimensions DICOM originales comme espace de coordonnées.
      // Les hooks d'interaction (useCanvasInteractions) utilisent aussi data.cols/data.rows
      // via getState() → les deux transforms sont identiques → pas de décalage de mesure.
      const iw = data.cols;
      const ih = data.rows;
      const t  = computeTransform(iw, ih, canvasSize.w, canvasSize.h, zoom, panX, panY);

      // Contraste / luminosité via manipulation pixel (formule linéaire standard)
      // formula: out = contrast × (pixel − 128) + 128 + brightness
      // → contrast et brightness sont indépendants et intuitifs.
      ctx.drawImage(img, t.offX, t.offY, iw * t.scale, ih * t.scale);

      if (contrast !== 1 || brightness !== 0) {
        // On travaille uniquement sur la région visible de l'image (coords canvas clampées)
        const rx = Math.max(0, Math.round(t.offX));
        const ry = Math.max(0, Math.round(t.offY));
        const rw = Math.min(canvasSize.w, Math.round(t.offX + iw * t.scale)) - rx;
        const rh = Math.min(canvasSize.h, Math.round(t.offY + ih * t.scale)) - ry;
        if (rw > 0 && rh > 0) {
          const imgData = ctx.getImageData(rx, ry, rw, rh);
          const d = imgData.data;
          const c = contrast;
          const b = brightness; // −100 … +100
          // Pivot à 0 (adapté aux images sombres comme l'échographie) :
          // output = c * pixel + b
          // → contrast=3 triple la dynamique sans écraser les darks vers 0
          for (let i = 0; i < d.length; i += 4) {
            d[i]   = Math.max(0, Math.min(255, c * d[i]   + b));
            d[i+1] = Math.max(0, Math.min(255, c * d[i+1] + b));
            d[i+2] = Math.max(0, Math.min(255, c * d[i+2] + b));
          }
          ctx.putImageData(imgData, rx, ry);
        }
      }

      // Détections
      const dets = (detectionsBy.original ?? [])[frameIdx] ?? [];
      if (dets.length) drawDetections(ctx, dets, t.scale, t.offX, t.offY);

      // Mesures finalisées
      const measures = measuresByFrame[frameIdx] ?? [];
      for (let i = 0; i < measures.length; i++) {
        drawMeasureSegment(ctx, measures[i].pts[0], measures[i].pts[1],
          t, canvasSize.w, canvasSize.h, i === selectedMeasure, data.pixelSpacing, measures[i].labelOffset);
      }

      // Mesure en cours de dessin
      if (measurePreview) {
        drawMeasureSegment(ctx, measurePreview[0], measurePreview[1],
          t, canvasSize.w, canvasSize.h, false, data.pixelSpacing);
      }
    };

    // Lookup / charge l'image depuis le cache
    const cached = imgCacheRef.current.get(cacheKey);
    if (cached) {
      drawFrame(cached);
    } else {
      const img = new Image();
      img.onload = () => {
        imgCacheRef.current.set(cacheKey, img);
        if (imgCacheRef.current.size > 200) {
          const firstKey = imgCacheRef.current.keys().next().value;
          if (firstKey !== undefined) imgCacheRef.current.delete(firstKey);
        }
        // Dessine seulement si l'effet n'a pas été re-déclenché entretemps
        // (changement d'onglet ou de frame pendant le chargement de l'image)
        if (drawGenRef.current === gen) drawFrame(img);
      };
      img.src = `data:image/jpeg;base64,${b64}`;
    }
  }, [
    tab, canvasSize, measurePreview,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    tab?.frameIdx, tab?.zoom, tab?.panX, tab?.panY,
    tab?.contrast, tab?.brightness, tab?.selectedMeasure,
    tab?.measuresByFrame, tab?.detectionsBy,
  ]);

  // Vue courante et badge
  const hasAnalysis = !!(tab?.detectionsBy.original?.some(d => d.length > 0));
  const modeBadgeTxt = hasAnalysis ? 'ANALYSE STARHE' : 'ORIGINAL';
  const zoomPct = tab ? Math.round(tab.zoom * 100) : 100;
  const viewMode = tab?.viewMode ?? 'normal';

  const cursorMap: Record<ViewMode, string> = {
    normal:  'default',
    pan:     'grab',
    measure: 'crosshair',
    series:  'ns-resize',
  };

  return (
    <div
      ref={wrapRef}
      style={{
        flex: 1, position: 'relative', background: CANVAS_BG, overflow: 'hidden',
        display: 'flex', flexDirection: 'column',
      }}
    >
      {/* Badge mode + zoom */}
      <div
        style={{
          position: 'absolute', top: 8, left: 8,
          display: 'flex', gap: 6, zIndex: 10, pointerEvents: 'none',
        }}
      >
        <span
          style={{
            background: hasAnalysis ? '#1e3a5f' : '#dbeafe',
            color:      hasAnalysis ? '#90caf9' : '#1d4ed8',
            fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
          }}
        >
          {modeBadgeTxt}
        </span>
        <span
          style={{
            background: '#1a1a2e', color: SBAR_MUTED,
            fontSize: 10, padding: '2px 6px', borderRadius: 4,
          }}
        >
          {zoomPct} %
        </span>
        {viewMode !== 'normal' && (
          <span
            style={{
              background: BLUE, color: '#fff',
              fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
            }}
          >
            {viewMode === 'pan' ? '✋ Pan' : viewMode === 'measure' ? '📏 Mesure' : '↕ Série'}
          </span>
        )}
      </div>

      <canvas
        ref={canvasRef}
        width={canvasSize.w}
        height={canvasSize.h}
        tabIndex={0}
        style={{
          outline: 'none',
          cursor: cursorMap[viewMode],
          display: 'block',
          width: '100%',
          height: '100%',
        }}
        onWheel={interactions.onWheel}
        onMouseDown={e => {
          interactions.onMouseDown(e);
          interactions.onContextMenuDown(e);
        }}
        onMouseMove={interactions.onMouseMove}
        onMouseLeave={interactions.onMouseLeave}
        onMouseUp={e => {
          interactions.onMouseUp(e);
          interactions.onContextMenuUp(e);
        }}
        onContextMenu={e => e.preventDefault()}
      />
    </div>
  );
}
