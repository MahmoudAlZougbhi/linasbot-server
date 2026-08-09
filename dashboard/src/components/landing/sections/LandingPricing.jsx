/** Pricing preview — matches linas-landing-05-pricing.jpg (no invented prices). */
export default function LandingPricing() {
  return (
    <section id="pricing" className="scroll-mt-24 border-y border-[#E4E8E6] bg-white py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] lg:items-end">
          <div>
            <p className="flex items-center gap-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#06715F]">
              <span className="inline-block h-px w-5 bg-[#06715F]" aria-hidden="true" />
              Pricing
            </p>
            <h2 className="mt-3 max-w-xl text-3xl font-semibold tracking-tight text-[#171A19] sm:text-4xl">
              A plan that grows with your conversations.
            </h2>
            <p className="mt-4 max-w-xl text-base leading-relaxed text-[#5C6663]">
              Live amounts, currencies, limits, and purchase routes come from the billing catalog at checkout in the Linas
              AI app — not via website signup.
            </p>
          </div>

          <div className="rounded-2xl border border-[#E4E8E6] bg-[#F6F7F6] p-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-[#E4E8E6] bg-white px-3 py-1 text-xs font-medium text-[#171A19]">
              <span className="h-2 w-2 rounded-full bg-[#06715F]" aria-hidden="true" />
              Catalog integration preview
            </div>
            <p className="mt-5 text-xs font-semibold uppercase tracking-[0.14em] text-[#8A938F]">Channel requirements</p>
            <ul className="mt-3 space-y-2.5 text-sm text-[#171A19]">
              {['Expected usage', 'Team structure', 'Location model', 'Implementation questions'].map((item) => (
                <li key={item} className="flex items-center gap-2">
                  <span className="text-[#06715F]" aria-hidden="true">
                    ✓
                  </span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
