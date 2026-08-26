import { HOW_IT_WORKS_HEADLINE } from '../../constants/landingHowItWorks';
import { POINT_ICONS } from './HowItWorksIcons';

/**
 * @param {{
 *   step: {
 *     n: string,
 *     kicker: string,
 *     title: string,
 *     body: string,
 *     points: Array<{ title: string, body: string }>,
 *   },
 * }} props
 */
export default function HowItWorksCopy({ step }) {
  return (
    <div className="relative z-[1] max-w-lg">
      <p className="flex items-center gap-2 text-[0.72rem] font-semibold uppercase tracking-[0.22em] text-[#00C9A0]">
        <span>+</span> How it works
      </p>
      <h2 className="mt-5 max-w-[11.2em] text-[2.55rem] font-bold leading-[1.08] tracking-tight text-[#171A19] sm:text-[3.1rem]">
        {HOW_IT_WORKS_HEADLINE}
      </h2>
      <p className="mt-10 flex items-baseline gap-2 font-semibold uppercase tracking-[0.18em] text-[#00C9A0]">
        <span className="text-[1.05rem] tracking-[0.12em]">{step.n}</span>
        <span className="text-[0.78rem]">{step.kicker}</span>
      </p>
      <h3 className="mt-3 text-[1.75rem] font-bold leading-snug tracking-tight text-[#171A19]">{step.title}</h3>
      <p className="mt-3 max-w-[28rem] text-[0.95rem] leading-relaxed text-[#6B746F]">{step.body}</p>
      <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-3 sm:gap-6">
        {step.points.map((point, i) => {
          const Icon = POINT_ICONS[i];
          if (!Icon) return null;
          return (
            <div key={point.title}>
              <span className="flex h-11 w-11 items-center justify-center rounded-full border border-[#00C9A0] text-[#00C9A0]">
                <Icon />
              </span>
              <p className="mt-3 text-sm font-semibold text-[#171A19]">{point.title}</p>
              <p className="mt-1 text-[0.78rem] leading-snug text-[#6B746F]">{point.body}</p>
            </div>
          );
        })}
      </div>
      <div className="mt-16 flex items-end gap-3 text-[0.82rem] text-[#8A938F]">
        <span className="hiw-scroll-stack" aria-hidden="true">
          <span className="hiw-scroll-dot" />
          <span className="hiw-scroll-stem" />
          <span className="hiw-scroll-mouse" />
        </span>
        Scroll to continue
      </div>
    </div>
  );
}
