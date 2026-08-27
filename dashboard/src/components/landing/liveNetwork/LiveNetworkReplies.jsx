import LiveNetworkBubbleNumber from './LiveNetworkBubbleNumber';
import { LP_NET_CAPTION_Y, LP_NET_REPLIES, LP_NET_VB } from './liveNetworkLayout';

/**
 * Part 3 — backend replies count with Karen bubble-mosaic fill.
 * @param {{ value: number | null, onDigitNode?: (node: HTMLElement | null) => void }} props
 */
export default function LiveNetworkReplies({ value, onDigitNode }) {
  return (
    <>
      <div
        className="lp-net-replies"
        style={{
          left: `${(LP_NET_REPLIES.x / LP_NET_VB.w) * 100}%`,
          top: `${(LP_NET_REPLIES.y / LP_NET_VB.h) * 100}%`,
        }}
      >
        <div ref={onDigitNode} className="lp-net-replies-digit">
          <LiveNetworkBubbleNumber value={value} />
        </div>
      </div>
      <p
        className="lp-net-caption lp-net-caption--replies"
        style={{
          left: `${(LP_NET_REPLIES.x / LP_NET_VB.w) * 100}%`,
          top: `${(LP_NET_CAPTION_Y / LP_NET_VB.h) * 100}%`,
        }}
      >
        Messages answered by Linas
      </p>
    </>
  );
}
