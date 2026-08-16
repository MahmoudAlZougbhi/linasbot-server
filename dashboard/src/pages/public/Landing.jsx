import { useCallback, useState } from 'react';
import '../../styles/landing.css';
import PublicSiteHeader from '../../components/landing/PublicSiteHeader';
import PublicSiteFooter from '../../components/landing/PublicSiteFooter';
import GuestChatPanel from '../../components/landing/GuestChatPanel';
import LandingHero from '../../components/landing/sections/LandingHero';
import LandingTeach from '../../components/landing/sections/LandingTeach';
import LandingReply from '../../components/landing/sections/LandingReply';
import LandingControl from '../../components/landing/sections/LandingControl';
import LandingGrow from '../../components/landing/sections/LandingGrow';
import LandingHowItWorks from '../../components/landing/sections/LandingHowItWorks';
import LandingLiveImpact from '../../components/landing/sections/LandingLiveImpact';
import LandingPricing from '../../components/landing/sections/LandingPricing';
import { usePublicLandingStats } from '../../hooks/usePublicLandingStats';

const Landing = () => {
  const [guestOpen, setGuestOpen] = useState(false);
  const openGuest = useCallback(() => setGuestOpen(true), []);
  const closeGuest = useCallback(() => setGuestOpen(false), []);
  const stats = usePublicLandingStats();

  return (
    <div className="landing-page min-h-screen antialiased">
      <PublicSiteHeader />
      <main>
        <LandingHero />
        <LandingTeach />
        <LandingReply />
        <LandingControl />
        <LandingGrow stats={stats} />
        <LandingHowItWorks />
        <LandingLiveImpact stats={stats} />
        <LandingPricing />
      </main>
      <PublicSiteFooter onOpenGuest={openGuest} />
      <GuestChatPanel open={guestOpen} onOpen={openGuest} onClose={closeGuest} showFab={false} />
    </div>
  );
};

export default Landing;
