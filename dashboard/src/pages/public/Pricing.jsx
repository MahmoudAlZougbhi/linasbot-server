import { Link } from 'react-router-dom';
import PublicSiteHeader from '../../components/landing/PublicSiteHeader';
import PublicSiteFooter from '../../components/landing/PublicSiteFooter';
import { PUBLIC_PATHS } from '../../constants/publicSite';

const PLANS = [
  {
    id: 'starter',
    price: '$24.99',
    blurb: 'Owner assistant, Content Management, DM automation, basic integrations.',
  },
  {
    id: 'growth',
    price: '$59',
    blurb: 'Everything in Starter plus comment automation and higher usage.',
  },
  {
    id: 'pro',
    price: '$109',
    blurb: 'Creative Studio, scheduling, images/video where supported, higher usage.',
  },
  {
    id: 'max',
    price: '$250',
    blurb: 'All available features and highest included usage.',
  },
];

export default function Pricing() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <PublicSiteHeader />
      <main className="mx-auto max-w-5xl px-6 py-16">
        <h1 className="text-4xl font-semibold tracking-tight">Pricing</h1>
        <p className="mt-3 max-w-2xl text-slate-300">
          Manage your business AI from the Linas AI mobile app. Subscriptions and credits are
          enforced by the Linas API — not by the website.
        </p>
        <div className="mt-10 grid gap-6 md:grid-cols-2">
          {PLANS.map((plan) => (
            <article key={plan.id} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
              <h2 className="text-xl font-semibold capitalize">{plan.id}</h2>
              <p className="mt-2 text-3xl font-bold">{plan.price}<span className="text-base font-normal text-slate-400">/mo</span></p>
              <p className="mt-3 text-slate-300">{plan.blurb}</p>
            </article>
          ))}
        </div>
        <p className="mt-10 text-slate-400">
          Download the iOS/Android app to subscribe. Website login remains available for operators
          and technical admin only.
        </p>
        <Link to={PUBLIC_PATHS.contact} className="mt-4 inline-block text-emerald-400 underline">
          Contact support
        </Link>
      </main>
      <PublicSiteFooter />
    </div>
  );
}
