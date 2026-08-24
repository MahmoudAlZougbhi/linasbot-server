import { HOW_IT_WORKS_HEADLINE } from '../../constants/landingHowItWorks';
import { POINT_ICONS } from './HowItWorksIcons';
import LinasStar from './LinasStar';

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
    <div>
      <p className="flex items-center gap-2 text-[0.7rem] font-semibold uppercase tracking-[0.2em] text-[#2EE6A8]">
        <span>+</span> How it works
      </p>
      <h2 className="mt-3 max-w-md text-[2.35rem] font-semibold leading-[1.12] tracking-tight text-[#171A19] sm:text-[2.75rem]">
        {HOW_IT_WORKS_HEADLINE}
      </h2>
      <p className="mt-8 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#2EE6A8]">
        {step.n} {step.kicker}
      </p>
      <h3 className="mt-3 max-w-md text-[1.65rem] font-semibold leading-snug tracking-tight text-[#171A19]">{step.title}</h3>
      <p className="mt-3 max-w-md text-[0.95rem] leading-relaxed text-[#6B746F]">{step.body}</p>
      <div className="mt-8 grid max-w-lg grid-cols-1 gap-5 sm:grid-cols-3">
        {step.points.map((point, i) => {
          const Icon = POINT_ICONS[i] || POINT_ICONS[0];
          return (
            <div key={point.title}>
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#E7F8F1] text-[#06715F]">
                <Icon />
              </span>
              <p className="mt-2.5 text-sm font-semibold text-[#171A19]">{point.title}</p>
              <p className="mt-1 text-[0.78rem] leading-snug text-[#6B746F]">{point.body}</p>
            </div>
          );
        })}
      </div>
      <p className="mt-12 flex items-center gap-2 text-[0.8rem] text-[#8A938F]">
        <span className="inline-flex h-8 w-6 items-center justify-center rounded-full border border-[#D5DCD8]" aria-hidden="true">
          <span className="h-2 w-1 rounded-full bg-[#8A938F]" />
        </span>
        Scroll to continue
        <LinasStar className="h-3 w-3 opacity-40" />
      </p>
    </div>
  );
}
