import HeroPhoneChat from './HeroPhoneChat';

function BookIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
      <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v16H7.5A2.5 2.5 0 0 0 5 21.5V5.5Z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 8h8M8 11.5h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
      <rect x="4" y="5" width="16" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4 10h16M8 3.5v4M16 3.5v4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function PeopleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
      <circle cx="9" cy="9" r="2.4" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="16" cy="10" r="2" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M4.5 18c.4-2.4 2.4-4 4.5-4s4.1 1.6 4.5 4M13 17.5c.4-1.6 1.8-2.8 3.4-2.8 1.4 0 2.7.9 3.2 2.2"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * @param {{ label: string, icon: import('react').ReactNode, className: string }} props
 */
function FloatCard({ label, icon, className }) {
  return (
    <div
      className={`pointer-events-none absolute z-[2] flex items-center gap-2.5 rounded-2xl bg-white px-3.5 py-2.5 shadow-[0_16px_36px_rgba(23,26,25,0.12)] ring-1 ring-black/[0.04] ${className}`}
    >
      <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#E8F4F0] text-[#06715F]">{icon}</span>
      <span className="whitespace-nowrap text-sm font-medium text-[#171A19]">{label}</span>
      <span className="lp-live-dot ml-0.5 h-2 w-2 shrink-0 rounded-full bg-[#22A06B]" aria-hidden="true" />
    </div>
  );
}

export default function HeroPhoneStage() {
  return (
    <div className="relative mx-auto flex w-full max-w-[42rem] justify-center overflow-visible px-2 pb-24 pt-20 lg:min-h-[50rem] lg:items-center lg:px-4 lg:pb-8 lg:pt-8">
      <div className="lp-orbit lp-orbit-a" aria-hidden="true" />
      <div className="lp-orbit lp-orbit-b" aria-hidden="true" />
      <div className="lp-orbit lp-orbit-c" aria-hidden="true" />
      <div className="lp-orbit lp-orbit-d" aria-hidden="true" />

      <div className="relative z-[1]">
        <HeroPhoneChat />
      </div>
      <FloatCard
        label="Knowledge updated"
        icon={<BookIcon />}
        className="left-2 top-4 lg:left-auto lg:right-[calc(50%+9.4rem)] lg:top-[30%]"
      />
      <FloatCard
        label="Off day saved"
        icon={<CalendarIcon />}
        className="right-2 top-4 lg:left-[calc(50%+9.4rem)] lg:right-auto lg:top-[8%]"
      />
      <FloatCard
        label="5 channels connected"
        icon={<PeopleIcon />}
        className="bottom-4 right-2 lg:bottom-[12%] lg:left-[calc(50%+9.4rem)] lg:right-auto lg:top-auto"
      />
    </div>
  );
}
