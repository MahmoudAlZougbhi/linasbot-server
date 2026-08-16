import MiniFrame from './MiniFrame';

/** @typedef {{ play?: boolean }} MiniPlay */

/** @param {MiniPlay} props */
export function TeachAiSetup({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="flex items-center justify-between text-xs font-semibold text-[#06715F]">
        <span>83% ready</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#E4EBE8]">
        <div className="lp-fill h-full w-[83%] rounded-full bg-[#06715F]" style={{ transform: play ? undefined : 'scaleX(1)' }} />
      </div>
      <ul className="mt-3 space-y-2 text-sm text-[#171A19]">
        {[
          { label: 'Languages', delay: '0ms', on: true },
          { label: 'Opening Hours', delay: '180ms', on: true },
          { label: 'Off Days', delay: '360ms', on: false },
        ].map((row) => (
          <li key={row.label} className="flex items-center justify-between">
            <span>{row.label}</span>
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full border text-[0.65rem] ${
                row.on ? 'border-[#06715F] bg-[#06715F] text-white lp-fade-up' : 'border-[#D5DCD8] text-transparent'
              }`}
              style={{ animationDelay: row.delay }}
            >
              {row.on ? '✓' : ''}
            </span>
          </li>
        ))}
      </ul>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function TeachKnowledge({ play }) {
  const kinds = ['Text', 'Image', 'Link', 'Doc', 'Video'];
  return (
    <MiniFrame play={play}>
      <div className="grid grid-cols-5 gap-1 text-center">
        {kinds.map((label, i) => (
          <div key={label} className="lp-fade-up" style={{ animationDelay: `${i * 90}ms` }}>
            <div className="mx-auto flex h-9 w-9 items-center justify-center rounded-xl bg-white text-xs font-bold text-[#06715F] shadow-sm">
              {label[0]}
            </div>
            <p className="mt-1 text-[0.6rem] text-[#6B746F]">{label}</p>
          </div>
        ))}
      </div>
      <div className="lp-fade-up mt-3 flex items-center gap-2 rounded-xl bg-[#E8F5F1] px-3 py-2" style={{ animationDelay: '500ms' }}>
        <span className="text-[#06715F]">✦</span>
        <div>
          <p className="text-xs font-semibold text-[#06715F]">Knowledge saved</p>
          <p className="text-[0.65rem] text-[#5C6663]">25 items • Updated just now</p>
        </div>
      </div>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function TeachOwnerCopilot({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="lp-fade-up flex justify-end" style={{ animationDelay: '0ms' }}>
        <div>
          <p className="mb-1 text-right text-[0.65rem] text-[#8A938F]">You</p>
          <p className="rounded-2xl bg-[#D7EFE8] px-3 py-1.5 text-xs text-[#171A19]">We&apos;re closed tomorrow.</p>
        </div>
      </div>
      <div className="lp-fade-up mt-2" style={{ animationDelay: '700ms' }}>
        <p className="mb-1 text-[0.65rem] text-[#06715F]">Linas</p>
        <p className="text-xs text-[#171A19]">Done — I added an off day.</p>
      </div>
      <div className="lp-fade-up mt-3 inline-flex items-center gap-1 rounded-full bg-[#E8F5F1] px-2.5 py-1 text-[0.65rem] font-semibold text-[#06715F]" style={{ animationDelay: '1400ms' }}>
        ✓ Saved to Business Knowledge
      </div>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function TeachServices({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="space-y-2 text-xs">
        <div className="flex items-center justify-between text-[#171A19]">
          <span>Laser consultation · 30 min</span>
          <span className="font-semibold">$49</span>
        </div>
        <div className="flex items-center justify-between text-[#171A19]">
          <span>Full body · 90 min</span>
          <span className="font-semibold">$299</span>
        </div>
        <div className="lp-fade-up flex items-center justify-between rounded-lg bg-white px-2 py-1.5" style={{ animationDelay: '200ms' }}>
          <span className="text-[#8A938F]">New service</span>
          <span className="font-semibold text-[#06715F]">$199</span>
        </div>
      </div>
      <div className="lp-fade-up mt-3 flex items-center justify-between text-xs" style={{ animationDelay: '450ms' }}>
        <span className="text-[#5C6663]">Available</span>
        <span className="relative h-5 w-9 rounded-full bg-[#06715F]">
          <span className="absolute right-0.5 top-0.5 h-4 w-4 rounded-full bg-white" />
        </span>
      </div>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function TeachProducts({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="lp-fade-up mx-auto h-16 w-12 rounded-xl bg-gradient-to-b from-[#54C7AC] to-[#06715F]" />
      <p className="mt-2 text-center text-xs font-semibold text-[#171A19]">Hydra Calm Serum</p>
      <p className="text-center text-xs text-[#06715F]">$59</p>
      <div className="mt-2 flex justify-center gap-1.5">
        {['#06715F', '#C5CDCA', '#E4E8E6', '#8A938F'].map((c, i) => (
          <span
            key={c}
            className={`h-4 w-4 rounded-full lp-fade-up ${i === 0 ? 'ring-2 ring-[#06715F] ring-offset-1' : ''}`}
            style={{ background: c, animationDelay: `${200 + i * 80}ms` }}
          />
        ))}
      </div>
      <div className="mt-2 flex justify-center gap-2 text-[0.65rem]">
        <span className="lp-fade-up rounded-full border border-[#06715F] px-2 py-0.5 text-[#06715F]" style={{ animationDelay: '500ms' }}>
          30ml
        </span>
        <span className="rounded-full border border-[#D5DCD8] px-2 py-0.5 text-[#5C6663]">50ml</span>
      </div>
    </MiniFrame>
  );
}
