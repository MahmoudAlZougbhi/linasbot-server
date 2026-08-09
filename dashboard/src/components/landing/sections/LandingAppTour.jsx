import { LANDING_ASSETS } from '../../../constants/landingDesignAssets';

/** App tour — matches linas-landing-04-app-tour.jpg */
export default function LandingAppTour() {
  return (
    <section id="app-tour" className="scroll-mt-24 bg-[#F6F7F6] py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mb-10 max-w-2xl">
          <p className="flex items-center gap-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#06715F]">
            <span className="inline-block h-px w-5 bg-[#06715F]" aria-hidden="true" />
            App tour
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-[#171A19] sm:text-4xl">
            One clean mobile experience.
          </h2>
        </div>

        <div className="overflow-hidden rounded-[2rem] border border-[#E4E8E6] bg-[#EEF1EF] px-6 py-10 sm:px-10 lg:grid lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:items-center lg:gap-10">
          <div className="mx-auto w-full max-w-[18rem]">
            <div className="overflow-hidden rounded-[1.75rem] border border-black/10 bg-black shadow-2xl">
              <img
                src={LANDING_ASSETS.appScreens.ownerCopilot}
                alt="Linas Owner Copilot conversation on mobile"
                className="block w-full"
                width={360}
                height={720}
              />
            </div>
          </div>

          <div className="mt-10 lg:mt-0">
            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-[#06715F]">Chat-first control</p>
            <h3 className="mt-3 text-3xl font-semibold tracking-tight text-[#171A19]">Run Linas from one conversation.</h3>
            <p className="mt-4 max-w-md text-base leading-relaxed text-[#5C6663]">
              Ask a question, request a configuration change, or inspect an issue. Linas turns consequential requests into
              typed review steps—never silent mutations.
            </p>
            <ul className="mt-6 space-y-3 text-sm font-medium text-[#171A19]">
              {[
                'One authenticated owner brain',
                'Workspace-aware and permission-safe',
                'Draft handoff before activation',
              ].map((item) => (
                <li key={item} className="flex items-start gap-2.5">
                  <span className="mt-0.5 text-[#06715F]" aria-hidden="true">
                    ✓
                  </span>
                  {item}
                </li>
              ))}
            </ul>
            <a
              href="#get-app"
              className="mt-8 inline-flex text-sm font-semibold text-[#06715F] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]"
            >
              See the complete app →
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
