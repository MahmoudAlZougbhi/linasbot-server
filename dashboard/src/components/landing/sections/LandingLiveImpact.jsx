import CountUp from '../CountUp';
import LiveNetworkFlow from '../LiveNetworkFlow';

function GlobeIcon() {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 text-[#06715F]" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4">
      <circle cx="8" cy="8" r="6.2" />
      <path d="M2 8h12M8 2c2.1 1.8 3.2 3.9 3.2 6S10.1 12.2 8 14C5.9 12.2 4.8 10.1 4.8 8S5.9 3.8 8 2z" />
    </svg>
  );
}

/**
 * @param {{ stats?: { ai_replies?: number, businesses_using_linas?: number | null } | null }} props
 */
export default function LandingLiveImpact({ stats }) {
  const replies = stats?.ai_replies ?? null;
  const businesses = stats?.businesses_using_linas ?? null;

  return (
    <section id="live-impact" className="bg-[#F7F8F5] px-4 py-16 sm:px-6">
      <div className="mx-auto grid max-w-6xl items-center gap-8 rounded-[1.75rem] border border-[#E7EBE9] bg-white px-6 py-10 shadow-[0_18px_50px_rgba(23,26,25,0.06)] sm:px-10 lg:grid-cols-[minmax(16rem,0.92fr)_minmax(0,1.35fr)_minmax(7rem,0.42fr)] lg:py-12">
        <div className="flex h-full flex-col justify-between gap-8">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full bg-[#E7F6F1] px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-[#06715F]">
              <span className="lp-live-dot relative inline-block h-2 w-2 rounded-full bg-[#06715F]" />
              Live network
            </p>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight text-[#171A19] sm:text-[2.15rem]">
              Every reply <span className="text-[#06715F]">adds up.</span>
            </h2>
            <p className="mt-3 text-sm text-[#6B746F]">Real activity across the Linas AI network.</p>
          </div>
          <p className="flex items-center gap-2 text-xs text-[#8A938F]">
            <GlobeIcon />
            Updated automatically
          </p>
        </div>

        <LiveNetworkFlow replies={replies} />

        <div className="text-center lg:text-left">
          <p className="text-5xl font-semibold tracking-tight text-[#171A19] sm:text-6xl">
            <CountUp value={businesses} />
          </p>
          <p className="mt-2 text-sm text-[#5C6663]">Businesses using Linas</p>
        </div>
      </div>
    </section>
  );
}
