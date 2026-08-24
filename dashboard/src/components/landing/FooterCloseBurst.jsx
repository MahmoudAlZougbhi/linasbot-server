import { CHANNELS } from './ChannelIcons';
import LinasStar from './LinasStar';

const PATHS = [
  'M44 28 C 168 30, 238 108, 318 140',
  'M44 78 C 168 80, 242 122, 318 140',
  'M44 140 C 190 140, 250 140, 318 140',
  'M44 202 C 168 200, 242 158, 318 140',
  'M44 252 C 168 250, 238 172, 318 140',
];

export default function FooterCloseBurst() {
  return (
    <div className="relative mx-auto h-[17.5rem] w-full max-w-[28rem]">
      <span className="lp-close-aura" aria-hidden="true" />
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 420 280" fill="none" aria-hidden="true">
        {PATHS.map((d) => (
          <path key={d} className="lp-close-flow" d={d} />
        ))}
      </svg>
      <div className="absolute left-0 top-0 flex h-full flex-col justify-between py-0.5">
        {CHANNELS.map((ch) => (
          <span
            key={ch.id}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-[#071614] shadow-[0_0_18px_rgba(61,255,194,0.2)] ring-1 ring-white/10"
            title={ch.label}
          >
            <ch.Icon className="h-7 w-7" />
          </span>
        ))}
      </div>
      <div className="lp-close-star-glow absolute right-0 top-1/2 flex h-[9.2rem] w-[9.2rem] -translate-y-1/2 items-center justify-center">
        <span className="absolute inset-0 rounded-full bg-[#3dffc2]/25 blur-3xl" />
        <span className="absolute inset-5 rotate-45 bg-[#3dffc2]/20 blur-2xl" />
        <LinasStar
          className="relative h-[6.1rem] w-[6.1rem] drop-shadow-[0_0_26px_rgba(61,255,194,0.95)]"
          color="#3dffc2"
          showMark={false}
        />
      </div>
    </div>
  );
}
