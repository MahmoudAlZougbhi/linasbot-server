import { Link } from 'react-router-dom';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';
import { CHANNELS, FbIcon, IgIcon, TtIcon } from './ChannelIcons';
import LinasStar from './LinasStar';
import StoreBadges from './StoreBadges';

/**
 * @param {{ onOpenGuest?: () => void }} props
 */
const PublicSiteFooter = ({ onOpenGuest }) => {
  const year = new Date().getFullYear();
  return (
    <footer className="relative z-10 bg-[#0B3D34] text-[#C9D0CD]">
      <div className="bg-[#F7F8F5] px-4 pb-10 sm:px-6">
        <div className="relative mx-auto flex max-w-6xl flex-col gap-8 overflow-hidden rounded-[2rem] border border-[#E4E8E6] bg-[#F3F7F4] px-6 py-10 sm:px-12 lg:flex-row lg:items-center lg:justify-between">
          <LinasStar className="pointer-events-none absolute bottom-2 left-1/2 h-24 w-24 -translate-x-1/2 opacity-20" />
          <div className="relative">
            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#06715F]">Ready when you are</p>
            <h2 className="mt-3 max-w-md text-3xl font-semibold tracking-tight text-[#171A19] sm:text-4xl">
              One AI to learn your business. Every channel ready to answer.
            </h2>
          </div>
          <div className="relative">
            <StoreBadges compact variant="hero" />
          </div>
        </div>
      </div>

      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[minmax(0,1.1fr)_repeat(4,minmax(0,0.7fr))]">
        <div>
          <div className="flex items-center gap-2.5">
            <LinasStar className="h-5 w-5" color="#54C7AC" />
            <p className="text-lg font-semibold text-white">{PUBLIC_SITE.productName}</p>
          </div>
          <p className="mt-3 max-w-sm text-sm leading-relaxed text-[#9AA39F]">
            Teach Linas once. Stay in control while it helps answer every customer.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            {[
              { label: 'Instagram', Icon: IgIcon },
              { label: 'Facebook', Icon: FbIcon },
              { label: 'TikTok', Icon: TtIcon },
            ].map((item) => (
              <span key={item.label} className="inline-flex items-center gap-2 rounded-full border border-white/15 px-3 py-1 text-xs text-white">
                <item.Icon className="h-4 w-4" />
                {item.label}
              </span>
            ))}
          </div>
        </div>

        <nav aria-label="Product">
          <p className="text-sm font-semibold text-white">Product</p>
          <div className="mt-3 flex flex-col gap-2 text-sm">
            <a href="/#features">Features</a>
            <a href="/#how-it-works">Explore the app</a>
            <a href="/#how-it-works">How it works</a>
            <a href="/#pricing">Pricing</a>
          </div>
        </nav>
        <nav aria-label="Channels">
          <p className="text-sm font-semibold text-white">Channels</p>
          <div className="mt-3 flex flex-col gap-2 text-sm">
            {CHANNELS.map((ch) => (
              <a key={ch.id} href="/#reply">
                {ch.label}
              </a>
            ))}
          </div>
        </nav>
        <nav aria-label="Support">
          <p className="text-sm font-semibold text-white">Support</p>
          <div className="mt-3 flex flex-col gap-2 text-sm">
            <Link to={PUBLIC_PATHS.contact}>Help & support</Link>
            {onOpenGuest ? (
              <button type="button" onClick={onOpenGuest} className="text-left">
                Ask Linas
              </button>
            ) : (
              <a href="/#talk-to-linas">Ask Linas</a>
            )}
            <Link to={PUBLIC_PATHS.contact}>Contact us</Link>
          </div>
        </nav>
        <nav aria-label="Legal">
          <p className="text-sm font-semibold text-white">Legal</p>
          <div className="mt-3 flex flex-col gap-2 text-sm">
            <a href={PUBLIC_PATHS.terms}>Terms of Service</a>
            <a href={PUBLIC_PATHS.privacy}>Privacy Policy</a>
            <a href={PUBLIC_PATHS.dataDeletion}>Data Deletion</a>
          </div>
        </nav>
      </div>

      <div className="mx-auto flex max-w-6xl flex-col gap-2 border-t border-white/10 px-4 py-4 text-xs text-[#7A8480] sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>
          © {year} {PUBLIC_SITE.productName}. All rights reserved.
        </p>
        <p>Built for businesses that care about every reply.</p>
      </div>
    </footer>
  );
};

export default PublicSiteFooter;
