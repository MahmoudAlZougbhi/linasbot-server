import { Link } from 'react-router-dom';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';

const PublicSiteFooter = () => {
  const year = new Date().getFullYear();
  return (
    <footer className="relative z-10 border-t border-slate-200/80 bg-white/80">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:px-6 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="font-display text-lg font-bold text-slate-900">{PUBLIC_SITE.productName}</p>
          <p className="mt-2 max-w-sm text-sm text-slate-600">
            AI messaging for Facebook Messenger and Instagram private messages.
          </p>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm text-slate-700 sm:grid-cols-3">
          <Link className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded" to={PUBLIC_PATHS.about}>
            About
          </Link>
          <a className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded" href="/#pricing">
            Pricing
          </a>
          <Link className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded" to={PUBLIC_PATHS.contact}>
            Contact
          </Link>
          <a className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded" href={PUBLIC_PATHS.privacy}>
            Privacy Policy
          </a>
          <a className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded" href={PUBLIC_PATHS.terms}>
            Terms of Service
          </a>
          <a className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded" href={PUBLIC_PATHS.dataDeletion}>
            Data Deletion
          </a>
          <Link className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded" to={PUBLIC_PATHS.login}>
            Log in
          </Link>
        </nav>
      </div>
      <div className="border-t border-slate-200/80 py-4 text-center text-xs text-slate-500">
        © {year} {PUBLIC_SITE.productName}. Contact:{' '}
        <a className="underline hover:text-slate-700" href={`mailto:${PUBLIC_SITE.contactEmail}`}>
          {PUBLIC_SITE.contactEmail}
        </a>
      </div>
    </footer>
  );
};

export default PublicSiteFooter;
