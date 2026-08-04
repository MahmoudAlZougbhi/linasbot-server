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
          {PUBLIC_SITE.productName} is a business messaging platform that helps companies answer private customer
          messages on Facebook Messenger and Instagram using information approved and controlled by each business.
        </p>
        <p className="mt-4 leading-relaxed text-slate-700">
          The public website is available at{' '}
          <a className="font-semibold text-primary-700 underline" href={PUBLIC_SITE.publicBaseUrl}>
            {PUBLIC_SITE.publicBaseUrl}
          </a>
          . The authenticated dashboard remains available to signed-in company users for content control, Meta
          connection management, and day-to-day operations.
        </p>
        <p className="mt-4 leading-relaxed text-slate-700">
          Scope is private messages only. {PUBLIC_SITE.productName} does not automate Facebook or Instagram comment
          replies, and inbound WhatsApp messages are not processed by the AI.
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
