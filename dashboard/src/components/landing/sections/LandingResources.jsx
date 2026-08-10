import LinasStar from '../LinasStar';

const GUIDES = [
  {
    n: '01',
    title: 'Connect your social media pages',
    body: 'Verified assets, scopes, and capability checks.',
  },
  {
    n: '02',
    title: 'Configure safe customer replies',
    body: 'Business facts, tone, languages, prices, and FAQs.',
  },
  {
    n: '03',
    title: 'Review AI-handled conversations',
    body: 'Search, inspect, and understand the read-only audit.',
  },
];

/** Resources / setup help — matches linas-landing-06-resources.jpg */
export default function LandingResources() {
  return (
    <section id="resources" className="scroll-mt-24 bg-[#F6F7F6] py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <p className="flex items-center justify-center gap-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#06715F]">
            <span className="inline-block h-px w-5 bg-[#06715F]" aria-hidden="true" />
            Learn Linas
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-[#171A19] sm:text-4xl">
            Setup help when you need it.
          </h2>
          <p className="mt-4 text-base leading-relaxed text-[#5C6663]">
            Start with a guided walkthrough, then use focused guides for configuration, connection, safety, and day-to-day
            audit.
          </p>
        </div>

        <div className="mt-12 grid gap-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <article className="overflow-hidden rounded-[1.5rem] border border-[#E4E8E6] bg-white">
            <div className="relative flex h-56 items-center justify-center bg-[#0B3D34]">
              <div className="absolute inset-0 opacity-40" aria-hidden="true">
                <div className="absolute left-1/2 top-1/2 h-40 w-40 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#54C7AC]/40" />
                <div className="absolute left-1/2 top-1/2 h-56 w-56 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#54C7AC]/25" />
                <div className="absolute left-1/2 top-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#54C7AC]/15" />
              </div>
              <LinasStar className="relative h-12 w-12" color="#FFFFFF" />
              <span className="absolute bottom-4 right-4 flex h-11 w-11 items-center justify-center rounded-full bg-white text-[#06715F]">
                ▶
              </span>
            </div>
            <div className="p-6">
              <p className="text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-[#06715F]">Guided overview</p>
              <h3 className="mt-2 text-xl font-semibold text-[#171A19]">See how Linas AI works</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#5C6663]">
                From owner chat to approved customer replies and read-only audit.
              </p>
            </div>
          </article>

          <div className="flex flex-col gap-3">
            {GUIDES.map((guide) => (
              <a
                key={guide.n}
                href="#contact"
                className="flex items-center gap-4 rounded-2xl border border-[#E4E8E6] bg-white px-5 py-4 transition hover:border-[#06715F]/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]"
              >
                <span className="text-sm font-semibold text-[#06715F]">{guide.n}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-base font-semibold text-[#171A19]">{guide.title}</span>
                  <span className="mt-0.5 block text-sm text-[#5C6663]">{guide.body}</span>
                </span>
                <span className="text-[#8A938F]" aria-hidden="true">
                  →
                </span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
