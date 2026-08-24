import LinasStar from './LinasStar';

const CHANNELS = [
  { name: 'Instagram', replies: 32, comments: 8, requests: 4, color: '#E1306C' },
  { name: 'Facebook', replies: 22, comments: 6, requests: 3, color: '#1877F2' },
  { name: 'TikTok', replies: 18, comments: 5, requests: 2, color: '#111314' },
  { name: 'WhatsApp', replies: 16, comments: 5, requests: 3, color: '#25D366' },
];

const METRICS = [
  { label: 'Replies', value: '88' },
  { label: 'Comments', value: '24' },
  { label: 'Smart Answers', value: '18' },
  { label: 'Requests', value: '12' },
];

export default function HowItWorksDashboardScreen() {
  return (
    <div className="flex h-full flex-col bg-[#F3F6F4] px-3 pb-3 pt-9 text-[#171A19]">
      <div className="flex items-center justify-between">
        <span className="text-[15px] text-[#171A19]" aria-hidden="true">
          ☰
        </span>
        <p className="text-[13px] font-semibold tracking-tight">Dashboard</p>
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-[#06715F] shadow-sm" aria-hidden="true">
          ⌁
        </span>
      </div>
      <div className="mt-2.5 inline-flex self-start rounded-full bg-white px-2.5 py-1 text-[10px] font-medium text-[#5C6663] shadow-sm">
        Aug 1 – Aug 13
      </div>
      <div className="hiw-dash-card mt-2.5">
        <p className="text-[10px] font-medium text-white/70">Credits</p>
        <p className="mt-0.5 text-[1.35rem] font-semibold tracking-tight">12,480 remaining</p>
        <div className="hiw-dash-bar mt-2.5">
          <span />
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[9px] text-white/65">
          <span>7,520 used of 20,000</span>
          <span>Renews Sep 13</span>
        </div>
        <button type="button" className="mt-2.5 w-full rounded-full border border-white/35 py-1.5 text-[11px] font-semibold text-white">
          Buy credits
        </button>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-1.5">
        {METRICS.map((item) => (
          <div key={item.label} className="rounded-[0.9rem] bg-white px-2.5 py-2 shadow-[0_4px_12px_rgba(23,26,25,0.04)]">
            <p className="text-[9px] font-medium text-[#6B746F]">{item.label}</p>
            <p className="mt-0.5 text-[1.15rem] font-semibold tracking-tight">{item.value}</p>
          </div>
        ))}
      </div>
      <div className="mt-2 min-h-0 flex-1 rounded-[0.95rem] bg-white px-2.5 py-2 shadow-[0_4px_12px_rgba(23,26,25,0.04)]">
        <p className="text-[10px] font-semibold text-[#171A19]">Performance by channel</p>
        <div className="mt-1.5 grid grid-cols-[1fr_repeat(3,2.1rem)] gap-1 text-[8px] font-medium uppercase tracking-wide text-[#8A938F]">
          <span />
          <span className="text-center">Rep</span>
          <span className="text-center">Com</span>
          <span className="text-center">Req</span>
        </div>
        {CHANNELS.map((ch) => (
          <div key={ch.name} className="mt-1 grid grid-cols-[1fr_repeat(3,2.1rem)] items-center gap-1">
            <span className="flex items-center gap-1.5 text-[10px] font-medium">
              <span className="h-2 w-2 rounded-full" style={{ background: ch.color }} />
              {ch.name}
            </span>
            <span className="text-center text-[10px] font-semibold">{ch.replies}</span>
            <span className="text-center text-[10px] font-semibold">{ch.comments}</span>
            <span className="text-center text-[10px] font-semibold">{ch.requests}</span>
          </div>
        ))}
      </div>
      <p className="mt-1.5 text-center text-[8px] text-[#8A938F]">All times shown in your local time zone.</p>
      <LinasStar className="mx-auto mt-1 h-3 w-3 opacity-50" />
    </div>
  );
}
