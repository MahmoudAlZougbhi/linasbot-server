import { useCallback, useEffect, useRef, useState } from 'react';

const ARM_PX = 4;
const FLICK_PX = 42;

/**
 * Drag the card wheel. The row follows the pointer; a short swipe is one step.
 * @param {{
 *   index: number,
 *   go: (next: number) => void,
 *   pause: () => void,
 *   resume: () => void,
 *   stepPx: number,
 * }} opts
 */
export function useCarouselWheel({ index, go, pause, resume, stepPx }) {
  const [offset, setOffset] = useState(0);
  const [dragging, setDragging] = useState(false);
  const startX = useRef(0);
  const lastX = useRef(0);
  const armed = useRef(false);
  const held = useRef(false);
  const pointerId = useRef(/** @type {number | null} */ (null));
  const nodeRef = useRef(/** @type {HTMLElement | null} */ (null));
  const indexRef = useRef(index);
  const stepRef = useRef(stepPx);
  const goRef = useRef(go);
  const resumeRef = useRef(resume);
  indexRef.current = index;
  stepRef.current = stepPx;
  goRef.current = go;
  resumeRef.current = resume;

  const resetOffset = useCallback(() => setOffset(0), []);

  const stopListening = useCallback(() => {
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', onUp);
  }, []);

  const onMove = useCallback((event) => {
    if (pointerId.current !== event.pointerId) return;
    const dx = event.clientX - startX.current;
    lastX.current = dx;
    if (!armed.current) {
      if (Math.abs(dx) < ARM_PX) return;
      armed.current = true;
      setDragging(true);
    }
    event.preventDefault();
    setOffset(dx);
  }, []);

  const onUp = useCallback((event) => {
    if (pointerId.current == null || event.pointerId !== pointerId.current) return;
    const dx = lastX.current;
    const didDrag = armed.current;
    const node = nodeRef.current;
    pointerId.current = null;
    held.current = false;
    armed.current = false;
    nodeRef.current = null;
    if (node && typeof node.releasePointerCapture === 'function') {
      try {
        if (node.hasPointerCapture?.(event.pointerId)) node.releasePointerCapture(event.pointerId);
      } catch {
        /* ignore */
      }
    }
    stopListening();
    setDragging(false);
    if (didDrag) {
      const width = Math.max(1, stepRef.current);
      if (Math.abs(dx) < FLICK_PX) setOffset(0);
      else {
        let steps = Math.round(-dx / width);
        if (steps === 0) steps = dx > 0 ? -1 : 1;
        goRef.current(indexRef.current + steps);
      }
    }
    resumeRef.current();
  }, [stopListening]);

  useEffect(() => () => stopListening(), [stopListening]);

  const onPointerDown = useCallback(
    /** @param {import('react').PointerEvent<HTMLElement>} event */
    (event) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      startX.current = event.clientX;
      lastX.current = 0;
      armed.current = false;
      held.current = true;
      pointerId.current = event.pointerId;
      nodeRef.current = event.currentTarget;
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        /* jsdom / older engines */
      }
      event.preventDefault();
      pause();
      window.addEventListener('pointermove', onMove, { passive: false });
      window.addEventListener('pointerup', onUp);
      window.addEventListener('pointercancel', onUp);
    },
    [onMove, onUp, pause],
  );

  return {
    offset,
    dragging,
    held,
    resetOffset,
    onPointerDown,
  };
}
