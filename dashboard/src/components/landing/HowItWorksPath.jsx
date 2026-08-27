import LinasStar from './LinasStar';

/**
 * Karen How-it-works ribbon — crisp SVG (no stretched bitmap).
 * Curve: top → left star hub → behind phone → bottom.
 */
const PATH =
  'M 420 28 ' +
  'C 300 58, 210 110, 188 168 ' +
  'C 162 236, 248 268, 310 300 ' +
  'C 390 340, 455 360, 470 420 ' +
  'C 488 492, 400 530, 310 555 ' +
  'C 200 588, 120 620, 148 690 ' +
  'C 180 780, 290 820, 360 868';

/** Node positions sampled along the Karen ribbon (viewBox 640×920). */
const NODES = [
  { cx: 360, cy: 48, dim: true },
  { cx: 250, cy: 100, dim: false },
  { cx: 188, cy: 168, dim: true },
  { cx: 220, cy: 240, dim: false },
  { cx: 310, cy: 300, dim: true },
  { cx: 410, cy: 360, dim: false },
  { cx: 470, cy: 420, dim: true },
  { cx: 430, cy: 500, dim: false },
  { cx: 310, cy: 555, dim: true },
  { cx: 180, cy: 620, dim: false },
  { cx: 148, cy: 700, dim: true },
  { cx: 240, cy: 800, dim: false },
  { cx: 360, cy: 868, dim: true },
];

/**
 * @param {{
 *   step: { n: string, kicker: string },
 *   prev?: { n: string, kicker: string } | null,
 *   next?: { n: string, kicker: string } | null,
 * }} props
 */
export default function HowItWorksPath({ step, prev, next }) {
  const prevShow = step.n === '03' ? { n: '02', kicker: 'AI SETUP' } : prev;
  const nextShow = step.n === '03' ? { n: '04', kicker: 'REQUESTS' } : next;

  return (
    <div className="hiw-path-col hidden md:block" aria-hidden="true">
      <svg className="hiw-path" viewBox="0 0 640 920" fill="none" preserveAspectRatio="xMidYMid meet">
        <defs>
          <filter id="hiw-path-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="3.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="hiw-path-stroke" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#7dffd4" stopOpacity="0.55" />
            <stop offset="35%" stopColor="#3dffc2" stopOpacity="0.95" />
            <stop offset="70%" stopColor="#3dffc2" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#7dffd4" stopOpacity="0.5" />
          </linearGradient>
        </defs>

        {/* Soft halo — light, not muddy */}
        <path className="hiw-path-halo" d={PATH} filter="url(#hiw-path-glow)" />
        {/* Crisp core stroke */}
        <path className="hiw-path-core" d={PATH} stroke="url(#hiw-path-stroke)" />

        {NODES.map((node) => (
          <circle
            key={`${node.cx}-${node.cy}`}
            className={node.dim ? 'hiw-node hiw-node-dim' : 'hiw-node'}
            cx={node.cx}
            cy={node.cy}
            r={node.dim ? 4.2 : 5.4}
          />
        ))}
      </svg>

      {prevShow ? (
        <p className="hiw-path-caption hiw-path-caption-prev">
          {prevShow.n} {pathTitle(prevShow.kicker)}
        </p>
      ) : null}

      <div className="hiw-path-active">
        <span className="hiw-path-star-bloom" />
        <LinasStar className="hiw-path-star" color="#3dffc2" showMark={false} />
        <p>
          {step.n} {pathTitle(step.kicker)}
        </p>
      </div>

      {nextShow ? (
        <p className="hiw-path-caption hiw-path-caption-next">
          {nextShow.n} {pathTitle(nextShow.kicker)}
        </p>
      ) : null}
    </div>
  );
}

/** @param {string} value */
function pathTitle(value) {
  const head = value.split('/')[0] ?? value;
  return head
    .trim()
    .split(/\s+/)
    .map((word) => {
      if (word === 'AI' || word === 'Q&A') return word;
      return word.charAt(0) + word.slice(1).toLowerCase();
    })
    .join(' ');
}
