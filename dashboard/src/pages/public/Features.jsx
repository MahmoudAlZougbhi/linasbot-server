import PublicSiteHeader from '../../components/landing/PublicSiteHeader';
import PublicSiteFooter from '../../components/landing/PublicSiteFooter';

const FEATURES = [
  'ChatGPT-style Linas AI owner assistant',
  'Content Management with publish and rollback',
  'Facebook / Instagram DM automation',
  'Creative Studio (Pro+)',
  'Scheduling (Pro+)',
  'Usage credits and subscription entitlements',
  'Role-aware team users',
];

export default function Features() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <PublicSiteHeader />
      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-4xl font-semibold">Features</h1>
        <p className="mt-3 text-slate-300">
          Visible features in the product are functional. Integrations show Available, Connected,
          Needs Permission, or Coming Later — never fake toggles.
        </p>
        <ul className="mt-8 space-y-3">
          {FEATURES.map((item) => (
            <li key={item} className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
              {item}
            </li>
          ))}
        </ul>
      </main>
      <PublicSiteFooter />
    </div>
  );
}
