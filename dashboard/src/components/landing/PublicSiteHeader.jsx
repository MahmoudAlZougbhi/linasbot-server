import { Link } from 'react-router-dom';
import { PUBLIC_LANDING_LOCALE_LABELS, PUBLIC_LANDING_LOCALES } from '../../constants/publicLandingLocale';
import { usePublicLandingLocale } from '../../contexts/PublicLandingLocaleContext';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';
import LinasMark from './LinasMark';

/**
 * @param {{ compact?: boolean }} props
 */
const PublicSiteHeader = ({ compact = false }) => {
  const { locale, setLocale } = usePublicLandingLocale();

  return (
    <header className="relative z-20 border-b border-[#243248] bg-[#0C1424]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <Link
          to={PUBLIC_PATHS.home}
          className="flex items-center gap-3 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0]"
          aria-label={`${PUBLIC_SITE.productName} home`}
        >
          <LinasMark className="h-10 w-10" />
          <span className="font-display text-xl font-bold text-[#E8EEF8] sm:text-2xl">
            {PUBLIC_SITE.productName}
          </span>
        </Link>

        {!compact && (
          <nav className="hidden items-center gap-6 text-sm font-medium text-[#8B9BB8] md:flex" aria-label="Primary">
            <a href="#how-it-works" className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded">
              How it works
            </a>
            <Link to={PUBLIC_PATHS.features} className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded">
              Features
            </Link>
            <Link to={PUBLIC_PATHS.pricing} className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded">
              Pricing
            </Link>
            <a href="#faq" className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded">
              FAQ
            </a>
            <Link to={PUBLIC_PATHS.contact} className="hover:text-[#3B8EF0] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0] rounded">
              Contact
            </Link>
          </nav>
        )}

        <div className="flex items-center gap-2 sm:gap-3">
          <div
            className="flex items-center rounded-xl border border-[#243248] bg-[#162033] p-0.5 text-xs font-bold text-[#8B9BB8]"
            role="group"
            aria-label="Page language"
          >
            {PUBLIC_LANDING_LOCALES.map((code) => (
              <button
                key={code}
                type="button"
                className={`min-w-[2rem] rounded-lg px-2 py-1 transition ${
                  locale === code
                    ? 'bg-[#3B8EF0] text-[#0C1424] shadow-sm'
                    : 'hover:bg-[#1C2A42]'
                }`}
                aria-pressed={locale === code}
                onClick={() => setLocale(code)}
              >
                {PUBLIC_LANDING_LOCALE_LABELS[code]}
              </button>
            ))}
          </div>
          <Link
            to={PUBLIC_PATHS.login}
            className="rounded-xl px-3 py-2 text-sm font-semibold text-[#E8EEF8] hover:bg-[#162033] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3B8EF0]"
          >
            Log in
          </Link>
          <Link
            to={PUBLIC_PATHS.register}
            className="rounded-xl bg-[#3B8EF0] px-3 py-2 text-sm font-semibold text-[#0C1424] shadow-md hover:opacity-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#3B8EF0] focus-visible:ring-offset-[#0C1424]"
          >
            Create Account
          </Link>
        </div>
      </div>
    </header>
  );
};

export default PublicSiteHeader;
