import { Link } from 'react-router-dom';
import { PUBLIC_LANDING_LOCALE_LABELS, PUBLIC_LANDING_LOCALES } from '../../constants/publicLandingLocale';
import { usePublicLandingLocale } from '../../contexts/PublicLandingLocaleContext';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';
import LinasStar from './LinasStar';

const NAV = [
  { href: '/#features', label: 'Features' },
  { href: '/#how-it-works', label: 'How it works' },
  { href: '/#app-tour', label: 'App tour' },
  { href: '/#pricing', label: 'Pricing' },
  { href: '/#resources', label: 'Resources' },
];

/**
 * Marketing header — no Login / Create Account CTAs on the public surface.
 * Matches LINAS_AI_LANDING_PAGE_DESIGN nav composition.
 * @param {{ compact?: boolean, onOpenGuest?: () => void }} props
 */
const PublicSiteHeader = ({ compact = false, onOpenGuest }) => {
  const { locale, setLocale } = usePublicLandingLocale();

  return (
    <header className="sticky top-0 z-30 border-b border-[#E4E8E6]/80 bg-[#F6F7F6]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
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

        {!compact && (
          <nav className="hidden items-center gap-1 text-[0.92rem] font-medium text-[#3A4240] lg:flex" aria-label="Primary">
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
        )}

        <div className="flex items-center gap-2 sm:gap-3">
          <div
            className="flex items-center rounded-full border border-[#E4E8E6] bg-white p-0.5 text-[0.7rem] font-bold text-[#5C6663]"
            role="group"
            aria-label="Page language"
          >
            {PUBLIC_LANDING_LOCALES.map((code) => (
              <button
                key={code}
                type="button"
                className={`min-w-[1.85rem] rounded-full px-2 py-1 transition ${
                  locale === code ? 'bg-[#06715F] text-white' : 'hover:bg-[#F0F3F1]'
                }`}
                aria-pressed={locale === code}
                onClick={() => setLocale(code)}
              >
                {PUBLIC_LANDING_LOCALE_LABELS[code]}
              </button>
            ))}
          </div>
          {onOpenGuest ? (
            <button
              type="button"
              onClick={onOpenGuest}
              className="hidden rounded-full px-3 py-2 text-sm font-semibold text-[#171A19] hover:bg-[#E8ECEA] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F] sm:inline-flex"
            >
              Try Guest AI
            </button>
          ) : (
            <a
              href="/#talk-to-linas"
              className="hidden rounded-full px-3 py-2 text-sm font-semibold text-[#171A19] hover:bg-[#E8ECEA] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F] sm:inline-flex"
            >
              Try Guest AI
            </a>
          )}
          <a
            href="/#get-app"
            className="rounded-full bg-[#171A19] px-3.5 py-2 text-sm font-semibold text-white hover:bg-black focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#06715F]"
          >
            Download app
          </a>
        </div>
      </div>
    </header>
  );
};

export default PublicSiteHeader;
