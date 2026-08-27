import { LP_NET_ORB, LP_NET_VB } from './liveNetworkLayout';

const ORB_SRC = '/brand/landing/live-network-ai-orb.png';

/** Part 4 — Karen AI orb (asset): lines from replies enter here, then leave to business. */
export default function LiveNetworkOrb() {
  return (
    <div
      className="lp-net-orb-shell"
      style={{
        left: `${(LP_NET_ORB.x / LP_NET_VB.w) * 100}%`,
        top: `${(LP_NET_ORB.y / LP_NET_VB.h) * 100}%`,
      }}
    >
      <img
        className="lp-net-orb-img"
        src={ORB_SRC}
        alt=""
        width={160}
        height={160}
        draggable={false}
      />
    </div>
  );
}
