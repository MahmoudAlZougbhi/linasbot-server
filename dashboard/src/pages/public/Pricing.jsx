import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import PublicSiteHeader from '../../components/landing/PublicSiteHeader';
import PublicSiteFooter from '../../components/landing/PublicSiteFooter';
import LinasMark from '../../components/landing/LinasMark';
import { PUBLIC_PATHS } from '../../constants/publicSite';

/**
 * Pricing page — loads canonical five-plan catalog from /api/public/plans.
 * Never invents prices client-side.
 */
export default function Pricing() {
  const [plans, setPlans] = useState(/** @type {Array<any>} */ ([]));
  const [error, setError] = useState(/** @type {string | null} */ (null));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/public/plans', { headers: { Accept: 'application/json' } });
        const body = await res.json();
        if (!res.ok || !body?.success) {
          throw new Error('catalog_unavailable');
        }
        if (!cancelled) {
          setPlans(Array.isArray(body.plans) ? body.plans : []);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setPlans([]);
          setError('Pricing catalog is temporarily unavailable. Please try again later.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-[#0C1424] text-[#E8EEF8]">
      <PublicSiteHeader />
      <main className="mx-auto max-w-5xl px-6 py-16">
        <div className="mb-8 flex items-center gap-4">
          <LinasMark className="h-12 w-12" />
          <div>
            <h1 className="font-display text-4xl font-semibold tracking-tight">Pricing</h1>
            <p className="mt-1 max-w-2xl text-[#8B9BB8]">
              Manage your business AI from the Linas AI mobile app. Subscriptions and credits are
              enforced by the Linas API — not by the website.
            </p>
          </div>
        </div>
        {loading && <p className="text-[#8B9BB8]">Loading plans…</p>}
        {error && (
          <p className="rounded-lg border border-red-500/40 bg-red-950/40 p-4 text-red-200" role="alert">
            {error}
          </p>
        )}
        {!loading && !error && (
          <div className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {plans.map((plan) => (
              <article
                key={plan.plan_id}
                className="rounded-2xl border border-[#243248] bg-[#162033]/70 p-6"
              >
                <h2 className="text-xl font-semibold text-[#E8EEF8]">{plan.display_name}</h2>
                <p className="mt-2 text-3xl font-bold text-[#3B8EF0]">
                  {Number(plan.price_usd) % 1 === 0 ? `$${plan.price_usd}` : `$${Number(plan.price_usd).toFixed(2)}`}
                  <span className="text-base font-normal text-[#8B9BB8]">/mo</span>
                </p>
                <ul className="mt-3 space-y-1 text-sm text-[#8B9BB8]">
                  <li>{plan.included_credits.toLocaleString()} included credits / period</li>
                  <li>FAQ capacity: {plan.faq_capacity}</li>
                  <li>
                    Additional seats:{' '}
                    {plan.additional_seats_unlimited ? 'Unlimited' : plan.additional_seats}
                  </li>
                  <li>Comments: {plan.comment_automation ? 'Enabled' : 'Disabled'}</li>
                </ul>
              </article>
            ))}
          </div>
        )}
        <p className="mt-10 text-[#8B9BB8]">
          Download the iOS/Android app to subscribe. The public website is marketing-only — account
          and workspace management live in the Linas AI app.
        </p>
        <Link to={PUBLIC_PATHS.contact} className="mt-4 inline-block text-[#5EE0B5] underline">
          Contact support
        </Link>
      </main>
      <PublicSiteFooter />
    </div>
  );
}
