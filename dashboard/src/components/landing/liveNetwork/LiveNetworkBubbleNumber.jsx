import { useEffect, useId, useRef, useState } from 'react';
import { usePrefersReducedMotion } from '../../../hooks/usePrefersReducedMotion';
import { formatImpact } from '../CountUp';
import {
  BUBBLE_PATTERN_H,
  BUBBLE_PATTERN_W,
  BubblePatternContent,
} from './liveNetworkBubblePattern';

/** ViewBox width budget so 63 / 1.1k / 5.5m stay compact in the flow. */
function labelViewBoxWidth(label) {
  const len = Math.max(1, label.length);
  // Slightly tighter than full Inter advance so lines can tuck under the glyph.
  return Math.max(96, Math.min(260, Math.round(len * 58)));
}

/**
 * Dynamic replies digit — Karen mosaic fill, clipped ON the glyph.
 * Width tracks the formatted label so flow lines stay glued for any count.
 * @param {{ value: number | null }} props
 */
export default function LiveNetworkBubbleNumber({ value }) {
  const uid = useId().replace(/:/g, '');
  const patternId = `${uid}-msg`;
  const reduced = usePrefersReducedMotion();
  const target = value == null || Number.isNaN(value) ? 0 : Math.max(0, Math.floor(value));
  const [shown, setShown] = useState(target);
  const fromRef = useRef(target);

  useEffect(() => {
    if (reduced) {
      setShown(target);
      fromRef.current = target;
      return undefined;
    }
    const startVal = fromRef.current;
    const start = performance.now();
    const duration = 2000;
    let frame = 0;
    /** @param {number} now */
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      setShown(Math.round(startVal + (target - startVal) * eased));
      if (t < 1) frame = requestAnimationFrame(tick);
      else fromRef.current = target;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, reduced]);

  const label = formatImpact(shown);
  const vbW = labelViewBoxWidth(label);
  const showHolePlate = label === '0';

  return (
    <div className="lp-net-bubble-num" aria-busy={value == null || undefined} aria-label={label}>
      {showHolePlate ? <span className="lp-net-bubble-num__plate" aria-hidden="true" /> : null}
      <svg
        className="lp-net-bubble-num__svg"
        viewBox={`0 0 ${vbW} 110`}
        role="img"
        aria-hidden="true"
      >
        <defs>
          <pattern
            id={patternId}
            width={BUBBLE_PATTERN_W}
            height={BUBBLE_PATTERN_H}
            patternUnits="userSpaceOnUse"
            patternTransform="scale(0.78)"
          >
            <BubblePatternContent />
          </pattern>
        </defs>
        <text className="lp-net-bubble-num__svg-ink" x={vbW / 2} y="86" textAnchor="middle" fill="#0A5348">
          {label}
        </text>
        <text className="lp-net-bubble-num__svg-fill" x={vbW / 2} y="86" textAnchor="middle" fill={`url(#${patternId})`}>
          {label}
        </text>
      </svg>
      <span className="lp-net-bubble-num__sr">{label}</span>
    </div>
  );
}
