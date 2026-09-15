/** Illustration of a photo question for the voice + vision reply card. */
export default function PhotoQuestionPreview() {
  return (
    <div
      className="lp-fade-up relative mt-2.5 overflow-hidden rounded-xl bg-[#EEF4F2] ring-1 ring-[#E6EBE8]"
      style={{ animationDelay: '400ms' }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 280 112" className="block h-28 w-full" preserveAspectRatio="xMidYMid slice">
        <rect width="280" height="112" fill="#F4F7F6" />
        <rect x="88" y="14" width="104" height="72" rx="8" fill="#FFFFFF" stroke="#D5DCD8" strokeWidth="1.2" />
        <rect x="100" y="24" width="80" height="40" rx="4" fill="#E8F5F1" />
        <circle cx="118" cy="38" r="7" fill="#06715F" opacity="0.35" />
        <path d="M108 58 L124 44 L140 54 L152 48 L172 58 Z" fill="#06715F" opacity="0.28" />
        <rect x="108" y="70" width="48" height="6" rx="2" fill="#D5DCD8" />
        <rect x="18" y="16" width="44" height="44" fill="none" stroke="#06715F" strokeWidth="1.2" strokeDasharray="4 3" opacity="0.55" rx="4" />
        <rect x="18" y="16" width="44" height="44" fill="#06715F" opacity="0.06" rx="4" />
        <path d="M18 16 L28 16 M18 16 L18 26 M62 16 L52 16 M62 16 L62 26 M18 60 L28 60 M18 60 L18 50 M62 60 L52 60 M62 60 L62 50" stroke="#06715F" strokeWidth="1.4" opacity="0.7" />
        <text x="140" y="102" textAnchor="middle" fill="#8A938F" fontSize="9" fontFamily="Inter, ui-sans-serif, system-ui, sans-serif">
          Photo question · vision scan
        </text>
      </svg>
    </div>
  );
}
