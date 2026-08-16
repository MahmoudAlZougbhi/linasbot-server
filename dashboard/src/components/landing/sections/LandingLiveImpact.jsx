import CountUp from '../CountUp';
import LinasStar from '../LinasStar';

/**
 * @param {{ stats?: { ai_replies?: number, businesses_using_linas?: number | null } | null }} props
 */
export default function LandingLiveImpact({ stats }) {
  const replies = stats?.ai_replies ?? null;
  const businesses = stats?.businesses_using_linas ?? null;

  return (
    <section id="live-impact" className="bg-[#F7F8F5] px-4 py-16 sm:px-6">
      <div className="mx-auto grid max-w-6xl items-center gap-8 rounded-[2rem] border border-[#E4E8E6] bg-white px-6 py-12 shadow-sm sm:px-12 lg:grid-cols-3">
        <div>
          <p className="flex items-center gap-2 text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-[#7AA3B8]">
            <span className="lp-live-dot relative inline-block h-2.5 w-2.5 rounded-full bg-[#06715F]" />
            Live impact
          </p>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-[#171A19] sm:text-4xl">
            Every reply <span className="text-[#06715F]">adds up.</span>
          </h2>
          <p className="mt-3 text-sm text-[#6B746F]">Real activity across the Linas AI network.</p>
        </div>

        <div className="border-t border-[#E4E8E6] pt-8 text-center lg:border-l lg:border-t-0 lg:pt-0">
          <p className="text-5xl font-semibold tracking-tight text-[#171A19]">
            <CountUp value={replies} />
          </p>
          <p className="mt-2 text-sm text-[#5C6663]">Messages answered by Linas</p>
          <p className="mt-4 text-[#06715F]" aria-hidden="true">
            ⌬
          </p>
          <p className="mt-3 text-xs text-[#9AA39F]">Updated automatically</p>
        </div>

        <div className="border-t border-[#E4E8E6] pt-8 text-center lg:border-l lg:border-t-0 lg:pt-0">
          <p className="text-5xl font-semibold tracking-tight text-[#171A19]">
            <CountUp value={businesses} />
          </p>
          <p className="mt-2 text-sm text-[#5C6663]">Businesses using Linas</p>
          <div className="mt-4 flex justify-center">
            <LinasStar className="h-6 w-6" />
          </div>
          <p className="mt-3 text-xs text-[#9AA39F]">Active subscribers</p>
        </div>
      </div>
    </section>
  );
}
