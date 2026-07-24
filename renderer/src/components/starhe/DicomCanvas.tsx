// components/DicomCanvas.tsx — DICOM viewer with an HTML5 canvas
//
// Features ported from prototype_tkinter.py:
//  - JPEG frame display with cursor-centered pan / zoom
//  - Detection bbox overlay (canvas drawing)
//  - mm measurement tool (canvas drawing, SVG overlay for the endpoints)
//  - Series mode (vertical drag = frame scroll)
//  - Right-click held = contrast (X) / brightness (Y)
//  - Wheel = cursor-centered zoom
//  - Mode bar ("ORIGINAL" / "STARHE ANALYSIS")
//  - Preview of the measure being drawn

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

// ── Draws the detection bboxes ───────────────────────────────────────────────

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

// ── Draws a measure segment ───────────────────────────────────────────────────

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

  // Label position (perpendicular by default, or custom if labelOffset)
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

// ── Component ─────────────────────────────────────────────────────────────────

export interface DicomCanvasProps {
  tab:              TabState | null;
  onZoomPan:        (zoom: number, panX: number, panY: number) => void;
  /** Called on every canvas resize to force the recentering of ALL the
   *  panels (multi-panel). If absent, falls back to onZoomPan(zoom,0,0) (single view). */
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
  // Generation counter: each invocation of the draw effect increments this counter.
  // The img.onload callbacks check that they match the current generation before
  // drawing, preventing a deferred load from overwriting another tab's canvas.
  const drawGenRef = useRef(0);

  // Preview segment being drawn
  const [measurePreview, setMeasurePreview] = useState<
    [[number, number], [number, number]] | null
  >(null);

  // Current canvas size (px)
  // canvasSizeRef: always up to date (updated synchronously in the ResizeObserver)
  // canvasSize    : React state (triggers the re-render and the canvas attribute update)
  const canvasSizeRef = useRef({ w: 640, h: 480 });
  const [canvasSize, setCanvasSize] = useState({ w: 640, h: 480 });

  // Screen pixel density (2 on Retina). The canvas backing store must be
  // allocated in physical pixels, otherwise the frame is upscaled from half
  // the resolution and looks blurry.
  const [dpr, setDpr] = useState(
    () => (typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1),
  );
  useEffect(() => {
    const update = () => setDpr(window.devicePixelRatio || 1);
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  // Size observer
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        const newSize = { w: e.contentRect.width, h: e.contentRect.height };
        canvasSizeRef.current = newSize;   // synchronous: used by getState() right away
        setCanvasSize(newSize);            // asynchronous: triggers the React re-render
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Stable refs for the recentering effect — updated on each render,
  // used in an effect that has only canvasSize in its dependencies.
  const onZoomPanRef = useRef(onZoomPan);
  onZoomPanRef.current = onZoomPan;
  const onPanResetRef = useRef(onPanReset);
  onPanResetRef.current = onPanReset;
  const tabZoomRef = useRef(tab?.zoom ?? 1);
  tabZoomRef.current = tab?.zoom ?? 1;
  const hasDataRef = useRef(!!tab?.data);
  hasDataRef.current = !!tab?.data;

  // When the canvas is resized in single-view mode (e.g. window resize),
  // reset panX=0 / panY=0 to recenter the image.
  // In multi-panel mode (onPanReset provided) do nothing: the pan must
  // be preserved during and after the separator is moved.
  const isFirstSizeRef = useRef(true);
  useEffect(() => {
    if (!hasDataRef.current) return;
    if (onPanResetRef.current) return; // multi-panel: keep the pan
    // Single panel : skip the very first size measurement to preserve user pan/zoom.
    if (isFirstSizeRef.current) { isFirstSizeRef.current = false; return; }
    onZoomPanRef.current(tabZoomRef.current, 0, 0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvasSize.w, canvasSize.h]);

  // State for the interactions hook
  // canvasSizeRef is used (not canvasSize) so that the zoom/pan handlers
  // always see the current dimensions, even during the resize
  // of the separator (before React has re-rendered with the new props).
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
  }), [tab]);  // no need to depend on canvasSize: the ref is always up to date

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

  // Wire up the preview setter
  useEffect(() => {
    interactions.setMeasurePreview(setMeasurePreview);
  }, [interactions]);

  // Listen for Delete / Backspace on the canvas
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

    // HiDPI/Retina: the backing store is in physical pixels
    // (canvas.width = CSS × dpr), but setTransform keeps the whole drawing API
    // in CSS pixels → no other coordinate computation needs to change.
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingQuality = 'high';

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
        'No DICOM loaded — use "Load DICOM file" in the sidebar',
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
    // Key namespaced by tab.id: prevents collisions between files sharing the same
    // identical JPEG header (all start with /9j/4AAQSkZJRgABAQAA in base64).
    const cacheKey = `${tab.id}-${frameIdx}`;
    const gen = ++drawGenRef.current;

    const drawFrame = (img: HTMLImageElement) => {
      // ALWAYS use the original DICOM dimensions as the coordinate space.
      // The interaction hooks (useCanvasInteractions) also use data.cols/data.rows
      // via getState() → both transforms are identical → no measurement offset.
      const iw = data.cols;
      const ih = data.rows;
      const t  = computeTransform(iw, ih, canvasSize.w, canvasSize.h, zoom, panX, panY);

      // Contrast / brightness via pixel manipulation (standard linear formula)
      // formula: out = contrast × (pixel − 128) + 128 + brightness
      // → contrast and brightness are independent and intuitive.
      ctx.drawImage(img, t.offX, t.offY, iw * t.scale, ih * t.scale);

      if (contrast !== 1 || brightness !== 0) {
        // Work only on the visible region of the image (clamped canvas coords)
        const rx = Math.max(0, Math.round(t.offX));
        const ry = Math.max(0, Math.round(t.offY));
        const rw = Math.min(canvasSize.w, Math.round(t.offX + iw * t.scale)) - rx;
        const rh = Math.min(canvasSize.h, Math.round(t.offY + ih * t.scale)) - ry;
        if (rw > 0 && rh > 0) {
          // getImageData/putImageData ignore the context transform and address
          // the backing store directly → convert CSS px to physical px.
          const px = Math.round(rx * dpr);
          const py = Math.round(ry * dpr);
          const pw = Math.round(rw * dpr);
          const ph = Math.round(rh * dpr);
          const imgData = ctx.getImageData(px, py, pw, ph);
          const d = imgData.data;
          const c = contrast;
          const b = brightness; // −100 … +100
          // Pivot at 0 (suited to dark images like ultrasound):
          // output = c * pixel + b
          // → contrast=3 triples the dynamic range without crushing the darks toward 0
          for (let i = 0; i < d.length; i += 4) {
            d[i]   = Math.max(0, Math.min(255, c * d[i]   + b));
            d[i+1] = Math.max(0, Math.min(255, c * d[i+1] + b));
            d[i+2] = Math.max(0, Math.min(255, c * d[i+2] + b));
          }
          ctx.putImageData(imgData, px, py);
        }
      }

      // Detections
      const dets = (detectionsBy.original ?? [])[frameIdx] ?? [];
      if (dets.length) drawDetections(ctx, dets, t.scale, t.offX, t.offY);

      // Finalized measures
      const measures = measuresByFrame[frameIdx] ?? [];
      for (let i = 0; i < measures.length; i++) {
        drawMeasureSegment(ctx, measures[i].pts[0], measures[i].pts[1],
          t, canvasSize.w, canvasSize.h, i === selectedMeasure, data.pixelSpacing, measures[i].labelOffset);
      }

      // Measure being drawn
      if (measurePreview) {
        drawMeasureSegment(ctx, measurePreview[0], measurePreview[1],
          t, canvasSize.w, canvasSize.h, false, data.pixelSpacing);
      }
    };

    // Look up / load the image from the cache
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
        // Draw only if the effect has not been re-triggered in the meantime
        // (tab or frame change while the image is loading)
        if (drawGenRef.current === gen) drawFrame(img);
      };
      img.src = `data:image/jpeg;base64,${b64}`;
    }
  }, [
    tab, canvasSize, dpr, measurePreview,
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
            {viewMode === 'pan' ? '✋ Pan' : viewMode === 'measure' ? '📏 Measure' : '↕ Series'}
          </span>
        )}
      </div>

      <canvas
        ref={canvasRef}
        width={Math.round(canvasSize.w * dpr)}
        height={Math.round(canvasSize.h * dpr)}
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
