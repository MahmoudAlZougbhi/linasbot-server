import { useMemo } from 'react';
import FeatureCarousel from '../FeatureCarousel';
import { GrowDashboard, GrowFollowUp, GrowInsights, GrowRequests, GrowSmartAnswers } from '../cards/GrowMinis';

/**
 * @param {{ stats?: object | null }} props
 */
export default function LandingGrow({ stats }) {
  const cards = useMemo(
    () => [
      {
        id: 'follow-up',
        title: 'Smart Follow-Up',
        description: 'Checks back automatically when an interested customer goes quiet.',
        Mini: GrowFollowUp,
      },
      {
        id: 'requests',
        title: 'Requests',
        description: 'Track orders, appointments and customer requests from one place.',
        Mini: GrowRequests,
      },
      {
        id: 'smart-answers',
        title: 'Smart Answers',
        description:
          'Matched replies cost 0 credits — they are free. Write a Q&A once for every language you select. The more Q&As you save, the more replies stay free.',
        core: true,
        Mini: GrowSmartAnswers,
      },
      {
        id: 'dashboard',
        title: 'Activity Dashboard',
        description: 'See messages, comments and requests across every channel.',
        Mini: (p) => <GrowDashboard {...p} stats={stats} />,
      },
      {
        id: 'insights',
        title: 'Channel Insights',
        description: 'Know which channels perform best and how credits are used.',
        Mini: GrowInsights,
      },
    ],
    [stats],
  );

  return (
    <FeatureCarousel
      id="grow"
      kicker="Grow"
      title="Turn every conversation"
      accent="into growth."
      subtitle="Save credits, follow up, capture requests and see what is working."
      cards={cards}
    />
  );
}
