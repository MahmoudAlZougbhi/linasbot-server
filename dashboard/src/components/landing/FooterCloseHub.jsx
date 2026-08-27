/**
 * Karen footer hub: tall misty Linas star + tiny bright core.
 * Uses the brand star path (same silhouette as LinasMark).
 */
const STAR_PATH =
  'M32 4 C35.6 23.5 42.2 30.2 60.5 33.5 C42.2 36.8 35.6 43.5 32 63 C28.4 43.5 21.8 36.8 3.5 33.5 C21.8 30.2 28.4 23.5 32 4Z';

/** @param {{ className?: string, style?: React.CSSProperties }} props */
export default function FooterCloseHub({ className = '', style }) {
  return (
    <svg
      className={className}
      style={style}
      viewBox="0 0 64 67"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <radialGradient id="lpCloseHubFill" cx="50%" cy="50%" r="55%">
          <stop offset="0%" stopColor="#b8ffe8" stopOpacity="0.55" />
          <stop offset="42%" stopColor="#3dffc2" stopOpacity="0.32" />
          <stop offset="100%" stopColor="#06715F" stopOpacity="0.05" />
        </radialGradient>
        <radialGradient id="lpCloseHubCoreGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
          <stop offset="35%" stopColor="#9fffe0" stopOpacity="0.85" />
          <stop offset="100%" stopColor="#3dffc2" stopOpacity="0" />
        </radialGradient>
        <filter id="lpCloseHubMist" x="-40%" y="-40%" width="180%" height="180%">
          <feTurbulence type="fractalNoise" baseFrequency="1.15" numOctaves="3" seed="7" result="n" />
          <feColorMatrix
            in="n"
            type="matrix"
            values="0 0 0 0 0.24
                    0 0 0 0 1
                    0 0 0 0 0.76
                    0 0 0 0.55 0"
            result="tint"
          />
          <feComposite in="tint" in2="SourceGraphic" operator="in" result="clipped" />
          <feGaussianBlur in="clipped" stdDeviation="0.35" result="soft" />
          <feBlend in="SourceGraphic" in2="soft" mode="screen" />
        </filter>
        <filter id="lpCloseHubBloom" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="3.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="lpCloseHubSpark" x="-120%" y="-120%" width="340%" height="340%">
          <feGaussianBlur stdDeviation="1.6" result="g" />
          <feMerge>
            <feMergeNode in="g" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Soft bloom behind mist */}
      <ellipse cx="32" cy="33.5" rx="14" ry="18" fill="url(#lpCloseHubCoreGlow)" opacity="0.45" />

      {/* Large misty star body */}
      <g filter="url(#lpCloseHubMist)" opacity="0.92">
        <path d={STAR_PATH} fill="url(#lpCloseHubFill)" filter="url(#lpCloseHubBloom)" />
      </g>

      {/* Extra soft silhouette pass (taller feel) */}
      <path d={STAR_PATH} fill="#3dffc2" opacity="0.12" />

      {/* Tiny bright core — same star, scaled down */}
      <g transform="translate(32 33.5) scale(0.22) translate(-32 -33.5)" filter="url(#lpCloseHubSpark)">
        <path d={STAR_PATH} fill="#ffffff" />
      </g>
      <circle cx="32" cy="33.5" r="1.35" fill="#ffffff" />
    </svg>
  );
}
