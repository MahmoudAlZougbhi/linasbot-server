import { Link } from 'react-router-dom';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';

const PublicSiteFooter = () => {
  const year = new Date().getFullYear();
  return (
    <footer className="relative z-10 border-t border-[#243248] bg-[#0C1424]">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:px-6 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="font-display text-lg font-bold text-[#E8EEF8]">{PUBLIC_SITE.productName}</p>
          <p className="mt-2 max-w-sm text-sm text-[#8B9BB8]">
            AI messaging for Facebook Messenger and Instagram private messages.
          </p>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm text-[#8B9BB8] sm:grid-cols-3">
          <Link className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded" to={PUBLIC_PATHS.about}>
            About
          </Link>
          <a className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded" href="/#pricing">
            Pricing
          </a>
          <Link className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded" to={PUBLIC_PATHS.contact}>
            Contact
          </Link>
          <a className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded" href={PUBLIC_PATHS.privacy}>
            Privacy Policy
          </a>
          <a className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded" href={PUBLIC_PATHS.terms}>
            Terms of Service
          </a>
          <a className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded" href={PUBLIC_PATHS.dataDeletion}>
            Data Deletion
          </a>
          <Link className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded" to={PUBLIC_PATHS.login}>
            Log in
          </Link>
        </nav>
      </div>
      <div className="border-t border-[#243248] py-4 text-center text-xs text-[#5E6E8A]">
        © {year} {PUBLIC_SITE.productName}. Contact:{' '}
        <a className="text-[#3B8EF0] underline" href={`mailto:${PUBLIC_SITE.contactEmail}`}>
          {PUBLIC_SITE.contactEmail}
        </a>
      </div>
    </footer>
  );
};

export default PublicSiteFooter;
