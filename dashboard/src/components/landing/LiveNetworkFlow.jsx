import { useCallback, useEffect, useState } from 'react';
import LiveNetworkBusiness from './liveNetwork/LiveNetworkBusiness';
import LiveNetworkChannels from './liveNetwork/LiveNetworkChannels';
import LiveNetworkDiagram from './liveNetwork/LiveNetworkDiagram';
import LiveNetworkOrb from './liveNetwork/LiveNetworkOrb';
import LiveNetworkReplies from './liveNetwork/LiveNetworkReplies';
import { LP_NET_VB } from './liveNetwork/liveNetworkLayout';
import './liveNetwork.css';

/**
 * Parts 2–5: channels → replies → orb → business (shared viewBox %).
 * Live-measures the replies glyph so IN/OUT paths stay tucked under its edges
 * for any formatted width (63, 109, 1.1k, 5.5m, …).
 * @param {{ replies: number | null, businesses: number | null }} props
 */
export default function LiveNetworkFlow({ replies, businesses }) {
  const [digitHalfW, setDigitHalfW] = useState(/** @type {number | null} */ (null));
  const [netEl, setNetEl] = useState(/** @type {HTMLElement | null} */ (null));
  const [digitEl, setDigitEl] = useState(/** @type {HTMLElement | null} */ (null));

  /** @type {(node: HTMLElement | null) => void} */
  const netRef = useCallback((node) => {
    setNetEl(node);
  }, []);

  /** @type {(node: HTMLElement | null) => void} */
  const onDigitNode = useCallback((node) => {
    setDigitEl(node);
  }, []);

  useEffect(() => {
    if (!netEl || !digitEl) return undefined;

    const measure = () => {
      const netBox = netEl.getBoundingClientRect();
      if (netBox.width < 8) return;

      // Prefer the painted SVG text bbox (glyph), not empty viewBox padding.
      const ink = digitEl.querySelector('.lp-net-bubble-num__svg-ink');
      let halfPx = digitEl.getBoundingClientRect().width / 2;
      if (ink instanceof SVGGraphicsElement) {
        try {
          const bbox = ink.getBBox();
          const ctm = ink.getScreenCTM();
          if (ctm && bbox.width > 2) {
            const sx = Math.hypot(ctm.a, ctm.b) || 1;
            halfPx = (bbox.width * sx) / 2;
          }
        } catch {
          /* keep element half-width */
        }
      }

      const halfSvg = (halfPx / netBox.width) * LP_NET_VB.w;
      // Cap keeps orb clearance; floor avoids tiny “0” leaving a visible gap.
      setDigitHalfW(Math.max(32, Math.min(150, halfSvg)));
    };

    measure();
    const ro = new ResizeObserver(() => {
      measure();
    });
    ro.observe(netEl);
    ro.observe(digitEl);
    // Count-up / format changes mutate text without always resizing the wrapper.
    const mo = new MutationObserver(() => {
      measure();
    });
    mo.observe(digitEl, { characterData: true, subtree: true, childList: true });

    return () => {
      ro.disconnect();
      mo.disconnect();
    };
  }, [netEl, digitEl, replies]);

  return (
    <div className="lp-net" aria-label="Live network activity" ref={netRef}>
      <LiveNetworkDiagram replies={replies} digitHalfW={digitHalfW} />
      <div className="lp-net-stage">
        <LiveNetworkChannels />
        <LiveNetworkReplies value={replies} onDigitNode={onDigitNode} />
        <LiveNetworkOrb />
        <LiveNetworkBusiness value={businesses} />
      </div>
    </div>
  );
}
