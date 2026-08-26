import { PUBLIC_SITE } from '../../../constants/publicSite';
import HeroChannelRow from '../HeroChannelRow';
import HeroPhoneStage from '../HeroPhoneStage';
import LinasStar from '../LinasStar';

export default function LandingHero() {
  return (
    <section className="relative bg-[#F7F8F5] md:min-h-[calc(100svh-5.25rem)]">
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute -right-16 top-0 h-[40rem] w-[40rem] rounded-full bg-[#D8F0E8]/50 blur-3xl" />
      </div>

      <div className="relative mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-8 sm:px-6 md:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] md:gap-2 md:pb-10 md:pt-4">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full bg-[#E7F2EE] px-3.5 py-1.5 text-sm font-medium text-[#06715F]">
            <LinasStar className="h-3.5 w-3.5" />
            {PUBLIC_SITE.heroKicker}
          </p>
          <h1 className="mt-6 max-w-xl text-4xl font-bold tracking-tight text-[#171A19] sm:text-5xl lg:text-[3.45rem] lg:leading-[1.06]">
            Talk to Linas.{' '}
            <span className="mt-1 block">
              Linas talks to <span className="text-[#06715F]">your customers.</span>
            </span>
          </h1>
          <p className="mt-6 max-w-lg text-base leading-relaxed text-[#5C6663] sm:text-lg">{PUBLIC_SITE.heroSupport}</p>
          <p className="mt-7 text-[0.98rem] font-medium text-[#171A19]">{PUBLIC_SITE.heroConnect}</p>
          <HeroChannelRow />
        </div>

        <HeroPhoneStage />
      </div>
    </section>
  );
}
