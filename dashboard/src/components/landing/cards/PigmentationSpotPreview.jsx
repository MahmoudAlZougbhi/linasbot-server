/** Illustration of hyperpigmentation for the voice + vision reply card (no stock portrait). */
export default function PigmentationSpotPreview() {
  return (
    <div
      className="lp-fade-up relative mt-2.5 overflow-hidden rounded-xl bg-[#F3E4D6] ring-1 ring-[#E6EBE8]"
      style={{ animationDelay: '400ms' }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 280 112" className="block h-28 w-full" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="lp-pigment-skin" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#EACCB0" />
            <stop offset="100%" stopColor="#DFB995" />
          </linearGradient>
          <radialGradient id="lp-pigment-spot-a" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#7A4E32" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#7A4E32" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="lp-pigment-spot-b" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#6B4228" stopOpacity="0.42" />
            <stop offset="100%" stopColor="#6B4228" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="280" height="112" fill="url(#lp-pigment-skin)" />
        <ellipse cx="98" cy="48" rx="34" ry="26" fill="url(#lp-pigment-spot-a)" />
        <ellipse cx="148" cy="62" rx="22" ry="17" fill="url(#lp-pigment-spot-b)" />
        <ellipse cx="176" cy="44" rx="14" ry="11" fill="#8B5A3C" opacity="0.22" />
        <ellipse cx="122" cy="72" rx="10" ry="8" fill="#8B5A3C" opacity="0.18" />
        <rect x="18" y="16" width="44" height="44" fill="none" stroke="#06715F" strokeWidth="1.2" strokeDasharray="4 3" opacity="0.55" rx="4" />
        <rect x="18" y="16" width="44" height="44" fill="#06715F" opacity="0.06" rx="4" />
        <path d="M18 16 L28 16 M18 16 L18 26 M62 16 L52 16 M62 16 L62 26 M18 60 L28 60 M18 60 L18 50 M62 60 L52 60 M62 60 L62 50" stroke="#06715F" strokeWidth="1.4" opacity="0.7" />
        <text x="140" y="98" textAnchor="middle" fill="#8A938F" fontSize="9" fontFamily="Inter, ui-sans-serif, system-ui, sans-serif">
          Pigmentation area · vision scan
        </text>
      </svg>
    </div>
  );
}
