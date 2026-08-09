import { Link } from 'react-router-dom';
import { PUBLIC_LANDING_LOCALE_LABELS, PUBLIC_LANDING_LOCALES } from '../../constants/publicLandingLocale';
import { usePublicLandingLocale } from '../../contexts/PublicLandingLocaleContext';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';
import LinasMark from './LinasMark';

/**
 * Marketing header — no Login / Create Account CTAs on the public surface.
 * @param {{ compact?: boolean }} props
 */
const PublicSiteHeader = ({ compact = false }) => {
  const { locale, setLocale } = usePublicLandingLocale();

  return (
    <header className="relative z-20 border-b border-[#E4DCF2]/80 bg-[#F7F4FC]/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <Link
          to={PUBLIC_PATHS.home}
          className="flex items-center gap-3 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF]"
          aria-label={`${PUBLIC_SITE.productName} home`}
        >
          <LinasMark className="h-10 w-10" />
          <span className="font-display text-xl font-bold text-[#2A1B4A] sm:text-2xl">
            {PUBLIC_SITE.productName}
          </span>
        </Link>

        {!compact && (
          <nav className="hidden items-center gap-6 text-sm font-medium text-[#6B5B85] md:flex" aria-label="Primary">
            <a href="/#talk-to-linas" className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded">
              Talk to Linas
            </a>
            <a href="/#how-it-works" className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded">
              How it works
            </a>
            <Link to={PUBLIC_PATHS.features} className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded">
              Features
            </Link>
            <Link to={PUBLIC_PATHS.pricing} className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded">
              Pricing
            </Link>
            <Link to={PUBLIC_PATHS.contact} className="hover:text-[#6D4AFF] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] rounded">
              Contact
            </Link>
          </nav>
        )}

        <div className="flex items-center gap-2 sm:gap-3">
          <div
            className="flex items-center rounded-xl border border-[#E4DCF2] bg-white p-0.5 text-xs font-bold text-[#6B5B85]"
            role="group"
            aria-label="Page language"
          >
            {PUBLIC_LANDING_LOCALES.map((code) => (
              <button
                key={code}
                type="button"
                className={`min-w-[2rem] rounded-lg px-2 py-1 transition ${
                  locale === code
                    ? 'bg-[#6D4AFF] text-white shadow-sm'
                    : 'hover:bg-[#EFE8F8]'
                }`}
                aria-pressed={locale === code}
                onClick={() => setLocale(code)}
              >
                {PUBLIC_LANDING_LOCALE_LABELS[code]}
              </button>
            ))}
          </div>
          <a
            href="/#get-app"
            className="rounded-xl bg-[#6D4AFF] px-3 py-2 text-sm font-semibold text-white shadow-md hover:opacity-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#6D4AFF]"
          >
            Get the app
          </a>
        </div>
      </div>
    </header>
  );
};

export default PublicSiteHeader;
