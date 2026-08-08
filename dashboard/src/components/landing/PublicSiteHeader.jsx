import { Link } from 'react-router-dom';
import { SparklesIcon } from '@heroicons/react/24/outline';
import { PUBLIC_LANDING_LOCALE_LABELS, PUBLIC_LANDING_LOCALES } from '../../constants/publicLandingLocale';
import { usePublicLandingLocale } from '../../contexts/PublicLandingLocaleContext';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';

/**
 * @param {{ compact?: boolean }} props
 */
const PublicSiteHeader = ({ compact = false }) => {
  const { locale, setLocale } = usePublicLandingLocale();

  return (
    <header className="relative z-20 border-b border-white/40 bg-white/70 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <Link
          to={PUBLIC_PATHS.home}
          className="flex items-center gap-3 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          aria-label={`${PUBLIC_SITE.productName} home`}
        >
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-secondary-500 shadow-lg">
            <SparklesIcon className="h-5 w-5 text-white" aria-hidden="true" />
          </span>
          <span className="font-display text-xl font-bold text-slate-900 sm:text-2xl">
            {PUBLIC_SITE.productName}
          </span>
        </Link>

        {!compact && (
          <nav className="hidden items-center gap-6 text-sm font-medium text-slate-700 md:flex" aria-label="Primary">
            <a href="#how-it-works" className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded">
              How it works
            </a>
            <a href="#features" className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded">
              Features
            </a>
            <a href="#pricing" className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded">
              Pricing
            </a>
            <a href="#faq" className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded">
              FAQ
            </a>
            <Link to={PUBLIC_PATHS.contact} className="hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded">
              Contact
            </Link>
          </nav>
        )}

        <div className="flex items-center gap-2 sm:gap-3">
          <div
            className="flex items-center rounded-xl border border-slate-200/80 bg-white/80 p-0.5 text-xs font-bold text-slate-600"
            role="group"
            aria-label="Page language"
          >
            {PUBLIC_LANDING_LOCALES.map((code) => (
              <button
                key={code}
                type="button"
                className={`min-w-[2rem] rounded-lg px-2 py-1 transition ${
                  locale === code
                    ? 'bg-gradient-to-r from-primary-600 to-secondary-600 text-white shadow-sm'
                    : 'hover:bg-slate-100'
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
            className="rounded-xl px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-white/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          >
            Log in
          </Link>
          <Link
            to={PUBLIC_PATHS.register}
            className="rounded-xl bg-gradient-to-r from-primary-600 to-secondary-600 px-3 py-2 text-sm font-semibold text-white shadow-md hover:opacity-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary-500"
          >
            Create Account
          </Link>
        </div>
      </div>
    </header>
  );
};

export default PublicSiteHeader;
