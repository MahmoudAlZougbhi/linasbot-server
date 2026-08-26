import LinasStar from './LinasStar';
import { HERO_CHANNELS } from './HeroChannelRow';
import { CalendarGlyph, ChatGlyph, CommentGlyph, DocGlyph } from './HowItWorksIcons';

const CHANNELS = [
  { id: 'instagram', replies: 32, comments: 14, requests: 6 },
  { id: 'facebook', replies: 18, comments: 10, requests: 5 },
  { id: 'tiktok', replies: 8, comments: 3, requests: 2 },
  { id: 'whatsapp', replies: 6, comments: 1, requests: 2 },
].map((row) => {
  const channel = HERO_CHANNELS.find((item) => item.id === row.id);
  if (!channel) {
    throw new Error(`How it works dashboard is missing channel ${row.id}`);
  }
  return { ...row, label: channel.label, Mark: channel.Mark };
});

function SmartMark({ className = 'h-3 w-3' }) {
  return <LinasStar className={className} color="#00C9A0" showMark={false} />;
}

const METRICS = [
  { label: 'Replies', value: '88', hint: 'Total replies', Icon: ChatGlyph },
  { label: 'Comments', value: '24', hint: 'Total comments', Icon: CommentGlyph },
  { label: 'Smart Answers', value: '18', hint: 'AI answers', Icon: SmartMark },
  { label: 'Requests', value: '12', hint: 'Total requests', Icon: DocGlyph },
];

export default function HowItWorksDashboardScreen() {
  return (
    <div className="relative flex h-full flex-col bg-[#F7F9F7] px-3 pb-2.5 pt-8 text-[#171A19]">
      <div className="mb-1 flex items-center justify-between px-1 text-[10px] font-semibold">
        <span>9:41</span>
        <span className="flex items-center gap-0.5 text-[#171A19]" aria-hidden="true">
          <span className="h-[7px] w-[10px] rounded-[1px] border border-current" />
          <span className="h-[9px] w-[6px] rounded-[1px] border border-current" />
          <span className="h-[11px] w-[16px] rounded-[2px] border border-current" />
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span className="flex h-5 w-5 flex-col justify-center gap-[3px]" aria-hidden="true">
          <span className="h-[1.6px] w-4 bg-[#171A19]" />
          <span className="h-[1.6px] w-4 bg-[#171A19]" />
          <span className="h-[1.6px] w-4 bg-[#171A19]" />
        </span>
        <p className="text-[13px] font-semibold tracking-tight">Dashboard</p>
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-[#06715F] shadow-sm" aria-hidden="true">
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none">
            <path d="M13 8a5 5 0 1 1-1.4-3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            <path d="M13 3.2V6H10.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </div>
      <div className="mt-2.5 flex w-full items-center justify-between rounded-xl border border-[#E6EBE8] bg-white px-2.5 py-1.5 text-[10px] font-medium text-[#5C6663]">
        <span className="flex items-center gap-1.5">
          <CalendarGlyph className="h-3.5 w-3.5 text-[#00C9A0]" />
          Aug 1 – Aug 13
        </span>
        <span className="text-[8px] text-[#9AA39F]">▾</span>
      </div>
      <div className="hiw-dash-card mt-2.5">
        <p className="text-[10px] font-medium text-white/70">Credits</p>
        <p className="mt-0.5 text-[1.45rem] font-semibold tracking-tight">12,480 remaining</p>
        <div className="hiw-dash-bar mt-2.5">
          <span />
        </div>
        <p className="mt-1.5 text-[9px] text-white/65">7,520 used of 20,000</p>
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[9px] text-white/65">Renews Sep 13</span>
          <span className="rounded-full border border-white/40 px-2.5 py-0.5 text-[9px] font-semibold">Buy credits</span>
        </div>
      </div>
      <p className="mt-2.5 text-[10px] font-semibold">Overview</p>
      <div className="mt-1.5 grid grid-cols-2 gap-1.5">
        {METRICS.map((item) => (
          <div key={item.label} className="rounded-[0.9rem] bg-white px-2.5 py-2 shadow-[0_4px_12px_rgba(23,26,25,0.04)]">
            <div className="flex items-center gap-1.5 text-[#00C9A0]">
              <item.Icon className="h-3 w-3" />
              <p className="text-[9px] font-medium text-[#6B746F]">{item.label}</p>
            </div>
            <p className="mt-0.5 text-[1.2rem] font-semibold tracking-tight text-[#00C9A0]">{item.value}</p>
            <p className="text-[8px] text-[#8A938F]">{item.hint}</p>
          </div>
        ))}
      </div>
      <div className="mt-2 min-h-0 flex-1 rounded-[0.95rem] bg-white px-2.5 py-2 shadow-[0_4px_12px_rgba(23,26,25,0.04)]">
        <p className="text-[10px] font-semibold text-[#171A19]">Performance by channel</p>
        <div className="mt-1.5 grid grid-cols-[1fr_repeat(3,2.35rem)] gap-1 text-[7.5px] font-medium uppercase tracking-wide text-[#8A938F]">
          <span>Channel</span>
          <span className="text-center">Rep</span>
          <span className="text-center">Com</span>
          <span className="text-center">Req</span>
        </div>
        {CHANNELS.map((row) => {
          const Mark = row.Mark;
          return (
            <div key={row.id} className="mt-1 grid grid-cols-[1fr_repeat(3,2.35rem)] items-center gap-1">
              <span className="flex items-center gap-1.5 text-[10px] font-medium">
                <Mark className="h-3.5 w-3.5" />
                {row.label}
              </span>
              <span className="text-center text-[10px] font-semibold">{row.replies}</span>
              <span className="text-center text-[10px] font-semibold">{row.comments}</span>
              <span className="text-center text-[10px] font-semibold">{row.requests}</span>
            </div>
          );
        })}
      </div>
      <p className="mt-1.5 text-center text-[8px] text-[#8A938F]">All times shown in your local time zone.</p>
    </div>
  );
}
