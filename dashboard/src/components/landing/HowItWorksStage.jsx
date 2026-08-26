import HowItWorksPath from './HowItWorksPath';
import HowItWorksPhone from './HowItWorksPhone';
import HowItWorksStand from './HowItWorksStand';
import LinasStar from './LinasStar';
import { ChatGlyph, CoinGlyph, DocGlyph } from './HowItWorksIcons';

const FLOATS = [
  { Icon: CoinGlyph, title: 'Credits', value: '12,480', hint: 'remaining', className: 'hiw-float-credits' },
  { Icon: ChatGlyph, title: 'Replies', value: '88', hint: 'total replies', className: 'hiw-float-replies' },
  { Icon: DocGlyph, title: 'Requests', value: '12', hint: 'total requests', className: 'hiw-float-requests' },
];

/**
 * @param {{
 *   step: { n: string, kicker: string, image: string, alt: string, builtScreen?: string },
 *   prev?: { n: string, kicker: string, image: string } | null,
 *   next?: { n: string, kicker: string, image: string } | null,
 * }} props
 */
export default function HowItWorksStage({ step, prev, next }) {
  return (
    <div className="hiw-stage relative mx-auto flex min-h-[48rem] w-full max-w-[52rem] items-center justify-center overflow-visible pb-10">
      <span className="hiw-mark-star" aria-hidden="true">
        <span className="hiw-mark-star-glow" />
        <LinasStar className="hiw-mark-star-icon" color="#3dffc2" showMark={false} />
      </span>
      <HowItWorksPath step={step} prev={prev} next={next} />
      {FLOATS.map((item) => (
        <div key={item.title} className={`hiw-float ${item.className}`}>
          <span className="flex h-10 w-10 items-center justify-center rounded-[0.9rem] bg-[#E8FBF4] text-[#00C9A0]">
            <item.Icon className="h-4 w-4" />
          </span>
          <span>
            <p className="text-[11px] font-semibold text-[#171A19]">{item.title}</p>
            <p className="hiw-float-num">{item.value}</p>
            <p className="text-[10px] text-[#8A938F]">{item.hint}</p>
          </span>
        </div>
      ))}
      <div className="hiw-device">
        <div className="hiw-ghost hiw-ghost-a" aria-hidden="true">
          <img src={next?.image || step.image} alt="" />
        </div>
        <div className="hiw-ghost hiw-ghost-b" aria-hidden="true">
          <img src={prev?.image || step.image} alt="" />
        </div>
        <HowItWorksPhone step={step} />
        <HowItWorksStand />
      </div>
    </div>
  );
}
