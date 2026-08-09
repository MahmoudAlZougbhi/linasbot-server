import { LANDING_ASSETS } from '../../../constants/landingDesignAssets';
import LinasMark from '../LinasMark';
import StoreBadges from '../StoreBadges';

/** Download / app promo — matches linas-landing-07-download.jpg */
export default function LandingDownload() {
  return (
    <section className="bg-[#F6F7F6] pb-8 pt-4 sm:pb-12">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="overflow-hidden rounded-[2rem] bg-[#0B0D0C] px-6 py-10 text-white sm:px-10 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center lg:gap-8 lg:py-0">
          <div className="lg:py-14">
            <LinasMark className="h-11 w-11" />
            <p className="mt-5 flex items-center gap-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#54C7AC]">
              <span className="inline-block h-px w-5 bg-[#54C7AC]" aria-hidden="true" />
              Linas in your pocket
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Open the app. Start in chat.</h2>
            <p className="mt-4 max-w-md text-base leading-relaxed text-white/70">
              No dashboard detour. Linas opens directly to the Owner Copilot, with your drawer, history, configuration,
              integrations, audit, team, billing, usage, and settings one tap away.
            </p>
            <div className="mt-8">
              <StoreBadges variant="dark" />
            </div>
            <p className="mt-3 text-xs text-white/45">
              Store buttons activate only after verified listing URLs are configured.
            </p>
          </div>

          <div className="relative mt-10 h-[22rem] lg:mt-0 lg:h-[28rem]">
            <img
              src={LANDING_ASSETS.appScreens.navigation}
              alt="Linas AI navigation drawer"
              className="absolute bottom-0 left-[6%] w-[48%] rotate-[-4deg] rounded-[1.4rem] border border-white/10 shadow-2xl"
              width={320}
              height={640}
            />
            <img
              src={LANDING_ASSETS.appScreens.settings}
              alt="Linas AI settings screen"
              className="absolute bottom-0 right-0 w-[52%] rotate-[5deg] rounded-[1.4rem] border border-white/10 shadow-2xl"
              width={340}
              height={680}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
