import { LP_NET_CHANNEL_R, LP_NET_CHANNELS, LP_NET_VB } from './liveNetworkLayout';

/**
 * Channel logos pinned in viewBox % — same space as SVG lines.
 * Spine is drawn in the SVG underneath so it stays behind the marks.
 */
export default function LiveNetworkChannels() {
  const sizePct = ((LP_NET_CHANNEL_R * 2) / LP_NET_VB.w) * 100;

  return (
    <div className="lp-net-channels" aria-hidden="true">
      {LP_NET_CHANNELS.map((ch) => (
        <span
          key={ch.id}
          className="lp-net-channel"
          title={ch.label}
          style={{
            left: `${(ch.x / LP_NET_VB.w) * 100}%`,
            top: `${(ch.y / LP_NET_VB.h) * 100}%`,
            width: `${sizePct}%`,
          }}
        >
          <ch.Mark className="lp-net-channel-mark" />
        </span>
      ))}
    </div>
  );
}
