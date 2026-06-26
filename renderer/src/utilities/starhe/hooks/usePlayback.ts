// hooks/usePlayback.ts — Gestion de la lecture vidéo DICOM
//
// Réplique exactement la logique de lecture de prototype_tkinter.py :
//  - fps natif du DICOM
//  - multiplicateur de vitesse (0.25× → 3.0×)
//  - saut de N frames par tick si speedMult >= 1
//  - allongement de l'intervalle si speedMult < 1
//  - boucle optionnelle

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

  // Garde les refs à jour sans déclencher de nouvelle animation
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
