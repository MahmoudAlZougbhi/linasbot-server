import MiniFrame from './MiniFrame';
import { CHANNELS } from '../ChannelIcons';

export function ReplyCustomer({ play }) {
  return (
    <MiniFrame play={play}>
      <p className="text-[0.65rem] text-[#8A938F]">10:30 AM</p>
      <p className="mt-1 rounded-2xl bg-white px-3 py-1.5 text-xs text-[#171A19] shadow-sm">Are you open tomorrow?</p>
      <div className="lp-fade-up mt-3" style={{ animationDelay: '600ms' }}>
        <p className="text-[0.65rem] text-[#06715F]">Linas · 10:31 AM</p>
        <p className="mt-1 rounded-2xl bg-[#D7EFE8] px-3 py-1.5 text-xs text-[#171A19]">We&apos;re open from 9 AM to 6 PM.</p>
      </div>
    </MiniFrame>
  );
}

export function ReplyLanguage({ play }) {
  const langs = ['AR', 'EN', 'FR', 'Arabizi'];
  return (
    <MiniFrame play={play}>
      <div className="flex gap-1.5">
        {langs.map((code, i) => (
          <span
            key={code}
            className={`lp-fade-up rounded-full px-2 py-0.5 text-[0.65rem] font-semibold ${
              code === 'EN' ? 'bg-[#06715F] text-white' : 'bg-white text-[#5C6663]'
            }`}
            style={{ animationDelay: `${i * 180}ms` }}
          >
            {code}
          </span>
        ))}
      </div>
      <p className="mt-3 text-xs text-[#171A19]">Are you open tomorrow?</p>
      <p className="lp-fade-up mt-2 text-xs text-[#06715F]" style={{ animationDelay: '700ms' }}>
        Êtes-vous ouvert demain ?
      </p>
      <p className="lp-fade-up mt-1 text-xs text-[#5C6663]" style={{ animationDelay: '1100ms' }}>
        Btfet7u bukra?
      </p>
    </MiniFrame>
  );
}

export function ReplyComments({ play }) {
  return (
    <MiniFrame play={play}>
      <p className="text-[0.65rem] font-semibold text-[#5C6663]">Public comment</p>
      <p className="mt-1 text-xs text-[#171A19]">How much is a full body session?</p>
      <p className="lp-fade-up mt-2 text-xs text-[#06715F]" style={{ animationDelay: '400ms' }}>
        I sent the details by DM +
      </p>
      <div className="lp-fade-up mt-3 rounded-xl border border-dashed border-[#06715F]/40 bg-white p-2" style={{ animationDelay: '1100ms' }}>
        <p className="text-[0.65rem] font-semibold text-[#06715F]">Private DM</p>
        <p className="mt-1 text-xs text-[#171A19]">Full body is $299. Would you like to book?</p>
      </div>
      <p className="lp-fade-up mt-2 text-[0.65rem] font-semibold text-[#06715F]" style={{ animationDelay: '1800ms' }}>
        ✓ Replied privately
      </p>
    </MiniFrame>
  );
}

export function ReplyVoiceVision({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="flex items-center gap-2 rounded-full bg-white px-3 py-2">
        <span className="text-[#06715F]">▶</span>
        <span className="h-5 flex-1 rounded-sm bg-gradient-to-r from-[#06715F] via-[#54C7AC] to-[#06715F] opacity-80" />
        <span className="text-[0.65rem] text-[#5C6663]">0:12</span>
      </div>
      <div className="lp-fade-up relative mx-auto mt-3 h-14 w-12 rounded-lg bg-[#D7EFE8]" style={{ animationDelay: '500ms' }}>
        <span className="absolute -left-1 -top-1 h-3 w-3 border-l border-t border-[#06715F]" />
        <span className="absolute -right-1 -top-1 h-3 w-3 border-r border-t border-[#06715F]" />
        <span className="absolute -bottom-1 -left-1 h-3 w-3 border-b border-l border-[#06715F]" />
        <span className="absolute -bottom-1 -right-1 h-3 w-3 border-b border-r border-[#06715F]" />
      </div>
      <p className="lp-fade-up mt-3 text-center text-xs text-[#171A19]" style={{ animationDelay: '1400ms' }}>
        Yes — it&apos;s available.
      </p>
    </MiniFrame>
  );
}

export function ReplyChannels({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="flex flex-wrap justify-center gap-3">
        {CHANNELS.map((ch, i) => (
          <div key={ch.id} className="lp-fade-up text-center" style={{ animationDelay: `${i * 220}ms` }}>
            <ch.Icon className="mx-auto h-8 w-8" />
            <p className="mt-1 text-[0.6rem] text-[#5C6663]">{ch.label}</p>
          </div>
        ))}
      </div>
    </MiniFrame>
  );
}
