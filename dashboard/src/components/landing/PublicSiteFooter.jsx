import { Link } from 'react-router-dom';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';
import { CHANNELS } from './ChannelIcons';
import FooterCloseBurst from './FooterCloseBurst';
import LinasStar from './LinasStar';
import StoreBadges from './StoreBadges';
import './footerClose.css';

const linkClass = 'transition-colors hover:text-white';

/**
 * @param {{ onOpenGuest?: () => void }} props
 */
const PublicSiteFooter = ({ onOpenGuest }) => {
  const year = new Date().getFullYear();
  return (
    <footer className="lp-close relative z-10 overflow-hidden">
      <span className="lp-close-grain" aria-hidden="true" />
      <LinasStar className="pointer-events-none absolute -left-10 bottom-24 h-48 w-48 opacity-[0.07]" color="#3dffc2" />
      <LinasStar className="pointer-events-none absolute -right-6 top-[46%] h-64 w-64 opacity-[0.09]" color="#3dffc2" />

      <div className="relative mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1.15fr)_minmax(0,0.85fr)] lg:gap-8 lg:py-20">
        <div>
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.22em] text-[#7dffe0]">Ready when you are</p>
          <h2 className="mt-4 max-w-md text-[2.15rem] font-semibold leading-[1.12] tracking-tight text-white sm:text-[2.55rem]">
            Teach Linas once.
            <br />
            Every channel knows
            <br />
            what to say.
          </h2>
          <p className="mt-5 max-w-md text-[0.95rem] leading-relaxed text-[#B7C7C1]">
            Linas answers customers, gathers order and appointment details, and sends every request to your app—ready for
            you or your team.
          </p>
        </div>
        <FooterCloseBurst />
        <div className="lg:justify-self-end">
          <StoreBadges compact variant="close" />
          <p className="mt-3 text-center text-[0.72rem] text-[#6E807A] lg:text-left">Available on iOS and Android</p>
        </div>
      </div>

      <div className="lp-close-rule" aria-hidden="true">
        <span className="lp-close-rule-beam" />
        <span className="lp-close-rule-core" />
      </div>

      <div className="relative mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[minmax(0,1.2fr)_repeat(4,minmax(0,0.68fr))]">
        <div>
          <div className="flex items-center gap-2.5">
            <LinasStar className="h-6 w-6" color="#3dffc2" />
            <p className="text-xl font-semibold text-white">{PUBLIC_SITE.productName}</p>
          </div>
          <p className="mt-3 max-w-xs text-sm leading-relaxed text-[#7D8F89]">One AI for every customer conversation.</p>
        </div>
        <nav aria-label="Product" className="lg:border-l lg:border-white/10 lg:pl-6">
          <p className="text-sm font-semibold text-[#9fffe0]">Product</p>
          <div className={`mt-3 flex flex-col gap-2 text-sm text-[#8FA39C]`}>
            <a className={linkClass} href="/#features">
              Features
            </a>
            <a className={linkClass} href="/#how-it-works">
              Explore the app
            </a>
            <a className={linkClass} href="/#how-it-works">
              How it works
            </a>
            <a className={linkClass} href="/#pricing">
              Pricing
            </a>
          </div>
        </nav>
        <nav aria-label="Channels" className="lg:border-l lg:border-white/10 lg:pl-6">
          <p className="text-sm font-semibold text-[#9fffe0]">Channels</p>
          <div className="mt-3 flex flex-col gap-2 text-sm text-[#8FA39C]">
            {CHANNELS.map((ch) => (
              <a key={ch.id} className={linkClass} href="/#reply">
                {ch.label}
              </a>
            ))}
          </div>
        </nav>
        <nav aria-label="Support" className="lg:border-l lg:border-white/10 lg:pl-6">
          <p className="text-sm font-semibold text-[#9fffe0]">Support</p>
          <div className="mt-3 flex flex-col gap-2 text-sm text-[#8FA39C]">
            <Link className={linkClass} to={PUBLIC_PATHS.contact}>
              Help & support
            </Link>
            {onOpenGuest ? (
              <button type="button" onClick={onOpenGuest} className={`text-left ${linkClass}`}>
                Ask Linas
              </button>
            ) : (
              <a className={linkClass} href="/#talk-to-linas">
                Ask Linas
              </a>
            )}
            <Link className={linkClass} to={PUBLIC_PATHS.contact}>
              Contact us
            </Link>
          </div>
        </nav>
        <nav aria-label="Legal" className="lg:border-l lg:border-white/10 lg:pl-6">
          <p className="text-sm font-semibold text-[#9fffe0]">Legal</p>
          <div className="mt-3 flex flex-col gap-2 text-sm text-[#8FA39C]">
            <a className={linkClass} href={PUBLIC_PATHS.terms}>
              Terms of Service
            </a>
            <a className={linkClass} href={PUBLIC_PATHS.privacy}>
              Privacy Policy
            </a>
            <a className={linkClass} href={PUBLIC_PATHS.dataDeletion}>
              Data Deletion
            </a>
          </div>
        </nav>
      </div>

      <div className="relative mx-auto flex max-w-6xl flex-col gap-2 px-4 py-5 text-[0.72rem] text-[#5E706A] sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>
          © {year} {PUBLIC_SITE.productName}. All rights reserved.
        </p>
        <p>Built for businesses that care about every reply.</p>
      </div>
    </footer>
  );
};

export default PublicSiteFooter;
