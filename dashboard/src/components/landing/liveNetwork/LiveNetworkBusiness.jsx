import CountUp from '../CountUp';
import { LP_NET_BUSINESS, LP_NET_CAPTION_Y, LP_NET_VB } from './liveNetworkLayout';

/** Part 5 — business count; always a real digit (0 when missing). */
/** @param {{ value: number | null }} props */
export default function LiveNetworkBusiness({ value }) {
  const n = value == null || Number.isNaN(value) ? 0 : Math.max(0, Math.floor(value));

  return (
    <>
      <div
        className="lp-net-business"
        style={{
          left: `${(LP_NET_BUSINESS.x / LP_NET_VB.w) * 100}%`,
          top: `${(LP_NET_BUSINESS.y / LP_NET_VB.h) * 100}%`,
        }}
        aria-busy={value == null || undefined}
      >
        <CountUp value={n} className="lp-net-business-num-html" />
      </div>
      <p
        className="lp-net-caption lp-net-caption--business"
        style={{
          left: `${(LP_NET_BUSINESS.x / LP_NET_VB.w) * 100}%`,
          top: `${(LP_NET_CAPTION_Y / LP_NET_VB.h) * 100}%`,
        }}
      >
        Business using Linas
      </p>
    </>
  );
}
