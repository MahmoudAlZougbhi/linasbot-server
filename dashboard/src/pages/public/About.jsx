import { Link } from 'react-router-dom';
import PublicSiteHeader from '../../components/landing/PublicSiteHeader';
import PublicSiteFooter from '../../components/landing/PublicSiteFooter';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';

const About = () => {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-sky-50 to-fuchsia-50">
      <PublicSiteHeader compact />
      <main className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <h1 className="font-display text-4xl font-bold text-slate-950">About {PUBLIC_SITE.productName}</h1>

        <p className="mt-4 text-lg leading-relaxed text-slate-700">
          {PUBLIC_SITE.productName} is a multi-tenant business customer-support AI. Each company gets its
          own workspace: customers are answered from knowledge that business approves in AI Setup—not
          from a shared general chatbot, and not as a consumer assistant for personal use.
        </p>

        <p className="mt-4 leading-relaxed text-slate-700">
          It is built for business owners and teams who want helpful, on-brand replies when people
          message or comment on the channels they connect. Typical uses include services, pricing,
          hours, policies, and directing a customer to the business’s preferred contact path when a
          human or booking step is needed.
        </p>

        <p className="mt-4 leading-relaxed text-slate-700">
          <span className="font-semibold text-slate-900">AI Setup</span> is where each tenant stores
          and publishes the facts Linas uses—services, FAQs, tone, and related business knowledge.
          Customer replies draw from that approved material so answers stay under the company’s
          control, with publish and rollback available when content changes.
        </p>

        <p className="mt-4 leading-relaxed text-slate-700">
          <span className="font-semibold text-slate-900">Owner chat</span> is for the business side:
          setup, control, and day-to-day visibility in a chat-first Copilot. Customer channels are
          separate—Linas replies only on accounts the business has authorized, to people who
          voluntarily message or comment there.
        </p>

        <p className="mt-4 leading-relaxed text-slate-700">
          Supported messaging channels include{' '}
          <span className="font-semibold text-slate-900">Facebook</span>,{' '}
          <span className="font-semibold text-slate-900">Instagram</span>,{' '}
          <span className="font-semibold text-slate-900">WhatsApp</span>, and{' '}
          <span className="font-semibold text-slate-900">TikTok</span>. Facebook and Instagram are
          the primary live Meta connections today. WhatsApp and TikTok inbound AI run when that
          business connects those channels through official platform APIs; until then, WhatsApp may
          still be used as an outbound handoff destination (for example a booking or human-agent
          link) where the business configures it.
        </p>

        <p className="mt-4 leading-relaxed text-slate-700">
          Scope is messaging conversations—customer DMs and, where enabled, comments—not automatic
          publishing of posts, Stories, Reels, or videos. Creative publishing is separate and only
          happens when a business user explicitly confirms it.
        </p>

        <p className="mt-4 leading-relaxed text-slate-700">
          The public website at{' '}
          <a className="font-semibold text-primary-700 underline" href={PUBLIC_SITE.publicBaseUrl}>
            {PUBLIC_SITE.publicBaseUrl}
          </a>{' '}
          is marketing plus a short guest chat. Signed-in company users do day-to-day work in the
          Linas AI app and authenticated dashboard: AI Setup, channel connections, and operations.
        </p>

        <p className="mt-6 text-slate-700">
          Contact:{' '}
          <a className="font-semibold text-primary-700 underline" href={`mailto:${PUBLIC_SITE.contactEmail}`}>
            {PUBLIC_SITE.contactEmail}
          </a>
        </p>
        <p className="mt-8">
          <Link to={PUBLIC_PATHS.home} className="font-semibold text-primary-700 underline">
            Back to home
          </Link>
        </p>
      </main>
      <PublicSiteFooter />
    </div>
  );
};

export default About;
