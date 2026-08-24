import LinasStar from './LinasStar';
import HowItWorksPhone from './HowItWorksPhone';
import { ChatGlyph, CoinGlyph, DocGlyph } from './HowItWorksIcons';

const FLOATS = [
  { Icon: CoinGlyph, title: 'Credits', value: '12,480 remaining', className: 'left-0 top-[18%] lg:-left-6' },
  { Icon: ChatGlyph, title: 'Replies', value: '88 total replies', className: 'right-0 top-[38%] lg:-right-10' },
  { Icon: DocGlyph, title: 'Requests', value: '12 total requests', className: 'right-[4%] bottom-[22%] lg:-right-4' },
];

/**
 * @param {{
 *   step: { n: string, kicker: string, image: string, alt: string, builtScreen?: string },
 *   prev?: { n: string, kicker: string } | null,
 *   next?: { n: string, kicker: string } | null,
 * }} props
 */
export default function HowItWorksStage({ step, prev, next }) {
  return (
    <div className="hiw-stage mx-auto flex min-h-[40rem] w-full max-w-[34rem] items-center justify-center">
      <svg className="hiw-path" viewBox="0 0 400 720" preserveAspectRatio="none" aria-hidden="true">
        <path
          className="hiw-path-line"
          d="M210 8 C 70 90, 340 150, 188 248 C 40 340, 360 410, 200 510 C 70 590, 310 650, 188 712"
        />
        <circle className="hiw-node" cx="188" cy="248" r="6" />
        <circle className="hiw-node hiw-node-active" cx="200" cy="510" r="7" />
        <circle className="hiw-node" cx="188" cy="712" r="5.5" />
        {prev ? (
          <text className="hiw-path-label" x="214" y="244">
            {prev.n} {titleCase(prev.kicker)}
          </text>
        ) : null}
        <text className="hiw-path-label hiw-path-label-active" x="226" y="506">
          {step.n} {titleCase(step.kicker)}
        </text>
        {next ? (
          <text className="hiw-path-label" x="214" y="708">
            {next.n} {titleCase(next.kicker)}
          </text>
        ) : null}
      </svg>
      <span className="absolute left-[46%] top-[66%] z-[3] text-[#3dffc2]" aria-hidden="true">
        <LinasStar className="h-7 w-7 drop-shadow-[0_0_10px_rgba(61,255,194,0.9)]" color="#3dffc2" />
      </span>
      {FLOATS.map((item) => (
        <div key={item.title} className={`hiw-float ${item.className}`}>
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#E8F7F1] text-[#06715F]">
            <item.Icon className="h-4 w-4" />
          </span>
          <span>
            <p className="text-[11px] font-semibold text-[#171A19]">{item.title}</p>
            <p className="text-[10px] text-[#6B746F]">{item.value}</p>
          </span>
        </div>
      ))}
      <HowItWorksPhone step={step} />
    </div>
  );
}

/** @param {string} value */
function titleCase(value) {
  const short = value.split('/')[0].trim().toLowerCase();
  return short.replace(/\b\w/g, (ch) => ch.toUpperCase());
}
