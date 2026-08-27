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
    /** @param {number} now */
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
function trimOneDecimal(n) {
  const t = n.toFixed(1);
  return t.endsWith('.0') ? t.slice(0, -2) : t;
}

/**
 * Compact impact labels so the live-network digit stays layout-stable.
 * <1000 → plain digits; ≥1000 → 1.1k; ≥1M → 5.5m
 * @param {number} n
 */
export function formatImpact(n) {
  const v = Math.max(0, Math.floor(Number(n) || 0));
  if (v >= 1_000_000) return `${trimOneDecimal(v / 1_000_000)}m`;
  if (v >= 1_000) return `${trimOneDecimal(v / 1_000)}k`;
  return String(v);
}
