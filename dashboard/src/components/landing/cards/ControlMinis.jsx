import MiniFrame from './MiniFrame';

/** @typedef {{ play?: boolean }} MiniPlay */

/** @param {MiniPlay} props */
export function ControlHandoff({ play }) {
  return (
    <MiniFrame play={play}>
      <p className="lp-fade-up rounded-2xl bg-white px-3 py-1.5 text-xs text-[#171A19]">I need to speak to someone.</p>
      <p className="lp-fade-up mt-2 rounded-lg bg-[#FFF4D6] px-2 py-1 text-[0.7rem] font-semibold text-[#8A5A00]" style={{ animationDelay: '500ms' }}>
        Human requested
      </p>
      <p className="lp-fade-up mt-2 rounded-lg bg-[#E8F5F1] px-2 py-1 text-[0.7rem] font-semibold text-[#06715F]" style={{ animationDelay: '1000ms' }}>
        Owner notified
      </p>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function ControlRoles({ play }) {
  const rows = [
    { role: 'Admin', checks: [true, true, true] },
    { role: 'Support', checks: [true, true, false] },
    { role: 'Viewer', checks: [true, false, false] },
  ];
  return (
    <MiniFrame play={play}>
      <div className="grid grid-cols-4 gap-1 text-[0.6rem] text-[#8A938F]">
        <span />
        <span className="text-center">Chat</span>
        <span className="text-center">Users</span>
        <span className="text-center">Settings</span>
      </div>
      {rows.map((row, r) => (
        <div key={row.role} className="mt-1.5 grid grid-cols-4 items-center gap-1 text-xs">
          <span className="text-[#171A19]">{row.role}</span>
          {row.checks.map((on, c) => (
            <span
              key={`${row.role}-${c}`}
              className={`lp-fade-up mx-auto flex h-4 w-4 items-center justify-center rounded-full ${on ? 'bg-[#06715F] text-[0.55rem] text-white' : 'border border-[#D5DCD8]'}`}
              style={{ animationDelay: `${r * 280 + c * 80}ms` }}
            >
              {on ? '✓' : ''}
            </span>
          ))}
        </div>
      ))}
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function ControlLiveChat({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="grid grid-cols-[0.9fr_1.1fr] gap-2 text-[0.65rem]">
        <div className="space-y-1.5">
          {['IG · 2m', 'WA · 5m', 'FB · 12m'].map((row, i) => (
            <p key={row} className={`rounded-lg px-2 py-1 ${i === 0 ? 'bg-white font-semibold text-[#171A19]' : 'text-[#6B746F]'}`}>
              {row}
            </p>
          ))}
        </div>
        <div>
          <p className="text-[#5C6663]">Are you open tomorrow?</p>
          <p className="lp-fade-up mt-2 text-[#06715F]" style={{ animationDelay: '500ms' }}>
            AI replying…
          </p>
          <p className="lp-fade-up mt-2 text-[0.6rem] text-[#8A938F]" style={{ animationDelay: '1400ms' }}>
            Mohammad took over · 2:14 PM
          </p>
        </div>
      </div>
      <div className="lp-fade-up mt-3 flex gap-2" style={{ animationDelay: '1800ms' }}>
        <span className="rounded-full bg-[#06715F] px-3 py-1 text-[0.65rem] font-semibold text-white">Take over</span>
        <span className="rounded-full border border-[#06715F] px-3 py-1 text-[0.65rem] font-semibold text-[#06715F]">Assign</span>
      </div>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function ControlAssignment({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="flex items-center justify-between text-xs">
        <span className="rounded-lg bg-white px-2 py-1 text-[#8A938F]">Unassigned</span>
        <span className="text-[#06715F]">→</span>
        <span className="lp-fade-up rounded-lg bg-[#E8F5F1] px-2 py-1 font-semibold text-[#06715F]" style={{ animationDelay: '500ms' }}>
          Maya
        </span>
      </div>
      <p className="lp-fade-up mt-3 text-[0.7rem] font-semibold text-[#06715F]" style={{ animationDelay: '900ms' }}>
        ✓ Assigned just now
      </p>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function ControlLimits({ play }) {
  return (
    <MiniFrame play={play}>
      <ul className="space-y-1 text-[0.7rem] text-[#171A19]">
        <li>Message: 8k chars</li>
        <li>Day: 25 chats</li>
        <li>Week: 100 chats</li>
      </ul>
      <p className="mt-2 text-[0.65rem] text-[#5C6663]">Usage</p>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[#E4EBE8]">
        <div className="lp-fill h-full w-[70%] rounded-full bg-[#06715F]" style={{ transform: play ? undefined : 'scaleX(1)' }} />
      </div>
      <p className="lp-fade-up mt-2 text-[0.7rem] font-semibold text-[#06715F]" style={{ animationDelay: '900ms' }}>
        Credits protected
      </p>
    </MiniFrame>
  );
}
