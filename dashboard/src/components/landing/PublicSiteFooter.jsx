import { Link } from 'react-router-dom';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';
import StoreBadges from './StoreBadges';

const PublicSiteFooter = () => {
  const year = new Date().getFullYear();
  return (
    <footer className="relative z-10 border-t border-[#E4DCF2] bg-[#F7F4FC]">
      <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="font-display text-lg font-bold text-[#2A1B4A]">{PUBLIC_SITE.productName}</p>
          <p className="mt-2 max-w-sm text-sm text-[#6B5B85]">
            Business AI for Messenger & Instagram — download the app to subscribe and operate.
          </p>
          <div className="mt-4">
            <StoreBadges compact />
          </div>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm text-[#6B5B85] sm:grid-cols-3">
          <Link className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded" to={PUBLIC_PATHS.about}>
            About
          </Link>
          <a className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded" href="/#pricing">
            Pricing
          </a>
          <Link className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded" to={PUBLIC_PATHS.contact}>
            Contact
          </Link>
          <a className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded" href={PUBLIC_PATHS.privacy}>
            Privacy Policy
          </a>
          <a className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded" href={PUBLIC_PATHS.terms}>
            Terms of Service
          </a>
          <a className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded" href={PUBLIC_PATHS.dataDeletion}>
            Data Deletion
          </a>
          <a className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded" href="/#talk-to-linas">
            Talk to Linas
          </a>
        </nav>
      </div>
      <div className="border-t border-[#E4DCF2] py-4 text-center text-xs text-[#9B8BB5]">
        © {year} {PUBLIC_SITE.productName}. Contact:{' '}
        <a className="text-[#6D4AFF] underline" href={`mailto:${PUBLIC_SITE.contactEmail}`}>
          {PUBLIC_SITE.contactEmail}
        </a>
      </div>
    </footer>
  );
};

export default PublicSiteFooter;
