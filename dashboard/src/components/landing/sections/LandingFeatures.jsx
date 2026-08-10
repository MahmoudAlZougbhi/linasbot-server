const FEATURES = [
  {
    title: 'One Owner Copilot',
    body: 'Ask, review, and manage from one familiar chat-first workspace. Linas proposes changes; you stay in control.',
    dark: true,
  },
  {
    title: 'DMs and comments, covered',
    body: 'Handle social media DMs and comments with approved business knowledge.',
    dark: false,
  },
  {
    title: 'Reply configuration',
    body: 'Set services, prices, branches, tone, languages, FAQs, and safe reply boundaries in one place.',
    dark: false,
  },
  {
    title: 'Draft → review → active',
    body: 'Changes remain drafts until an authorized owner reviews and activates the complete configuration.',
    dark: false,
  },
  {
    title: 'Verified Meta connections',
    body: 'Connection health, permissions, and channel capability states come from the provider and backend.',
    dark: false,
  },
  {
    title: 'Read-only Live Chat audit',
    body: 'See what customers asked, what Linas answered, and what happened—without shadow reply controls.',
    dark: true,
  },
  {
    title: 'Roles, usage, and control',
    body: 'Give each teammate the right access and keep usage, limits, billing, and activity visible.',
    dark: false,
  },
  {
    title: 'Built for multilingual teams',
    body: 'The product supports English and Arabic reply configuration, with ready mobile interfaces and explicit language control.',
    dark: false,
  },
];

/** Features grid — matches linas-landing-02-features.jpg */
export default function LandingFeatures() {
  return (
    <section id="features" className="scroll-mt-24 bg-[#F6F7F6] py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <p className="flex items-center justify-center gap-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#06715F]">
            <span className="inline-block h-px w-5 bg-[#06715F]" aria-hidden="true" />
            Everything stays connected
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-[#171A19] sm:text-4xl">
            Powerful AI. Clear business control.
          </h2>
          <p className="mt-4 text-base leading-relaxed text-[#5C6663]">
            From the first customer question to the final audit trail, every part of Linas AI follows one approved
            configuration and one shared backend.
          </p>
        </div>

        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature) => (
            <article
              key={feature.title}
              className={`rounded-2xl border p-5 ${
                feature.dark
                  ? 'border-[#0B3D34] bg-[#0B3D34] text-white'
                  : 'border-[#E4E8E6] bg-white text-[#171A19]'
              }`}
            >
              <span
                className={`mb-4 inline-flex h-9 w-9 items-center justify-center rounded-xl text-lg ${
                  feature.dark ? 'bg-white/10 text-[#54C7AC]' : 'bg-[#E8F5F1] text-[#06715F]'
                }`}
                aria-hidden="true"
              >
                ✦
              </span>
              <h3 className="text-lg font-semibold tracking-tight">{feature.title}</h3>
              <p className={`mt-2 text-sm leading-relaxed ${feature.dark ? 'text-white/75' : 'text-[#5C6663]'}`}>
                {feature.body}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
