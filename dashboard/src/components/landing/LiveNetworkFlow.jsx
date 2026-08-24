import { useId } from 'react';
import { CHANNELS } from './ChannelIcons';
import CountUp from './CountUp';
import LinasStar from './LinasStar';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import './liveNetwork.css';

const IN_PATHS = [
  'M40 22 C 140 18, 220 78, 300 110',
  'M40 66 C 140 62, 222 92, 300 110',
  'M40 110 C 150 110, 230 110, 300 110',
  'M40 154 C 140 158, 222 128, 300 110',
  'M40 198 C 140 202, 220 142, 300 110',
];

const OUT_PATHS = [
  'M308 110 C 328 78, 340 46, 356 28',
  'M308 110 C 332 110, 344 110, 356 110',
  'M308 110 C 328 142, 340 174, 356 192',
];

/**
 * @param {{ pathId: string, delay: string, duration: string, reverse?: boolean, chip?: boolean }} props
 */
function Packet({ pathId, delay, duration, reverse = false, chip = false }) {
  return (
    <g>
      <animateMotion
        dur={duration}
        begin={delay}
        repeatCount="indefinite"
        rotate={chip ? '0' : 'auto'}
        keyPoints={reverse ? '1;0' : '0;1'}
        keyTimes="0;1"
        calcMode="linear"
      >
        <mpath href={`#${pathId}`} />
      </animateMotion>
      {chip ? (
        <>
          <rect className="lp-net-chip" x="-8" y="-5" width="16" height="10" rx="3" />
          <circle cx="-1" cy="0" r="1.5" fill="#06715F" />
        </>
      ) : (
        <circle className="lp-net-glow" r="2.4" />
      )}
    </g>
  );
}

/**
 * @param {{ replies: number | null }} props
 */
export default function LiveNetworkFlow({ replies }) {
  const uid = useId().replace(/:/g, '');
  const reduced = usePrefersReducedMotion();

  return (
    <div className="lp-net">
      <svg className="lp-net-svg" viewBox="0 0 360 220" fill="none" aria-hidden="true">
        {IN_PATHS.map((d, i) => (
          <path key={`in-${i}`} id={`${uid}-in-${i}`} className="lp-net-line" d={d} />
        ))}
        {OUT_PATHS.map((d, i) => (
          <path key={`out-${i}`} id={`${uid}-out-${i}`} className="lp-net-line" d={d} />
        ))}
        {!reduced
          ? IN_PATHS.map((_, i) => (
              <g key={`pkt-in-${i}`}>
                <Packet pathId={`${uid}-in-${i}`} delay={`${0.15 * i}s`} duration={`${3.1 + i * 0.18}s`} reverse chip={i % 2 === 0} />
                <Packet pathId={`${uid}-in-${i}`} delay={`${1.4 + i * 0.2}s`} duration={`${2.7 + i * 0.12}s`} reverse />
              </g>
            ))
          : null}
        {!reduced
          ? OUT_PATHS.map((_, i) => (
              <Packet key={`pkt-out-${i}`} pathId={`${uid}-out-${i}`} delay={`${0.3 * i}s`} duration={`${2.8 + i * 0.2}s`} chip={i === 1} />
            ))
          : null}
      </svg>

      <div className="absolute left-0 top-0 flex h-full flex-col justify-between py-1">
        {CHANNELS.map((ch) => (
          <span
            key={ch.id}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white shadow-[0_2px_8px_rgba(23,26,25,0.08)] ring-1 ring-[#E4E8E6]"
            title={ch.label}
          >
            <ch.Icon className="h-7 w-7" />
          </span>
        ))}
      </div>

      <div className="absolute left-[46%] top-[46%] -translate-x-1/2 -translate-y-1/2 text-center">
        <p className="leading-none">
          <CountUp value={replies} className="lp-net-num text-[3.6rem] font-bold tracking-tight sm:text-[4.6rem]" />
        </p>
        <p className="mt-2 text-sm text-[#5C6663]">Messages answered by Linas</p>
      </div>

      <div className="lp-net-orb absolute right-[14%] top-1/2 flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center">
        <span className="lp-net-orb-glow pointer-events-none absolute inset-[-0.55rem] rounded-full bg-[#3dffc2]/35 blur-md" />
        <span className="absolute inset-0 rounded-full bg-white shadow-[0_0_24px_rgba(61,255,194,0.55)] ring-1 ring-[#D7EFE8]" />
        <LinasStar className="relative h-8 w-8" color="#06715F" showMark={false} />
      </div>
    </div>
  );
}
