import LinasStar from './LinasStar';

export const HERO_CHAT_LINES = [
  { role: 'linas', text: 'What would you like to teach me about your business?' },
  { role: 'you', text: "We're closed tomorrow." },
  { role: 'linas', text: 'Done — I added tomorrow as an off day.' },
  {
    role: 'you',
    text: 'If someone asks how long we’ve been in business, tell them the company was founded in 1977.',
  },
  { role: 'linas', text: 'Got it — I saved this in your Business Knowledge.' },
];

function BookIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
      <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v16H7.5A2.5 2.5 0 0 0 5 21.5V5.5Z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3" stroke="currentColor" strokeWidth="1.6" />
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

function StatusIcons() {
  return (
    <span className="flex items-center gap-[3px] text-[#171A19]" aria-hidden="true">
      <svg viewBox="0 0 18 12" className="h-2.5 w-[1.05rem]" fill="currentColor">
        <rect x="0" y="7" width="3" height="5" rx="0.6" />
        <rect x="5" y="5" width="3" height="7" rx="0.6" />
        <rect x="10" y="2.5" width="3" height="9.5" rx="0.6" />
        <rect x="15" y="0" width="3" height="12" rx="0.6" />
      </svg>
      <svg viewBox="0 0 16 12" className="h-2.5 w-3.5" fill="currentColor">
        <path d="M8 9.4a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8zm0-3.3c1.6 0 3.1.6 4.2 1.7l-1.1 1.1A4.1 4.1 0 0 0 8 7.6c-1.1 0-2.1.4-2.9 1.2L4 7.8A5.8 5.8 0 0 1 8 6.1zm0-3.3c2.5 0 4.8 1 6.5 2.7L13.4 7A7.3 7.3 0 0 0 8 4.3 7.3 7.3 0 0 0 2.6 7L1.5 5.5A9.3 9.3 0 0 1 8 2.8z" />
      </svg>
      <svg viewBox="0 0 25 12" className="h-2.5 w-[1.45rem]" fill="currentColor">
        <rect x="0.6" y="1.2" width="20.5" height="9.6" rx="2" fill="none" stroke="currentColor" strokeWidth="1.2" />
        <rect x="2.2" y="2.8" width="16.2" height="6.4" rx="1" />
        <rect x="21.8" y="4" width="1.8" height="4" rx="0.6" />
      </svg>
    </span>
  );
}

function FloatCard({ label, icon, className }) {
  return (
    <div
      className={`absolute z-10 flex items-center gap-2.5 rounded-2xl bg-white px-3 py-2.5 shadow-[0_12px_30px_rgba(23,26,25,0.1)] ring-1 ring-black/[0.04] ${className}`}
    >
      <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#E8F4F0] text-[#06715F]">{icon}</span>
      <span className="whitespace-nowrap text-sm font-medium text-[#171A19]">{label}</span>
      <span className="lp-live-dot ml-1 h-2 w-2 shrink-0 rounded-full bg-[#22A06B]" aria-hidden="true" />
    </div>
  );
}

export default function HeroPhoneStage() {
  return (
    <div className="relative mx-auto flex min-h-[34rem] w-full max-w-[28rem] items-center justify-center">
      <div className="lp-orbit lp-orbit-a" aria-hidden="true" />
      <div className="lp-orbit lp-orbit-b" aria-hidden="true" />
      <div className="lp-orbit lp-orbit-c" aria-hidden="true" />

      <FloatCard label="Knowledge updated" icon={<BookIcon />} className="left-0 top-[18%] lg:-left-4" />
      <FloatCard label="Off day saved" icon={<CalendarIcon />} className="right-0 top-[42%] lg:-right-2" />
      <FloatCard label="5 channels connected" icon={<PeopleIcon />} className="bottom-[14%] right-0 lg:-right-6" />

      <div className="relative z-[1] w-[17.5rem] rounded-[2.4rem] bg-[#111314] p-[0.55rem] shadow-[0_28px_60px_rgba(23,26,25,0.22)]">
        <div className="relative overflow-hidden rounded-[1.9rem] bg-white">
          <div
            className="absolute left-1/2 top-[0.55rem] z-[2] h-[1.2rem] w-[5.4rem] -translate-x-1/2 rounded-full bg-[#111314]"
            aria-hidden="true"
          />
          <div className="relative z-[1] flex items-center justify-between px-5 pt-3 text-[0.72rem] font-semibold text-[#171A19]">
            <span>9:41</span>
            <StatusIcons />
          </div>
          <div className="mt-1.5 flex items-center px-3 pb-2.5">
            <span className="flex h-6 w-6 items-center text-[#171A19]" aria-hidden="true">
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none">
                <path
                  d="M12.5 4.5 6.5 10l6 5.5"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <p className="flex flex-1 items-center justify-center gap-1.5 pr-6 text-sm font-semibold text-[#171A19]">
              Linas <LinasStar className="h-3.5 w-3.5" />
            </p>
          </div>
          <div className="min-h-[21.5rem] space-y-3.5 px-3.5 py-2">
            {HERO_CHAT_LINES.map((line) =>
              line.role === 'you' ? (
                <div key={line.text} className="lp-fade-up flex justify-end">
                  <p className="max-w-[14.5rem] rounded-[1.15rem] bg-[#ECEDEB] px-3 py-2 text-[0.8rem] leading-relaxed text-[#171A19]">
                    {line.text}
                  </p>
                </div>
              ) : (
                <p key={line.text} className="lp-fade-up max-w-[15rem] text-[0.8rem] leading-relaxed text-[#06715F]">
                  {line.text}
                </p>
              ),
            )}
          </div>
          <div className="px-3 pb-2">
            <div className="flex items-center gap-1.5 rounded-full bg-white px-2 py-1.5 shadow-[0_4px_14px_rgba(23,26,25,0.06)] ring-1 ring-[#E6E8E4]">
              <span className="flex h-7 w-7 items-center justify-center text-xl font-light text-[#6B746F]" aria-hidden="true">
                +
              </span>
              <span className="flex-1 text-[0.8rem] text-[#8A938F]">Work with Linas</span>
              <span className="text-[#6B746F]" aria-hidden="true">
                <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                  <path d="M10 2.2c.7 0 1.2.5 1.2 1.1v7.3l1.6-1.6a1 1 0 1 1 1.4 1.4l-3.3 3.3a1 1 0 0 1-1.4 0L6.2 10.4a1 1 0 1 1 1.4-1.4l1.6 1.6V3.3c0-.6.5-1.1 1.2-1.1zM4 16h12a1 1 0 1 1 0 2H4a1 1 0 1 1 0-2z" />
                </svg>
              </span>
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#06715F] text-white" aria-hidden="true">
                <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="currentColor">
                  <path d="M10 3.2 4.6 8.4a1 1 0 1 0 1.4 1.4L9 7.8V16a1 1 0 1 0 2 0V7.8l3 2a1 1 0 1 0 1.4-1.4L10 3.2z" />
                </svg>
              </span>
            </div>
            <div className="mx-auto mt-2 h-[4px] w-[6.5rem] rounded-full bg-[#171A19]/20" aria-hidden="true" />
          </div>
        </div>
      </div>
    </div>
  );
}
