import { useEffect, useRef, useState } from 'react';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';

/**
 * @param {{ value: number | null | undefined, duration?: number, className?: string }} props
 */
export default function CountUp({ value, duration = 2000, className = '' }) {
  const reduced = usePrefersReducedMotion();
  const [shown, setShown] = useState(0);
  const fromRef = useRef(0);

  useEffect(() => {
    if (value == null || Number.isNaN(value)) return undefined;
    const target = Math.max(0, Math.floor(value));
    if (reduced) {
      setShown(target);
      fromRef.current = target;
      return undefined;
    }
    const startVal = fromRef.current;
    const start = performance.now();
    let frame = 0;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      const next = Math.round(startVal + (target - startVal) * eased);
      setShown(next);
      if (t < 1) frame = requestAnimationFrame(tick);
      else fromRef.current = target;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration, reduced]);

  if (value == null) return <span className={className}>—</span>;
  return <span className={className}>{formatImpact(shown)}</span>;
}

/** @param {number} n */
export function formatImpact(n) {
  if (n >= 1_000_000) return `${Math.floor(n / 1_000_000)}M+`;
  if (n >= 10_000) return `${Math.floor(n / 1000)}K+`;
  return n.toLocaleString('en-US');
}
