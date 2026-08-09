import { Link } from 'react-router-dom';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';
import LinasStar from './LinasStar';
import StoreBadges from './StoreBadges';

const PublicSiteFooter = () => {
  const year = new Date().getFullYear();
  return (
    <footer className="relative z-10 bg-[#0B0D0C] text-[#C9D0CD]">
      <div className="mx-auto flex max-w-6xl flex-col gap-10 px-4 py-12 sm:px-6 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <LinasStar className="h-5 w-5" color="#54C7AC" />
            <p className="text-lg font-semibold text-white">{PUBLIC_SITE.productName}</p>
          </div>
          <p className="mt-3 max-w-sm text-sm leading-relaxed text-[#9AA39F]">
            AI messaging for Facebook & Instagram DMs and comments — operated from the Linas AI app.
          </p>
          <div className="mt-5">
            <StoreBadges compact />
          </div>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-x-10 gap-y-2 text-sm sm:grid-cols-3">
          <Link className="rounded hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#54C7AC]" to={PUBLIC_PATHS.about}>
            About
          </Link>
          <a className="rounded hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#54C7AC]" href="/#pricing">
            Pricing
          </a>
          <Link className="rounded hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#54C7AC]" to={PUBLIC_PATHS.contact}>
            Contact
          </Link>
          <a className="rounded hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#54C7AC]" href={PUBLIC_PATHS.privacy}>
            Privacy Policy
          </a>
          <a className="rounded hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#54C7AC]" href={PUBLIC_PATHS.terms}>
            Terms of Service
          </a>
          <a className="rounded hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#54C7AC]" href={PUBLIC_PATHS.dataDeletion}>
            Data Deletion
          </a>
          <a className="rounded hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#54C7AC]" href="/#talk-to-linas">
            Talk to Linas
          </a>
        </nav>
      </div>
      <div className="border-t border-white/10 py-4 text-center text-xs text-[#7A8480]">
        © {year} {PUBLIC_SITE.productName}. Contact:{' '}
        <a className="text-[#54C7AC] underline" href={`mailto:${PUBLIC_SITE.contactEmail}`}>
          {PUBLIC_SITE.contactEmail}
        </a>
      </div>
    </footer>
  );
};

export default PublicSiteFooter;
