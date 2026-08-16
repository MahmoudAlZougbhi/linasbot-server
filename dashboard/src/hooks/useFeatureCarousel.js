import { useCallback, useEffect, useRef, useState } from 'react';
import { usePrefersReducedMotion } from './usePrefersReducedMotion';

const AUTOPLAY_MS = 5500;
const MANUAL_PAUSE_MS = 8000;

/**
 * Feature carousel state: one-step moves, autoplay, pause on hover/focus/touch/hidden.
 * @param {number} count
 * @param {number} [initialIndex]
 */
export function useFeatureCarousel(count, initialIndex = 2) {
  const reduced = usePrefersReducedMotion();
  const [index, setIndex] = useState(Math.min(initialIndex, Math.max(0, count - 1)));
  const [paused, setPaused] = useState(false);
  const lastManual = useRef(0);
  const interacting = useRef(false);

  const go = useCallback(
    /**
     * @param {number} next
     * @param {boolean} [manual]
     */
    (next, manual = false) => {
      if (count <= 0) return;
      const wrapped = ((next % count) + count) % count;
      setIndex(wrapped);
      if (manual) lastManual.current = Date.now();
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
    if (reduced || count <= 1) return undefined;
    const id = setInterval(() => {
      if (document.visibilityState === 'hidden') return;
      if (interacting.current || paused) return;
      if (Date.now() - lastManual.current < MANUAL_PAUSE_MS) return;
      setIndex((current) => (current + 1) % count);
    }, AUTOPLAY_MS);
    return () => clearInterval(id);
  }, [count, paused, reduced]);

  return { index, go, next, prev, pause, resume, reduced };
}
