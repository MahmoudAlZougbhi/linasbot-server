import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { PLAN_LANDING_COPY } from '../../../constants/landingPlansCopy';
import { PUBLIC_PATHS } from '../../../constants/publicSite';
import LinasStar from '../LinasStar';

/** @param {unknown} value */
function formatPrice(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return null;
  return n % 1 === 0 ? `$${n}` : `$${n.toFixed(2)}`;
}

export default function LandingPricing() {
  const [plans, setPlans] = useState(/** @type {Array<any>} */ ([]));
  const [error, setError] = useState(/** @type {string | null} */ (null));
  const [period, setPeriod] = useState('monthly');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/public/plans', { headers: { Accept: 'application/json' } });
        const body = await res.json();
        if (!res.ok || !body?.success) throw new Error('catalog_unavailable');
        if (!cancelled) {
          setPlans(Array.isArray(body.plans) ? body.plans : []);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setPlans([]);
          setError('Pricing catalog is temporarily unavailable.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section id="pricing" className="scroll-mt-24 bg-[#F7F8F5] py-16 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <p className="text-center text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#06715F]">Simple, flexible plans</p>
        <h2 className="mt-3 text-center text-3xl font-semibold tracking-tight text-[#171A19] sm:text-4xl">Choose the plan that fits your business</h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-[#6B746F]">Start with what you need today. Upgrade whenever your business grows.</p>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <div className="inline-flex rounded-full border border-[#E4E8E6] bg-white p-1">
            {['monthly', 'yearly'].map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setPeriod(key)}
                className={`rounded-full px-4 py-1.5 text-sm font-semibold capitalize ${period === key ? 'bg-[#06715F] text-white' : 'text-[#5C6663]'}`}
              >
                {key}
              </button>
            ))}
          </div>
          <p className="flex items-center gap-1 text-xs text-[#06715F]">
            <LinasStar className="h-3.5 w-3.5" /> Included credits refresh each billing month.
          </p>
        </div>

        {error ? (
          <p className="mt-10 text-center text-sm text-[#B45309]" role="alert">
            {error}
          </p>
        ) : null}

        <div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {plans.map((plan) => {
            const catalog = /** @type {Record<string, { tier: string, blurb: string, included: string[], missing: string | null, recommended?: boolean }>} */ (
              PLAN_LANDING_COPY
            );
            const copy = catalog[String(plan.plan_id)] || { tier: '', blurb: '', included: [], missing: null };
            const recommended = Boolean(copy.recommended);
            const price = formatPrice(plan.price_usd);
            return (
              <article
                key={plan.plan_id}
                className={`flex flex-col rounded-[1.4rem] border bg-white p-5 ${recommended ? 'border-[#06715F] shadow-lg shadow-[#06715F]/10' : 'border-[#E4E8E6]'}`}
              >
                {recommended ? (
                  <p className="mb-2 inline-flex items-center gap-1 self-start rounded-full bg-[#06715F] px-2 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-white">
                    <LinasStar className="h-3 w-3" color="#fff" /> Recommended
                  </p>
                ) : null}
                <p className="text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-[#06715F]">{copy.tier}</p>
                <h3 className="mt-1 text-xl font-semibold text-[#171A19]">{plan.display_name}</h3>
                <p className="mt-2 text-2xl font-semibold text-[#171A19]">
                  {price || '—'}
                  <span className="text-sm font-normal text-[#6B746F]"> / month</span>
                </p>
                <p className="mt-2 text-sm text-[#6B746F]">{copy.blurb}</p>
                <p className="mt-4 rounded-xl bg-[#E8F5F1] px-3 py-2 text-sm font-semibold text-[#06715F]">
                  {Number(plan.included_credits).toLocaleString()} AI credits.
                </p>
                <ul className="mt-4 flex-1 space-y-2 text-sm text-[#171A19]">
                  {copy.included.map((/** @type {string} */ item) => (
                    <li key={item} className="flex gap-2">
                      <span className="text-[#06715F]">✓</span>
                      {item}
                    </li>
                  ))}
                  {copy.missing ? (
                    <li className="flex gap-2 text-[#8A938F]">
                      <span>○</span>
                      {copy.missing}
                    </li>
                  ) : null}
                </ul>
                <a
                  href="/#get-app"
                  className={`mt-5 rounded-full px-4 py-2.5 text-center text-sm font-semibold ${
                    recommended ? 'bg-[#06715F] text-white' : 'border border-[#06715F] text-[#06715F]'
                  }`}
                >
                  Choose {plan.display_name}
                </a>
              </article>
            );
          })}
        </div>

        <div className="mt-8 flex items-start gap-3 rounded-2xl bg-[#E8F4F8] px-5 py-4 text-sm text-[#171A19]">
          <LinasStar className="mt-0.5 h-5 w-5" />
          <p>
            <span className="font-semibold">Smart Answers are free replies. </span>
            When a saved Q&amp;A matches, the reply uses 0 credits. Write it once and it applies in every language you
            select. The more Q&amp;As you save, the more customer replies stay free. They are not a limit on AI
            conversations.
          </p>
        </div>

        <div className="mt-6 flex flex-col items-start justify-between gap-4 rounded-[1.6rem] bg-[#0B3D34] px-6 py-6 text-white sm:flex-row sm:items-center">
          <div>
            <p className="text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-[#54C7AC]">Enterprise</p>
            <p className="mt-1 text-2xl font-semibold">Need more than Max?</p>
            <p className="mt-1 text-sm text-white/70">Custom capacity, onboarding and team access for high-volume organizations.</p>
          </div>
          <div className="text-right">
            <Link to={PUBLIC_PATHS.contact} className="inline-flex rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-[#171A19]">
              Contact Sales
            </Link>
            <p className="mt-2 text-xs text-white/55">Available through a business agreement.</p>
          </div>
        </div>
      </div>
    </section>
  );
}
