function GlobeIcon() {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 text-[#06715F]" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4">
      <circle cx="8" cy="8" r="6.2" />
      <path d="M2 8h12M8 2c2.1 1.8 3.2 3.9 3.2 6S10.1 12.2 8 14C5.9 12.2 4.8 10.1 4.8 8S5.9 3.8 8 2z" />
    </svg>
  );
}

/** Part 1 — left copy column (Karen Figma). */
export default function LiveNetworkCopy() {
  return (
    <div className="lp-live-copy flex h-full min-h-[13.75rem] flex-col justify-between gap-6">
      <div>
        <p className="inline-flex items-center gap-2 rounded-full bg-[#E7F6F1] px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-[#06715F]">
          <span className="lp-live-dot relative inline-block h-2 w-2 rounded-full bg-[#06715F]" />
          Live network
        </p>
        <h2 className="mt-4 text-[2.05rem] font-semibold leading-[1.06] tracking-[-0.02em] text-[#171A19] sm:text-[2.15rem]">
          Every reply
          <br />
          <span className="text-[#06715F]">adds up.</span>
        </h2>
        <p className="mt-3 max-w-[15rem] text-sm leading-relaxed text-[#6B746F]">Real activity across the Linas AI network.</p>
      </div>
      <p className="flex items-center gap-2 text-xs text-[#8A938F]">
        <GlobeIcon />
        Updated automatically
      </p>
    </div>
  );
}
