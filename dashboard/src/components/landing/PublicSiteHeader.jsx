import { Link } from 'react-router-dom';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';
import LinasStar from './LinasStar';

const NAV = [
  { href: '/#features', label: 'Features' },
  { href: '/#how-it-works', label: 'How it works' },
  { href: '/#pricing', label: 'Pricing' },
];

/**
 * @param {{ compact?: boolean, onOpenGuest?: () => void }} props
 */
const PublicSiteHeader = ({ compact = false }) => {
  return (
    <header className="sticky top-0 z-30 bg-[#F7F8F5]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <Link
          to={PUBLIC_PATHS.home}
          className="flex items-center gap-2.5 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]"
          aria-label={`${PUBLIC_SITE.productName} home`}
        >
          <LinasStar className="h-6 w-6" />
          <span className="text-[1.05rem] font-semibold tracking-tight text-[#171A19] sm:text-lg">{PUBLIC_SITE.productName}</span>
        </Link>

        {!compact ? (
          <nav className="flex items-center gap-1 text-[0.95rem] font-medium text-[#3A4240]" aria-label="Primary">
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
        ) : null}
      </div>
    </header>
  );
};

export default PublicSiteHeader;
