import { Link } from 'react-router-dom';
import PublicSiteHeader from '../../components/landing/PublicSiteHeader';
import PublicSiteFooter from '../../components/landing/PublicSiteFooter';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';

const Contact = () => {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-sky-50 to-fuchsia-50">
      <PublicSiteHeader compact />
      <main className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <h1 className="font-display text-4xl font-bold text-slate-950">Contact</h1>
        <p className="mt-4 text-lg leading-relaxed text-slate-700">
          For questions about {PUBLIC_SITE.productName}, privacy, Meta connections, or user data deletion, email:
        </p>
        <p className="mt-6">
          <a
            className="inline-flex rounded-xl bg-gradient-to-r from-primary-600 to-secondary-600 px-5 py-3 font-semibold text-white shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary-500"
            href={`mailto:${PUBLIC_SITE.contactEmail}`}
          >
            {PUBLIC_SITE.contactEmail}
          </a>
        </p>
        <p className="mt-8 text-slate-600">
          Data deletion instructions:{' '}
          <a className="font-semibold text-primary-700 underline" href={PUBLIC_PATHS.dataDeletion}>
            {PUBLIC_PATHS.dataDeletion}
          </a>
        </p>
        <p className="mt-3 text-slate-600">
          Privacy Policy:{' '}
          <a className="font-semibold text-primary-700 underline" href={PUBLIC_PATHS.privacy}>
            {PUBLIC_PATHS.privacy}
          </a>
        </p>
        <p className="mt-8 text-sm text-slate-500">
          Phone number and postal address are not published in the current public materials. Use the email above for
          all contact requests.
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

export default Contact;
