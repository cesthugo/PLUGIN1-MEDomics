// hooks/usePlayback.ts — DICOM video playback management
//
// Exactly replicates the playback logic of prototype_tkinter.py:
//  - native DICOM fps
//  - speed multiplier (0.25× → 3.0×)
//  - jump of N frames per tick if speedMult >= 1
//  - interval lengthening if speedMult < 1
//  - optional loop

import { useCallback, useEffect, useRef } from 'react';

interface PlaybackOptions {
  frameCount:  number;
  baseFps:     number;
  speedMult:   number;
  loop:        boolean;
  playing:     boolean;
  frameIdx:    number;
  onFrameChange: (idx: number) => void;
  onStop: () => void;
}

export function usePlayback({
  frameCount,
  baseFps,
  speedMult,
  loop,
  playing,
  frameIdx,
  onFrameChange,
  onStop,
}: PlaybackOptions): void {
  const rafRef   = useRef<number | null>(null);
  const stateRef = useRef({ frameIdx, playing, loop, speedMult, baseFps, frameCount });

  // Keeps the refs up to date without triggering a new animation
  stateRef.current = { frameIdx, playing, loop, speedMult, baseFps, frameCount };

  const step = useCallback(() => {
    const s = stateRef.current;
    if (!s.playing || s.frameCount === 0) return;

    const skip     = s.speedMult >= 1 ? Math.max(1, Math.round(s.speedMult)) : 1;
    let   nextIdx  = s.frameIdx + skip;

    if (nextIdx >= s.frameCount) {
      if (!s.loop) {
        onStop();
        return;
      }
      nextIdx = nextIdx % s.frameCount;
    }

    onFrameChange(nextIdx);

    const baseMsPerFrame   = 1000 / Math.max(1, s.baseFps);
    const intervalMs       = s.speedMult >= 1 ? baseMsPerFrame : baseMsPerFrame / s.speedMult;
    const delayMs          = Math.max(1, intervalMs);

    rafRef.current = window.setTimeout(step, delayMs) as unknown as number;
  }, [onFrameChange, onStop]);

  useEffect(() => {
    if (!playing) {
      if (rafRef.current !== null) {
        clearTimeout(rafRef.current);
        rafRef.current = null;
      }
      return;
    }

    const baseMsPerFrame = 1000 / Math.max(1, baseFps);
    const intervalMs     = speedMult >= 1 ? baseMsPerFrame : baseMsPerFrame / speedMult;
    rafRef.current = window.setTimeout(step, Math.max(1, intervalMs)) as unknown as number;

    return () => {
      if (rafRef.current !== null) {
        clearTimeout(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [playing, step, baseFps, speedMult]);
}
