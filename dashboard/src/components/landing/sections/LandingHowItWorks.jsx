const STEPS = [
  {
    n: '01',
    title: 'Create your account',
    body: 'Start in chat, authenticate, then resolve the correct workspace.',
  },
  {
    n: '02',
    title: 'Teach Linas your business',
    body: 'Add services, branches, prices, care details, languages, tone, and FAQs.',
  },
  {
    n: '03',
    title: 'Connect verified Meta assets',
    body: 'Approve the required scopes and verify each DM or comment capability.',
  },
  {
    n: '04',
    title: 'Review, activate, and audit',
    body: 'Activate one complete configuration and inspect customer conversations in read-only Live Chat.',
  },
];

/**
 * How it works — matches linas-landing-03-how-it-works.jpg
 * Step copy describes product flow; no website signup CTA.
 * @param {{ onOpenGuest?: () => void }} props
 */
export default function LandingHowItWorks({ onOpenGuest }) {
  return (
    <section id="how-it-works" className="scroll-mt-24 bg-[#0B0D0C] py-20 text-white sm:py-24">
      <div className="mx-auto grid max-w-6xl gap-12 px-4 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-start">
        <div>
          <p className="flex items-center gap-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#54C7AC]">
            <span className="inline-block h-px w-5 bg-[#54C7AC]" aria-hidden="true" />
            How it works
          </p>
          <h2 className="mt-4 max-w-md text-3xl font-semibold tracking-tight sm:text-4xl">
            From account to active replies—without losing control.
          </h2>
          <p className="mt-4 max-w-md text-base leading-relaxed text-white/70">
            Linas guides the owner through a safe, visible sequence. Customer automation only begins after the business,
            connection, and reply configuration are ready.
          </p>
          <button
            type="button"
            onClick={onOpenGuest}
            className="mt-8 rounded-full bg-white px-5 py-3 text-sm font-semibold text-[#171A19] hover:bg-[#F0F3F1] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#54C7AC]"
          >
            Ask the guest guide →
          </button>
        </div>

        <ol className="divide-y divide-white/10">
          {STEPS.map((step) => (
            <li key={step.n} className="grid grid-cols-[3rem_minmax(0,1fr)] gap-4 py-5 first:pt-0 last:pb-0">
              <span className="text-sm font-semibold text-[#54C7AC]">{step.n}</span>
              <div>
                <h3 className="text-lg font-semibold tracking-tight">{step.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-white/65">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
