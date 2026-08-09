import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import PublicSiteHeader from '../../components/landing/PublicSiteHeader';
import PublicSiteFooter from '../../components/landing/PublicSiteFooter';
import GuestChatPanel from '../../components/landing/GuestChatPanel';
import LandingHero from '../../components/landing/sections/LandingHero';
import LandingFeatures from '../../components/landing/sections/LandingFeatures';
import LandingHowItWorks from '../../components/landing/sections/LandingHowItWorks';
import LandingAppTour from '../../components/landing/sections/LandingAppTour';
import LandingPricing from '../../components/landing/sections/LandingPricing';
import LandingResources from '../../components/landing/sections/LandingResources';
import LandingDownload from '../../components/landing/sections/LandingDownload';
import LandingFaqContact from '../../components/landing/sections/LandingFaqContact';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';

/**
 * Public marketing landing — visual composition from
 * docs/design/landing/LINAS_AI_LANDING_PAGE_DESIGN_IMAGES.zip
 * (no Login / Create Account CTAs; ops /login stays unlinked).
 */
const Landing = () => {
  const [guestOpen, setGuestOpen] = useState(false);
  const openGuest = useCallback(() => setGuestOpen(true), []);
  const closeGuest = useCallback(() => setGuestOpen(false), []);

  return (
    <div className="min-h-screen bg-[#F6F7F6] font-sans text-[#171A19] antialiased">
      <PublicSiteHeader onOpenGuest={openGuest} />

      <main>
        <LandingHero onOpenGuest={openGuest} />
        <LandingFeatures />
        <LandingHowItWorks onOpenGuest={openGuest} />
        <LandingAppTour />
        <LandingPricing />
        <LandingResources />
        <LandingDownload />
        <LandingFaqContact />

        <section id="privacy" className="border-t border-[#E4E8E6] bg-[#F6F7F6] py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="text-2xl font-semibold tracking-tight text-[#171A19]">Privacy and data use</h2>
            <p className="mt-4 max-w-4xl text-base leading-relaxed text-[#5C6663]">{PUBLIC_SITE.metaPlatformDataUse}</p>
            <p className="mt-4 text-sm text-[#5C6663]">
              Read the full{' '}
              <a className="font-semibold text-[#06715F] underline" href={PUBLIC_PATHS.privacy}>
                Privacy Policy
              </a>
              ,{' '}
              <a className="font-semibold text-[#06715F] underline" href={PUBLIC_PATHS.terms}>
                Terms of Service
              </a>
              , and{' '}
              <a className="font-semibold text-[#06715F] underline" href={PUBLIC_PATHS.dataDeletion}>
                User Data Deletion Instructions
              </a>
              .
            </p>
            <p className="mt-6 max-w-3xl text-sm text-[#5C6663]">
              {PUBLIC_SITE.productName} is the software platform behind{' '}
              <a className="font-semibold text-[#06715F] underline" href={PUBLIC_SITE.publicBaseUrl}>
                {PUBLIC_SITE.publicBaseUrl.replace('https://', '')}
              </a>
              .{' '}
              <Link className="font-semibold text-[#06715F] underline" to={PUBLIC_PATHS.about}>
                More about {PUBLIC_SITE.productName}
              </Link>
            </p>
          </div>
        </section>
      </main>

      <PublicSiteFooter />
      <GuestChatPanel open={guestOpen} onOpen={openGuest} onClose={closeGuest} />
    </div>
  );
};

export default Landing;
