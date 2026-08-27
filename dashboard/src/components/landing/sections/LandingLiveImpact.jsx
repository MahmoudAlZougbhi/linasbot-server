import LiveNetworkCopy from '../liveNetwork/LiveNetworkCopy';
import LiveNetworkFlow from '../LiveNetworkFlow';

/**
 * @param {{ stats?: { ai_replies?: number, businesses_using_linas?: number | null } | null }} props
 */
export default function LandingLiveImpact({ stats }) {
  const replies = stats?.ai_replies ?? null;
  const businesses = stats?.businesses_using_linas ?? null;

  return (
    <section id="live-impact" className="bg-[#F7F8F5] px-4 py-16 sm:px-6">
      <div className="lp-live-card mx-auto max-w-6xl rounded-[1.75rem] border border-[#E7EBE9] bg-white px-6 py-10 shadow-[0_18px_50px_rgba(23,26,25,0.06)] sm:px-10 lg:py-12">
        <div className="lp-live-card-grid">
          <LiveNetworkCopy />
          <LiveNetworkFlow replies={replies} businesses={businesses} />
        </div>
      </div>
    </section>
  );
}
