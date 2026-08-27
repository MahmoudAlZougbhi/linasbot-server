import { HERO_CHANNEL_MARKS } from './channelBrandMarks';

export default function HeroChannelRow() {
  return (
    <div className="mt-6 flex flex-nowrap gap-4 overflow-visible sm:gap-5">
      {HERO_CHANNEL_MARKS.map((ch) => (
        <div key={ch.id} className="flex w-[4.5rem] shrink-0 flex-col items-center gap-2 sm:w-[4.85rem]">
          <span className="flex h-[4.25rem] w-[4.25rem] items-center justify-center rounded-[1.35rem] bg-white shadow-[0_12px_30px_rgba(23,26,25,0.08)] ring-1 ring-black/[0.04] sm:h-[4.6rem] sm:w-[4.6rem]">
            <ch.Mark className="h-9 w-9 sm:h-10 sm:w-10" />
          </span>
          <span className="text-[0.7rem] font-medium tracking-tight text-[#5C6663] sm:text-[0.74rem]">{ch.label}</span>
        </div>
      ))}
    </div>
  );
}

export { HERO_CHANNEL_MARKS as HERO_CHANNELS };
