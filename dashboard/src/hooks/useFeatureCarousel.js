import { useCallback, useEffect, useRef, useState } from 'react';
import { usePrefersReducedMotion } from './usePrefersReducedMotion';

const AUTOPLAY_MS = 4500;

/**
 * Feature carousel: autoplay continues, and the user can still step/drag at any time.
 * Hover, focus, touch, and a hidden tab pause autoplay; the next move restarts the timer.
 * @param {number} count
 * @param {number} [initialIndex]
 */
export function useFeatureCarousel(count, initialIndex = 2) {
  const reduced = usePrefersReducedMotion();
  const [index, setIndex] = useState(Math.min(initialIndex, Math.max(0, count - 1)));
  const [paused, setPaused] = useState(false);
  const interacting = useRef(false);

  const go = useCallback(
    /**
     * @param {number} next
     * @param {boolean} [_manual]
     */
    (next, _manual = false) => {
      if (count <= 0) return;
      setIndex(((next % count) + count) % count);
    },
    [count],
  );

  const next = useCallback(() => go(index + 1, true), [go, index]);
  const prev = useCallback(() => go(index - 1, true), [go, index]);

  const pause = useCallback(() => {
    interacting.current = true;
    setPaused(true);
  }, []);
  const resume = useCallback(() => {
    interacting.current = false;
    setPaused(false);
  }, []);

  useEffect(() => {
    if (reduced || count <= 1 || paused) return undefined;
    const id = setInterval(() => {
      if (document.visibilityState === 'hidden') return;
      if (interacting.current) return;
      setIndex((current) => (current + 1) % count);
    }, AUTOPLAY_MS);
    return () => clearInterval(id);
  }, [count, index, paused, reduced]);

  return { index, go, next, prev, pause, resume, reduced };
}
