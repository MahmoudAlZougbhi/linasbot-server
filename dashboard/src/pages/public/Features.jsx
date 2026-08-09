import PublicSiteHeader from '../../components/landing/PublicSiteHeader';
import PublicSiteFooter from '../../components/landing/PublicSiteFooter';
import LinasMark from '../../components/landing/LinasMark';

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
    <div className="min-h-screen bg-[#0C1424] text-[#E8EEF8]">
      <PublicSiteHeader />
      <main className="mx-auto max-w-3xl px-6 py-16">
        <div className="mb-8 flex items-center gap-4">
          <LinasMark className="h-12 w-12" />
          <div>
            <h1 className="font-display text-4xl font-semibold tracking-tight">Features</h1>
            <p className="mt-1 text-[#8B9BB8]">App-first business AI — calm, truthful, ChatGPT-like.</p>
          </div>
        </div>
        <p className="text-[#8B9BB8]">
          Visible features in the product are functional. Integrations show Available, Connected,
          Needs Permission, or Coming Later — never fake toggles.
        </p>
        <ul className="mt-8 space-y-3">
          {FEATURES.map((item) => (
            <li
              key={item}
              className="rounded-xl border border-[#243248] bg-[#162033]/80 px-4 py-3 text-[#E8EEF8]"
            >
              {item}
            </li>
          ))}
        </ul>
      </main>
      <PublicSiteFooter />
    </div>
  );
}
