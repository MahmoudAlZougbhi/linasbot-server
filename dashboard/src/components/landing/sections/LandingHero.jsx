import { LANDING_ASSETS } from '../../../constants/landingDesignAssets';

/**
 * Hero section — matches linas-landing-01-hero.jpg composition.
 * @param {{ onOpenGuest?: () => void }} props
 */
export default function LandingHero({ onOpenGuest }) {
  return (
    <section className="relative overflow-hidden border-b border-[#E4E8E6] bg-[#F6F7F6]">
      <div className="pointer-events-none absolute inset-y-0 right-0 w-[55%] opacity-70" aria-hidden="true">
        <div className="absolute right-[8%] top-1/2 h-[28rem] w-[28rem] -translate-y-1/2 rounded-full border border-[#06715F]/10" />
        <div className="absolute right-[4%] top-1/2 h-[36rem] w-[36rem] -translate-y-1/2 rounded-full border border-[#06715F]/08" />
        <div className="absolute right-0 top-1/2 h-[44rem] w-[44rem] -translate-y-1/2 rounded-full border border-[#06715F]/05" />
      </div>

      <div className="relative mx-auto grid max-w-6xl gap-10 px-4 pb-16 pt-14 sm:px-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:items-center lg:pb-20 lg:pt-16">
        <div>
          <p className="flex items-center gap-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#06715F]">
            <span className="inline-block h-px w-5 bg-[#06715F]" aria-hidden="true" />
            AI messaging for social media
          </p>
          <h1 className="mt-4 max-w-xl text-4xl font-semibold tracking-tight text-[#171A19] sm:text-5xl lg:text-[3.25rem] lg:leading-[1.08]">
            Turn every DM and comment into a helpful answer.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-[#5C6663] sm:text-lg">
            Linas AI answers customers using business facts you approve—while one chat-first Owner Copilot keeps setup,
            control, and visibility in your hands.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onOpenGuest}
              className="rounded-full bg-[#06715F] px-5 py-3 text-base font-semibold text-white shadow-lg shadow-[#06715F]/25 hover:bg-[#0B3D34] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F] focus-visible:ring-offset-2"
            >
              Try Guest AI →
            </button>
            <a
              href="#get-app"
              className="rounded-full border border-[#D5DCD8] bg-white px-5 py-3 text-base font-semibold text-[#171A19] hover:bg-[#F0F3F1] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]"
            >
              Get the app
            </a>
          </div>

          <dl className="mt-10 grid max-w-md grid-cols-3 gap-0 border-t border-[#E4E8E6] pt-6">
            {[
              { value: '4', label: 'Meta reply surfaces' },
              { value: '1', label: 'Owner Copilot' },
              { value: '10', label: 'guest prompts' },
            ].map((stat, i) => (
              <div key={stat.label} className={`px-3 ${i > 0 ? 'border-l border-[#E4E8E6]' : 'pl-0'}`}>
                <dt className="sr-only">{stat.label}</dt>
                <dd>
                  <p className="text-2xl font-semibold text-[#171A19]">{stat.value}</p>
                  <p className="mt-1 text-xs leading-snug text-[#5C6663]">{stat.label}</p>
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-5 flex items-start gap-2 text-sm text-[#5C6663]">
            <span className="mt-0.5 text-[#06715F]" aria-hidden="true">
              ✓
            </span>
            Built for DMs and comments. No post, Story, Reel, or video publishing.
          </p>
        </div>

        <div className="relative mx-auto w-full max-w-md lg:max-w-none">
          <div className="relative mx-auto aspect-[4/5] w-full max-w-[26rem]">
            <img
              src={LANDING_ASSETS.appScreens.integrations}
              alt="Meta integrations connected in Linas AI"
              className="absolute left-0 top-6 w-[58%] rotate-[-6deg] rounded-[1.6rem] border border-black/10 shadow-2xl"
              width={320}
              height={640}
            />
            <img
              src={LANDING_ASSETS.appScreens.ownerCopilot}
              alt="Owner Copilot chat drafting a greeting"
              className="absolute bottom-0 right-0 w-[68%] rotate-[4deg] rounded-[1.6rem] border border-black/10 shadow-2xl"
              width={360}
              height={720}
            />
            <div className="absolute left-[8%] top-[42%] z-10 flex items-center gap-2 rounded-full border border-[#E4E8E6] bg-white px-3 py-2 text-sm font-medium text-[#171A19] shadow-lg">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#06715F] text-[0.65rem] text-white">
                ✓
              </span>
              Customer reply ready
            </div>
          </div>
        </div>
      </div>

      <div className="bg-[#171A19] text-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-white/80">
            One system for the conversations that matter
          </p>
          <div className="flex flex-wrap gap-2">
            {['Social media DMs', 'Comments', 'Approved facts', 'Owner Copilot'].map((label) => (
              <span
                key={label}
                className="rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-white/90"
              >
                {label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
