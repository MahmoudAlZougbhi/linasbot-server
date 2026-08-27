import { Link } from 'react-router-dom';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';
import HeaderDownloadMenu from './HeaderDownloadMenu';
import LinasStar from './LinasStar';

const NAV = [
  { href: '/#features', label: 'Features' },
  { href: '/#how-it-works', label: 'Explore the app' },
  { href: '/#pricing', label: 'Pricing' },
];

/**
 * @param {{ compact?: boolean, onOpenGuest?: () => void }} props
 */
const PublicSiteHeader = ({ compact = false }) => {
  return (
    <header className="sticky top-0 z-50 bg-[#F7F8F5]/85 backdrop-blur-md">
      <div className="mx-auto max-w-6xl px-4 py-3 sm:px-6">
        <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-full bg-white px-3 py-1.5 shadow-[0_10px_32px_rgba(23,26,25,0.07)] ring-1 ring-black/[0.04] sm:px-5 sm:py-2">
          <Link
            to={PUBLIC_PATHS.home}
            className="flex items-center gap-2.5 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]"
            aria-label={`${PUBLIC_SITE.productName} home`}
          >
            <LinasStar className="h-6 w-6" />
            <span className="text-[1.05rem] font-semibold tracking-tight text-[#171A19] sm:text-lg">
              {PUBLIC_SITE.productName}
            </span>
          </Link>

          {!compact ? (
            <nav className="hidden justify-center text-[0.95rem] font-medium text-[#3A4240] md:flex" aria-label="Primary">
              {NAV.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  className="rounded-full px-3 py-1.5 hover:bg-[#E8ECEA] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]"
                >
                  {item.label}
                </a>
              ))}
            </nav>
          ) : (
            <div />
          )}

          {!compact ? <HeaderDownloadMenu /> : <div />}
        </div>
      </div>
    </header>
  );
};

export default PublicSiteHeader;
