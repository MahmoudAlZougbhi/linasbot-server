import { PUBLIC_SITE } from '../../../constants/publicSite';
import { CHANNELS } from '../ChannelIcons';
import HeroPhoneStage from '../HeroPhoneStage';
import LinasStar from '../LinasStar';

export default function LandingHero() {
  return (
    <section className="relative overflow-hidden bg-[#F7F8F5]">
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute -right-16 top-8 h-[32rem] w-[32rem] rounded-full bg-[#D8F0E8]/80 blur-3xl" />
      </div>

      <div className="relative mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-8 sm:px-6 lg:grid-cols-[minmax(0,1.02fr)_minmax(0,0.98fr)] lg:gap-8 lg:pb-24 lg:pt-10">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full bg-[#E7F2EE] px-3 py-1 text-sm font-medium text-[#06715F]">
            <LinasStar className="h-3.5 w-3.5" />
            {PUBLIC_SITE.heroKicker}
          </p>
          <h1 className="mt-5 max-w-xl text-4xl font-semibold tracking-tight text-[#171A19] sm:text-5xl lg:text-[3.35rem] lg:leading-[1.08]">
            Talk to Linas.{' '}
            <span className="mt-1 block">
              Linas talks to <span className="text-[#06715F]">your customers.</span>
            </span>
          </h1>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-[#5C6663] sm:text-lg">{PUBLIC_SITE.heroSupport}</p>
          <p className="mt-5 text-[0.95rem] font-medium text-[#171A19]">{PUBLIC_SITE.heroConnect}</p>
          <div className="mt-6 flex flex-wrap gap-5">
            {CHANNELS.map((ch) => (
              <div key={ch.id} className="flex flex-col items-center gap-1.5">
                <span className="h-11 w-11 overflow-hidden rounded-full shadow-[0_4px_10px_rgba(23,26,25,0.08)]">
                  <ch.Icon className="h-11 w-11" />
                </span>
                <span className="text-[0.7rem] font-medium text-[#5C6663]">{ch.label}</span>
              </div>
            ))}
          </div>
        </div>

        <HeroPhoneStage />
      </div>
    </section>
  );
}
