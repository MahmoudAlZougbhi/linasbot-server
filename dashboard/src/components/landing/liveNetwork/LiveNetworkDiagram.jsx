import { useId, useMemo } from 'react';
import { usePrefersReducedMotion } from '../../../hooks/usePrefersReducedMotion';
import {
  LP_NET_BUSINESS,
  LP_NET_CHANNEL_R,
  LP_NET_CHANNELS,
  LP_NET_ORB,
  LP_NET_REPLIES,
  LP_NET_VB,
  lpNetLineStartX,
} from './liveNetworkLayout';

const RX = LP_NET_REPLIES.x;
const RY = LP_NET_REPLIES.y;
const OX = LP_NET_ORB.x;
const OY = LP_NET_ORB.y;
const BX = LP_NET_BUSINESS.x;
const BY = LP_NET_BUSINESS.y;

const FIRST_CH = LP_NET_CHANNELS[0];
const LAST_CH = LP_NET_CHANNELS[LP_NET_CHANNELS.length - 1];
/** Vertical rail sits left of the channel pads — not through their centers. */
const SPINE_X = FIRST_CH.x - LP_NET_CHANNEL_R - 6;

/** Fallback half-width until the digit is measured. */
const DEFAULT_HALF_W = 52;

/**
 * @param {number} _halfW
 * @param {number} endX  absolute SVG x where IN paths should end (under left rim)
 */
function buildInPaths(_halfW, endX) {
  const stop = endX;
  return LP_NET_CHANNELS.map((ch) => {
    const startX = lpNetLineStartX(ch.x);
    const midY = RY + (ch.y - RY) * 0.2;
    const reach = Math.max(24, Math.min(56, (stop - startX) * 0.35));
    return `M${startX} ${ch.y} C ${startX + reach} ${ch.y}, ${stop - reach} ${ch.y * 0.45 + midY * 0.55}, ${stop - 8} ${midY} S ${stop - 1} ${RY}, ${stop} ${RY}`;
  });
}

/** @param {number} halfW */
function buildToOrbPaths(halfW) {
  const right = RX + halfW;
  /** Start under the right rim so strokes look like they leave the glyph. */
  const start = right - Math.min(36, halfW * 0.58);
  return [
    `M${start} ${RY - 14} C ${right + 10} ${RY - 24}, ${OX - 50} ${OY - 28}, ${OX - 22} ${OY - 8}`,
    `M${start + 2} ${RY} C ${right + 14} ${RY}, ${OX - 48} ${OY}, ${OX - 22} ${OY}`,
    `M${start} ${RY + 14} C ${right + 10} ${RY + 24}, ${OX - 50} ${OY + 28}, ${OX - 22} ${OY + 8}`,
  ];
}

const TO_BUSINESS_PATHS = [
  `M${OX + 22} ${OY - 8} C ${OX + 50} ${OY - 32}, ${BX - 50} ${BY - 24}, ${BX - 6} ${BY - 6}`,
  `M${OX + 22} ${OY} C ${OX + 55} ${OY}, ${BX - 50} ${BY}, ${BX - 6} ${BY}`,
  `M${OX + 22} ${OY + 8} C ${OX + 50} ${OY + 32}, ${BX - 50} ${BY + 24}, ${BX - 6} ${BY + 6}`,
];

/** @param {{ scale?: number }} props */
function MessageIcon({ scale = 1 }) {
  const w = 20 * scale;
  const h = 13 * scale;
  return (
    <g>
      <rect className="lp-net-chip" x={-w / 2} y={-h / 2} width={w} height={h} rx={3.2 * scale} />
      <circle cx={-w / 2 + 4.2 * scale} cy={0} r={1.55 * scale} fill="#06715F" />
      <line
        x1={-w / 2 + 7.2 * scale}
        y1={-2 * scale}
        x2={w / 2 - 3.2 * scale}
        y2={-2 * scale}
        stroke="#C5D1CC"
        strokeWidth={1.05 * scale}
        strokeLinecap="round"
      />
      <line
        x1={-w / 2 + 7.2 * scale}
        y1={2.1 * scale}
        x2={w / 2 - 5.5 * scale}
        y2={2.1 * scale}
        stroke="#C5D1CC"
        strokeWidth={1.05 * scale}
        strokeLinecap="round"
      />
    </g>
  );
}

/**
 * @param {{ pathId: string, delay: string, duration: string, scale?: number, reverse?: boolean }} props
 */
function MovingMessage({ pathId, delay, duration, scale = 1, reverse = false }) {
  return (
    <g className="lp-net-packet">
      <animateMotion
        dur={duration}
        begin={delay}
        repeatCount="indefinite"
        rotate="0"
        keyPoints={reverse ? '1;0' : '0;1'}
        keyTimes="0;1"
        calcMode="linear"
      >
        <mpath href={`#${pathId}`} />
      </animateMotion>
      <MessageIcon scale={scale} />
    </g>
  );
}

/**
 * Flow lines + packets. `digitHalfW` comes from a live measure of the replies glyph.
 * @param {{ replies?: number | null, digitHalfW?: number | null }} props
 */
export default function LiveNetworkDiagram({ replies: _replies = null, digitHalfW = null }) {
  const uid = useId().replace(/:/g, '');
  const reduced = usePrefersReducedMotion();
  const halfW = digitHalfW != null && digitHalfW > 0 ? digitHalfW : DEFAULT_HALF_W;
  /** Deep tuck under the outer left stroke — lines meet the glyph, not hang short. */
  const tuck = Math.min(40, Math.max(18, halfW * 0.62));
  const inEndX = RX - halfW + tuck;
  const inPaths = useMemo(() => buildInPaths(halfW, inEndX), [halfW, inEndX]);
  const toOrbPaths = useMemo(() => buildToOrbPaths(halfW), [halfW]);

  return (
    <svg
      className="lp-net-diagram"
      viewBox={`0 0 ${LP_NET_VB.w} ${LP_NET_VB.h}`}
      fill="none"
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      {/* Spine left of channels (first→last), not behind icon centers */}
      <line
        className="lp-net-channel-spine-svg"
        x1={SPINE_X}
        y1={FIRST_CH.y}
        x2={SPINE_X}
        y2={LAST_CH.y}
      />

      {inPaths.map((d, i) => (
        <path key={`in-${i}`} id={`${uid}-in-${i}`} className="lp-net-line" d={d} />
      ))}
      {toOrbPaths.map((d, i) => (
        <path key={`orb-${i}`} id={`${uid}-orb-${i}`} className="lp-net-line" d={d} />
      ))}
      {TO_BUSINESS_PATHS.map((d, i) => (
        <path key={`biz-${i}`} id={`${uid}-biz-${i}`} className="lp-net-line" d={d} />
      ))}

      {!reduced
        ? inPaths.map((_, i) => (
            <g key={`pkt-in-${i}`}>
              <MovingMessage pathId={`${uid}-in-${i}`} delay={`${0.15 * i}s`} duration={`${3.2 + i * 0.12}s`} reverse />
              <MovingMessage pathId={`${uid}-in-${i}`} delay={`${1.55 + i * 0.2}s`} duration={`${2.9 + i * 0.1}s`} scale={0.92} reverse />
            </g>
          ))
        : null}

      {!reduced
        ? toOrbPaths.map((_, i) => (
            <g key={`pkt-orb-${i}`}>
              <MovingMessage pathId={`${uid}-orb-${i}`} delay={`${0.15 * i}s`} duration={`${3.2 + i * 0.12}s`} scale={0.9} reverse />
              <MovingMessage pathId={`${uid}-orb-${i}`} delay={`${1.55 + i * 0.2}s`} duration={`${2.9 + i * 0.1}s`} scale={0.88} reverse />
            </g>
          ))
        : null}

      {!reduced
        ? TO_BUSINESS_PATHS.map((_, i) => (
            <g key={`pkt-biz-${i}`}>
              <MovingMessage pathId={`${uid}-biz-${i}`} delay={`${0.15 * i}s`} duration={`${3.2 + i * 0.12}s`} scale={0.88} reverse />
              <MovingMessage pathId={`${uid}-biz-${i}`} delay={`${1.55 + i * 0.2}s`} duration={`${2.9 + i * 0.1}s`} scale={0.85} reverse />
            </g>
          ))
        : null}
    </svg>
  );
}
