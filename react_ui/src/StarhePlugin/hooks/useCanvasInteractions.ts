// hooks/useCanvasInteractions.ts — Pan / Zoom / Mesure / Scroll série
//
// Réplique les interactions du canvas Tkinter de prototype_tkinter.py.
// Le hook retourne des gestionnaires d'événements à attacher au <canvas>.

import { useCallback, useRef } from 'react';
import type { ViewMode, Measure } from '../types';

// ── Types internes ────────────────────────────────────────────────────────────

interface Transform {
  scale: number;
  offX:  number;
  offY:  number;
}

interface InteractState {
  viewMode:        ViewMode;
  zoom:            number;
  panX:            number;
  panY:            number;
  contrast:        number;
  brightness:      number;
  frameIdx:        number;
  frameCount:      number;
  imgW:            number;
  imgH:            number;
  canvasW:         number;
  canvasH:         number;
  measuresByFrame: Record<number, Measure[]>;
  selectedMeasure: number | null;
  pixelSpacing:    [number, number] | null;
}

export interface InteractCallbacks {
  onZoomPan:       (zoom: number, panX: number, panY: number) => void;
  onContrastBright:(contrast: number, brightness: number) => void;
  onFrameChange:   (idx: number) => void;
  onMeasureAdd:    (frameIdx: number, measure: Measure) => void;
  onMeasureMove:   (frameIdx: number, segIdx: number, newPts: [[number, number],[number, number]]) => void;
  onMeasureSelect: (frameIdx: number, segIdx: number | null) => void;
  onContextMenu:   (x: number, y: number) => void;
}

// ── Calcul de la transformation image → écran ─────────────────────────────────

export function computeTransform(
  imgW:    number,
  imgH:    number,
  canvasW: number,
  canvasH: number,
  zoom:    number,
  panX:    number,
  panY:    number,
): Transform {
  if (imgW === 0 || imgH === 0) return { scale: 1, offX: 0, offY: 0 };
  const fitScale = Math.min(canvasW / imgW, canvasH / imgH);
  const scale    = fitScale * zoom;
  const scaledW  = imgW * scale;
  const scaledH  = imgH * scale;
  const offX     = canvasW / 2 - scaledW / 2 + panX;
  const offY     = canvasH / 2 - scaledH / 2 + panY;
  return { scale, offX, offY };
}

export function screenToImg(
  sx: number, sy: number, t: Transform,
): [number, number] {
  return [(sx - t.offX) / t.scale, (sy - t.offY) / t.scale];
}

export function imgToScreen(
  ix: number, iy: number, t: Transform,
): [number, number] {
  return [ix * t.scale + t.offX, iy * t.scale + t.offY];
}

// ── Distance d'un point à un segment ──────────────────────────────────────────

function distToSegment(
  px: number, py: number,
  x1: number, y1: number,
  x2: number, y2: number,
): number {
  const dx = x2 - x1, dy = y2 - y1;
  if (dx === 0 && dy === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

// ── Hit-test sur les mesures ──────────────────────────────────────────────────

function measureHit(
  x: number, y: number,
  measures: Measure[],
  t: Transform,
): [number, 'p1' | 'p2' | 'seg'] | null {
  const EP = 8, LD = 6;
  for (let i = 0; i < measures.length; i++) {
    const [p1, p2] = measures[i].pts;
    const [sx1, sy1] = imgToScreen(p1[0], p1[1], t);
    const [sx2, sy2] = imgToScreen(p2[0], p2[1], t);
    if (Math.hypot(x - sx1, y - sy1) <= EP) return [i, 'p1'];
    if (Math.hypot(x - sx2, y - sy2) <= EP) return [i, 'p2'];
    if (distToSegment(x, y, sx1, sy1, sx2, sy2) <= LD) return [i, 'seg'];
  }
  return null;
}

// ── Hook principal ────────────────────────────────────────────────────────────

export function useCanvasInteractions(
  getState: () => InteractState,
  cbs: InteractCallbacks,
) {
  // État du drag (lbm press)
  const dragRef = useRef<{
    startX:   number;
    startY:   number;
    panX0:    number;
    panY0:    number;
    frameIdx0: number;
    mode:     ViewMode;
  } | null>(null);

  // État de la mesure en cours de dessin
  const drawingRef = useRef<[number, number] | null>(null); // premier point (coords image)

  // Édition d'une mesure existante
  const editRef = useRef<{
    segIdx:    number;
    part:      'p1' | 'p2' | 'seg';
    startImg:  [number, number];
    origPts:   [[number, number], [number, number]];
  } | null>(null);

  // Glissement droit (contraste/luminosité)
  const rclickRef = useRef<{
    startX:    number;
    startY:    number;
    contrast0: number;
    bright0:   number;
    t0:        number;
  } | null>(null);

  // Prévisualisation du segment en cours (pour le parent)
  const previewRef = useRef<[[number, number], [number, number]] | null>(null);
  const _previewSetter = useRef<((p: typeof previewRef.current) => void) | null>(null);

  const setMeasurePreview = useCallback(
    (setter: (p: [[number, number], [number, number]] | null) => void) => {
      _previewSetter.current = setter;
    }, [],
  );

  // ── Helpers ──────────────────────────────────────────────────────────────────

  const getTransform = useCallback((): Transform => {
    const s = getState();
    return computeTransform(s.imgW, s.imgH, s.canvasW, s.canvasH, s.zoom, s.panX, s.panY);
  }, [getState]);

  // ── Molette : zoom centré sur le curseur ──────────────────────────────────────

  const onWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const s   = getState();
    const t   = getTransform();
    const delta = e.deltaY > 0 ? -1 : 1;
    const factor = delta > 0 ? 1.1 : 1 / 1.1;
    const newZoom = Math.max(0.1, Math.min(10, s.zoom * factor));
    const af      = newZoom / s.zoom;
    const cw      = s.canvasW, ch = s.canvasH;
    const mx = e.nativeEvent.offsetX, my = e.nativeEvent.offsetY;
    const newPanX = s.panX * af + (1 - af) * (mx - cw / 2);
    const newPanY = s.panY * af + (1 - af) * (my - ch / 2);
    cbs.onZoomPan(newZoom, newPanX, newPanY);
  }, [getState, getTransform, cbs]);

  // ── Bouton gauche : press ──────────────────────────────────────────────────────

  const onMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) return;
    const s   = getState();
    const t   = getTransform();
    const mx  = e.nativeEvent.offsetX, my = e.nativeEvent.offsetY;

    if (s.viewMode === 'pan') {
      dragRef.current = { startX: mx, startY: my, panX0: s.panX, panY0: s.panY, frameIdx0: s.frameIdx, mode: 'pan' };
      return;
    }

    if (s.viewMode === 'series') {
      dragRef.current = { startX: mx, startY: my, panX0: s.panX, panY0: s.panY, frameIdx0: s.frameIdx, mode: 'series' };
      return;
    }

    if (s.viewMode === 'normal') {
      dragRef.current = { startX: mx, startY: my, panX0: s.panX, panY0: s.panY, frameIdx0: s.frameIdx, mode: 'normal' };
      return;
    }

    if (s.viewMode === 'measure') {
      const measures = s.measuresByFrame[s.frameIdx] ?? [];
      const hit = measureHit(mx, my, measures, t);

      if (hit) {
        const [segIdx, part] = hit;
        cbs.onMeasureSelect(s.frameIdx, segIdx);
        const seg = measures[segIdx];
        editRef.current = {
          segIdx,
          part,
          startImg: screenToImg(mx, my, t),
          origPts:  [seg.pts[0], seg.pts[1]],
        };
        drawingRef.current = null;
        _previewSetter.current?.(null);
      } else {
        cbs.onMeasureSelect(s.frameIdx, null);
        editRef.current = null;
        drawingRef.current = screenToImg(mx, my, t);
        _previewSetter.current?.(null);
      }
    }
  }, [getState, getTransform, cbs]);

  // ── Bouton gauche : drag ───────────────────────────────────────────────────────

  const onMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const mx = e.nativeEvent.offsetX, my = e.nativeEvent.offsetY;
    const s  = getState();

    if (dragRef.current) {
      const d = dragRef.current;
      if (d.mode === 'pan') {
        cbs.onZoomPan(s.zoom, d.panX0 + (mx - d.startX), d.panY0 + (my - d.startY));
        return;
      }
      if (d.mode === 'normal' && s.frameCount > 0) {
        const step    = Math.floor((my - d.startY) / 8);
        const newIdx  = Math.max(0, Math.min(s.frameCount - 1, d.frameIdx0 + step));
        if (newIdx !== s.frameIdx) cbs.onFrameChange(newIdx);
        return;
      }
      if (d.mode === 'series' && s.frameCount > 0) {
        const step   = Math.floor((my - d.startY) / 8);
        const newIdx = Math.max(0, Math.min(s.frameCount - 1, d.frameIdx0 + step));
        if (newIdx !== s.frameIdx) cbs.onFrameChange(newIdx);
        return;
      }
    }

    if (s.viewMode === 'measure') {
      const t = getTransform();
      if (editRef.current) {
        const ed       = editRef.current;
        const curImg   = screenToImg(mx, my, t);
        const dix      = curImg[0] - ed.startImg[0];
        const diy      = curImg[1] - ed.startImg[1];
        const [ox1, oy1] = ed.origPts[0];
        const [ox2, oy2] = ed.origPts[1];
        let newPts: [[number,number],[number,number]];
        if      (ed.part === 'p1')  newPts = [[ox1 + dix, oy1 + diy], [ox2, oy2]];
        else if (ed.part === 'p2')  newPts = [[ox1, oy1], [ox2 + dix, oy2 + diy]];
        else                        newPts = [[ox1 + dix, oy1 + diy], [ox2 + dix, oy2 + diy]];
        cbs.onMeasureMove(s.frameIdx, ed.segIdx, newPts);
      } else if (drawingRef.current) {
        const cur = screenToImg(mx, my, t);
        _previewSetter.current?.([drawingRef.current, cur]);
      }
    }

    // Clic droit maintenu (contraste/luminosité)
    if (rclickRef.current) {
      const r  = rclickRef.current;
      const dx = mx - r.startX, dy = my - r.startY;
      const newC = Math.max(0.1, Math.min(3.0,   r.contrast0 + dx * 0.008));
      const newB = Math.max(-100, Math.min(100, r.bright0  + dy * 0.5));
      cbs.onContrastBright(newC, newB);
    }
  }, [getState, getTransform, cbs]);

  // ── Bouton gauche : release ────────────────────────────────────────────────────

  const onMouseUp = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) {
      dragRef.current = null;
      return;
    }
    const s  = getState();
    const mx = e.nativeEvent.offsetX, my = e.nativeEvent.offsetY;

    dragRef.current = null;

    if (s.viewMode === 'measure') {
      if (editRef.current) {
        editRef.current = null;
        return;
      }
      if (drawingRef.current) {
        const t   = getTransform();
        const p1  = drawingRef.current;
        const p2  = screenToImg(mx, my, t);
        const [sx1, sy1] = imgToScreen(p1[0], p1[1], t);
        const dist = Math.hypot(mx - sx1, my - sy1);
        if (dist > 5) {
          cbs.onMeasureAdd(s.frameIdx, { pts: [p1, p2] });
        }
        drawingRef.current = null;
        _previewSetter.current?.(null);
      }
    }
  }, [getState, getTransform, cbs]);

  // ── Clic droit : press / drag / release ───────────────────────────────────────

  const onContextMenuDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 2) return;
    e.preventDefault();
    const s = getState();
    rclickRef.current = {
      startX: e.nativeEvent.offsetX,
      startY: e.nativeEvent.offsetY,
      contrast0: s.contrast,
      bright0:   s.brightness,
      t0: Date.now(),
    };
  }, [getState]);

  const onContextMenuUp = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 2) return;
    e.preventDefault();
    const r = rclickRef.current;
    rclickRef.current = null;
    if (!r) return;
    const dt = Date.now() - r.t0;
    const dx = Math.abs(e.nativeEvent.offsetX - r.startX);
    const dy = Math.abs(e.nativeEvent.offsetY - r.startY);
    if (dt < 250 && dx < 5 && dy < 5) {
      cbs.onContextMenu(e.clientX, e.clientY);
    }
  }, [cbs]);

  // ── Suppression mesure sélectionnée (Delete / Backspace) ─────────────────────

  const onKeyDown = useCallback((e: KeyboardEvent) => {
    const s = getState();
    if (s.viewMode === 'measure' && s.selectedMeasure !== null &&
        (e.key === 'Delete' || e.key === 'Backspace')) {
      // Signale au parent une suppression via onMeasureMove avec pts spéciales
      // (convention : pts nulles = suppression)
      cbs.onMeasureMove(s.frameIdx, s.selectedMeasure, [[-1, -1], [-1, -1]]);
      cbs.onMeasureSelect(s.frameIdx, null);
    }
  }, [getState, cbs]);

  return {
    onWheel,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    onContextMenuDown,
    onContextMenuUp,
    onKeyDown,
    setMeasurePreview,
    previewRef,
    drawingRef,
  };
}
