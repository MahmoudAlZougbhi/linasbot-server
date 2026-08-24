import MiniFrame from './MiniFrame';
import { CHANNELS } from '../ChannelIcons';

/** @typedef {{ play?: boolean }} MiniPlay */

const WORLD_LANGS = ['العربية', '中文', 'Español', 'Français', '日本語', 'Türkçe', 'हिन्दी', 'Deutsch'];

/** @param {MiniPlay} props */
export function ReplyCustomer({ play }) {
  return (
    <MiniFrame play={play}>
      <p className="text-[0.65rem] text-[#8A938F]">WhatsApp · 10:30 AM</p>
      <p className="mt-1 rounded-2xl bg-white px-3 py-1.5 text-xs leading-snug text-[#171A19] shadow-sm">
        I tanned yesterday — can I still do full-body laser this week? Any slots after 8pm Thursday?
      </p>
      <div className="lp-fade-up mt-2.5" style={{ animationDelay: '600ms' }}>
        <p className="text-[0.65rem] text-[#06715F]">Linas · 10:31 AM</p>
        <p className="mt-1 rounded-2xl bg-[#D7EFE8] px-3 py-1.5 text-xs leading-snug text-[#171A19]">
          Not until the tan fades — laser on tanned skin can burn. Thursday last slot is 6pm. I can hold Friday 10am.
        </p>
      </div>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function ReplyLanguage({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="flex flex-wrap gap-1">
        {WORLD_LANGS.map((label, i) => (
          <span
            key={label}
            className={`lp-fade-up rounded-full px-1.5 py-0.5 text-[0.58rem] font-semibold ${
              i === 0 ? 'bg-[#06715F] text-white' : 'bg-white text-[#5C6663]'
            }`}
            style={{ animationDelay: `${i * 90}ms` }}
          >
            {label}
          </span>
        ))}
      </div>
      <p className="mt-2 text-right text-xs leading-snug text-[#171A19]" dir="rtl">
        في عندكن ليزر جسم كامل؟ عندي بشرة حساسة
      </p>
      <p className="lp-fade-up mt-2 text-right text-xs leading-snug text-[#06715F]" dir="rtl" style={{ animationDelay: '700ms' }}>
        نعم — $299. للبشرة الحساسة منبلّش بـ patch test. في موعد الجمعة ١٠ صباحاً.
      </p>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function ReplyComments({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="rounded-xl bg-white px-2.5 py-2 shadow-sm">
        <p className="text-[0.6rem] font-semibold uppercase tracking-wide text-[#06715F]">You taught</p>
        <p className="mt-0.5 text-xs text-[#171A19]">Price questions → Private DM</p>
      </div>
      <p className="mt-2 text-[0.65rem] font-semibold text-[#5C6663]">Public comment</p>
      <p className="text-xs text-[#171A19]">How much is a full body session?</p>
      <p className="lp-fade-up mt-1.5 text-xs text-[#06715F]" style={{ animationDelay: '400ms' }}>
        Sending the details privately ✓
      </p>
      <div className="lp-fade-up mt-2 rounded-xl border border-[#06715F]/30 bg-white p-2" style={{ animationDelay: '1000ms' }}>
        <p className="text-[0.65rem] font-semibold text-[#06715F]">Private DM</p>
        <p className="mt-1 text-xs leading-snug text-[#171A19]">Full body is $299. Would you like to book?</p>
      </div>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function ReplyVoiceVision({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="flex items-center gap-2 rounded-full bg-white px-3 py-2">
        <span className="text-[#06715F]">▶</span>
        <span className="h-5 flex-1 rounded-sm bg-gradient-to-r from-[#06715F] via-[#54C7AC] to-[#06715F] opacity-80" />
        <span className="text-[0.65rem] text-[#5C6663]">0:12</span>
      </div>
      <img
        src="/brand/landing/customer-vision.jpg"
        alt=""
        className="lp-fade-up mt-2.5 h-28 w-full rounded-xl object-cover object-[center_20%] ring-1 ring-[#06715F]/20"
        style={{ animationDelay: '400ms' }}
      />
      <p className="mt-2 text-center text-[0.65rem] text-[#5C6663]">Can you treat this?</p>
      <p className="lp-fade-up mt-1 text-center text-xs text-[#06715F]" style={{ animationDelay: '1100ms' }}>
        Yes — pigmentation laser can help.
      </p>
    </MiniFrame>
  );
}

/** @param {MiniPlay} props */
export function ReplyChannels({ play }) {
  return (
    <MiniFrame play={play}>
      <div className="flex flex-wrap justify-center gap-x-3 gap-y-2.5">
        {CHANNELS.map((ch, i) => (
          <div key={ch.id} className="lp-fade-up w-[3.15rem] text-center" style={{ animationDelay: `${i * 160}ms` }}>
            <ch.Icon className="mx-auto h-11 w-11 rounded-[0.85rem] shadow-[0_6px_14px_rgba(23,26,25,0.16)]" />
            <p className="mt-1 text-[0.58rem] font-medium leading-tight text-[#171A19]">{ch.label}</p>
          </div>
        ))}
      </div>
    </MiniFrame>
  );
}
