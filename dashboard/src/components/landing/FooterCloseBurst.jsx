import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import { HERO_CHANNEL_MARKS } from './channelBrandMarks';
import LinasStar from './LinasStar';
import StoreBadges from './StoreBadges';

const VB = { w: 640, h: 280 };
const STAR = { x: 300, y: 126 };
const CH_X = 36;
/** Mark radius so lines tuck into the brand glyph. */
const CH_R = 11;
const CH_YS = [36, 88, 140, 192, 244];

/** Tight Y offsets through the logo — lines pinch into the star core. */
const BUNDLE_Y = [-8, -4, 0, 4, 8];

/** Left edge of store pills in viewBox space. */
const STORE_LEFT = 478;
/** End slightly inside the pill so nodes sit on the rim. */
const STORE_END_X = STORE_LEFT + 10;

/** True vertical centers of the two store pills (note excluded from centering). */
const APP_Y = 122;
const PLAY_Y = 170;
/** Fan: 3 into App Store, 2 into Google Play. */
const STORE_YS = [APP_Y - 12, APP_Y, APP_Y + 12, PLAY_Y - 9, PLAY_Y + 9];

/**
 * Continuous ribbon: into channel mark → pinch through tall star → into store pills.
 * @param {number} i
 */
function pathThrough(i) {
  const y0 = CH_YS[i] ?? CH_YS[0] ?? 140;
  const yMid = STAR.y + (BUNDLE_Y[i] ?? 0);
  const y1 = STORE_YS[i] ?? STORE_YS[0] ?? 140;
  const startX = CH_X + CH_R;
  const pinchL = STAR.x - 22;
  const pinchR = STAR.x + 22;
  return [
    `M${startX} ${y0}`,
    `C ${startX + 70} ${y0}, ${pinchL - 80} ${y0 * 0.22 + yMid * 0.78}, ${pinchL} ${yMid}`,
    `L ${pinchR} ${yMid}`,
    `C ${pinchR + 78} ${yMid}, ${STORE_END_X - 48} ${y1}, ${STORE_END_X} ${y1}`,
  ].join(' ');
}

/** Hub → store pill — pulses leave the center toward the app icons. */
/** @param {number} i */
function pathHubToStore(i) {
  const yMid = STAR.y + (BUNDLE_Y[i] ?? 0);
  const y1 = STORE_YS[i] ?? STORE_YS[0] ?? 140;
  const pinchR = STAR.x + 22;
  return `M${pinchR} ${yMid} C ${pinchR + 78} ${yMid}, ${STORE_END_X - 48} ${y1}, ${STORE_END_X} ${y1}`;
}

/** Hub → channel mark — pulses leave the center toward the channel icons. */
/** @param {number} i */
function pathHubToChannel(i) {
  const y0 = CH_YS[i] ?? CH_YS[0] ?? 140;
  const yMid = STAR.y + (BUNDLE_Y[i] ?? 0);
  const endX = CH_X + CH_R;
  const pinchL = STAR.x - 22;
  // Reverse of the inbound curve: start at hub, end at channel
  return `M${pinchL} ${yMid} C ${pinchL - 80} ${y0 * 0.22 + yMid * 0.78}, ${endX + 70} ${y0}, ${endX} ${y0}`;
}

const FLOW_PATHS = CH_YS.map((_, /** @type {number} */ i) => pathThrough(i));
const PULSE_TO_STORE = CH_YS.map((_, /** @type {number} */ i) => pathHubToStore(i));
const PULSE_TO_CHANNEL = CH_YS.map((_, /** @type {number} */ i) => pathHubToChannel(i));

/** Channels → tall dual star → App Store / Play (Karen clean reference). */
export default function FooterCloseBurst() {
  const reduced = usePrefersReducedMotion();
  const storesMidY = (APP_Y + PLAY_Y) / 2;

  return (
    <div className="lp-close-burst">
      <span className="lp-close-aura" aria-hidden="true" />

      <svg
        className="lp-close-burst-svg"
        viewBox={`0 0 ${VB.w} ${VB.h}`}
        fill="none"
        aria-hidden="true"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          {/* Soft mint at left/right ends, brighter through the hub — matches Karen fade */}
          <linearGradient
            id="lp-close-flow-fade"
            x1="0"
            y1="0"
            x2={VB.w}
            y2="0"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="#3dffc2" stopOpacity="0.5" />
            <stop offset="12%" stopColor="#5affee" stopOpacity="0.65" />
            <stop offset="32%" stopColor="#3dffc2" stopOpacity="0.9" />
            <stop offset="50%" stopColor="#b8ffe8" stopOpacity="1" />
            <stop offset="68%" stopColor="#3dffc2" stopOpacity="0.9" />
            <stop offset="88%" stopColor="#5affee" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#3dffc2" stopOpacity="0.55" />
          </linearGradient>
        </defs>
        {FLOW_PATHS.map((d, i) => (
          <g key={`flow-${i}`}>
            <path id={`lp-close-path-${i}`} className="lp-close-flow" d={d} />
            {/* Pulses leave the hub both ways: channels ← hub → stores */}
            {!reduced ? (
              <>
                <circle className="lp-close-flow-pulse" r="3.4" opacity="1">
                  <animateMotion
                    dur={`${2.1 + i * 0.16}s`}
                    begin={`${i * 0.28}s`}
                    repeatCount="indefinite"
                    path={PULSE_TO_STORE[i]}
                    calcMode="linear"
                  />
                </circle>
                <circle className="lp-close-flow-pulse lp-close-flow-pulse--soft" r="5.8" opacity="0.4">
                  <animateMotion
                    dur={`${2.1 + i * 0.16}s`}
                    begin={`${i * 0.28}s`}
                    repeatCount="indefinite"
                    path={PULSE_TO_STORE[i]}
                    calcMode="linear"
                  />
                </circle>
                <circle className="lp-close-flow-pulse" r="3.4" opacity="1">
                  <animateMotion
                    dur={`${2.1 + i * 0.16}s`}
                    begin={`${0.35 + i * 0.28}s`}
                    repeatCount="indefinite"
                    path={PULSE_TO_CHANNEL[i]}
                    calcMode="linear"
                  />
                </circle>
                <circle className="lp-close-flow-pulse lp-close-flow-pulse--soft" r="5.8" opacity="0.4">
                  <animateMotion
                    dur={`${2.1 + i * 0.16}s`}
                    begin={`${0.35 + i * 0.28}s`}
                    repeatCount="indefinite"
                    path={PULSE_TO_CHANNEL[i]}
                    calcMode="linear"
                  />
                </circle>
              </>
            ) : null}
            <circle className="lp-close-flow-node" cx={CH_X + CH_R} cy={CH_YS[i]} r="2.6" />
            <circle className="lp-close-flow-node" cx={STORE_END_X} cy={STORE_YS[i]} r="2.6" />
          </g>
        ))}
      </svg>

      <div className="lp-close-burst-stage">
        {HERO_CHANNEL_MARKS.map((ch, i) => (
          <span
            key={ch.id}
            className="lp-close-ch"
            style={{
              left: `${(CH_X / VB.w) * 100}%`,
              top: `${((CH_YS[i] ?? CH_YS[0] ?? 140) / VB.h) * 100}%`,
            }}
            title={ch.label}
          >
            <ch.Mark className="lp-close-ch-mark" />
          </span>
        ))}

        {/*
          Tall dual star: back tip near first channel, bottom tip near last channel.
          Core stays bright and larger in the middle; lines pass under into the logo.
        */}
        <div
          className="lp-close-star-hub"
          style={{
            left: `${(STAR.x / VB.w) * 100}%`,
            top: `${(STAR.y / VB.h) * 100}%`,
          }}
        >
          <span className="lp-close-star-bloom" aria-hidden="true" />
          <LinasStar className="lp-close-star-back" color="#3dffc2" showMark={false} />
          <span className="lp-close-star-mist" aria-hidden="true" />
          <LinasStar className="lp-close-star-core" color="#F4FFFB" showMark={false} />
        </div>

        <div
          id="get-app"
          className="lp-close-stores scroll-mt-24"
          style={{
            left: `${(STORE_LEFT / VB.w) * 100}%`,
            top: `${(storesMidY / VB.h) * 100}%`,
          }}
        >
          <div className="lp-close-stores-badges">
            <StoreBadges compact variant="close" />
          </div>
          <p className="lp-close-stores-note">Available on iOS and Android</p>
        </div>
      </div>
    </div>
  );
}
