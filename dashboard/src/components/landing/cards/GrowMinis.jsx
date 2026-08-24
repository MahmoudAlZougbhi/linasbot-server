import MiniFrame from './MiniFrame';
import CountUp from '../CountUp';

/** @typedef {{ play?: boolean }} MiniPlay */

/** @param {MiniPlay} props */
export function GrowFollowUp({ play }) {
  return (
    <MiniFrame play={play}>
      <p className="text-xs text-[#5C6663]">Customer went quiet</p>
      <p className="lp-fade-up mt-2 inline-flex rounded-full bg-[#06715F] px-2 py-0.5 text-[0.65rem] font-semibold text-white" style={{ animationDelay: '400ms' }}>
        30 min
      </p>
      <p className="lp-fade-up mt-3 rounded-xl bg-[#E8F5F1] px-3 py-2 text-xs text-[#171A19]" style={{ animationDelay: '1100ms' }}>
        Still interested? I can help you book.
      </p>
      <p className="mt-2 text-[0.6rem] font-bold uppercase tracking-wide text-[#8A938F]">Auto</p>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function GrowRequests({ play }) {
  const rows = [
    { name: 'Laser appointment', status: 'New', cls: 'bg-[#E8F5F1] text-[#06715F]', delay: '0ms' },
    { name: 'Hair treatment request', status: 'In progress', cls: 'bg-[#FFF4D6] text-[#8A5A00]', delay: '700ms' },
    { name: 'Product order', status: 'Done', cls: 'bg-[#E8F5F1] text-[#06715F]', delay: '1400ms' },
  ];
  return (
    <MiniFrame play={play}>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.name} className="flex items-center justify-between text-xs">
            <span className="text-[#171A19]">{row.name}</span>
            <span className={`lp-fade-up rounded-full px-2 py-0.5 text-[0.6rem] font-semibold ${row.cls}`} style={{ animationDelay: row.delay }}>
              {row.status}
            </span>
          </li>
        ))}
      </ul>
      <div className="lp-fade-up mt-3 flex gap-2 text-[0.65rem] text-[#06715F]" style={{ animationDelay: '1800ms' }}>
        <span className="rounded-full border border-[#06715F] px-2 py-0.5">Print</span>
        <span className="rounded-full border border-[#06715F] px-2 py-0.5">Assign</span>
      </div>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function GrowSmartAnswers({ play }) {
  return (
    <MiniFrame play={play}>
      <p className="text-[0.6rem] font-semibold uppercase tracking-wide text-[#06715F]">Write once</p>
      <p className="mt-1 text-xs leading-snug text-[#171A19]">
        I tanned yesterday — can I still do full-body laser? How much is it?
      </p>
      <p className="mt-2 text-xs font-semibold leading-snug text-[#171A19]">
        Full body is $299. Wait until the tan fades — then I can book you.
      </p>
      <p className="mt-2 text-[0.6rem] text-[#5C6663]">Auto in every language you select</p>
      <div className="mt-1 flex flex-wrap gap-1">
        {['EN', 'AR', 'FR', 'Arabizi'].map((code, i) => (
          <span
            key={code}
            className="lp-fade-up rounded-full bg-[#06715F] px-2 py-0.5 text-[0.6rem] font-semibold text-white"
            style={{ animationDelay: `${700 + i * 100}ms` }}
          >
            {code}
          </span>
        ))}
      </div>
      <p className="lp-fade-up mt-2 text-[0.65rem] font-semibold text-[#06715F]" style={{ animationDelay: '1300ms' }}>
        0 credits · Free reply · More Q&amp;As, more free replies
      </p>
    </MiniFrame>
  );
}

/**
 * @param {{ play?: boolean, stats?: { messages_replied?: number, comments_replied?: number, requests?: number | null } | null }} props
 */
export function GrowDashboard({ play, stats }) {
  const messages = stats ? stats.messages_replied ?? 0 : null;
  const comments = stats ? stats.comments_replied ?? 0 : null;
  const requests = stats ? stats.requests ?? 0 : null;
  return (
    <MiniFrame play={play}>
      <p className="text-[0.65rem] text-[#5C6663]">All-time activity</p>
      <div className="mt-2 grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-lg font-semibold text-[#171A19]">{play ? <CountUp value={messages} duration={1600} /> : messages == null ? '—' : messages.toLocaleString()}</p>
          <p className="text-[0.6rem] text-[#5C6663]">Messages</p>
        </div>
        <div>
          <p className="text-lg font-semibold text-[#171A19]">{play ? <CountUp value={comments} duration={1600} /> : comments == null ? '—' : comments.toLocaleString()}</p>
          <p className="text-[0.6rem] text-[#5C6663]">Comments</p>
        </div>
        <div>
          <p className="text-lg font-semibold text-[#171A19]">{play ? <CountUp value={requests} duration={1600} /> : requests == null ? '—' : requests.toLocaleString()}</p>
          <p className="text-[0.6rem] text-[#5C6663]">Requests</p>
        </div>
      </div>
      <div className="mt-3 flex h-8 items-end gap-1">
        {[40, 55, 48, 70, 62, 88, 76].map((h, i) => (
          <span
            key={h}
            className="lp-fade-up w-full rounded-t bg-[#06715F]"
            style={{ height: `${h}%`, animationDelay: `${i * 80}ms` }}
          />
        ))}
      </div>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function GrowInsights({ play }) {
  const rows = [
    { name: 'Instagram', pct: 42 },
    { name: 'WhatsApp', pct: 31 },
    { name: 'Facebook', pct: 18 },
    { name: 'TikTok', pct: 9 },
  ];
  return (
    <MiniFrame play={play}>
      {rows.map((row, i) => (
        <div key={row.name} className="mt-1.5">
          <div className="flex justify-between text-[0.65rem] text-[#171A19]">
            <span>{row.name}</span>
            <span>{row.pct}%</span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[#E4EBE8]">
            <div
              className="lp-fill h-full rounded-full bg-[#06715F]"
              style={{ width: `${row.pct}%`, animationDelay: `${i * 200}ms`, transform: play ? undefined : 'scaleX(1)' }}
            />
          </div>
        </div>
      ))}
      <p className="lp-fade-up mt-3 text-sm font-semibold text-[#06715F]" style={{ animationDelay: '900ms' }}>
        Credits remaining: 12,480
      </p>
    </MiniFrame>
  );
}
