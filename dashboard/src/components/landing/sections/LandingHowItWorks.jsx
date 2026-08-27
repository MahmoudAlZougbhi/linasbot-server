import { useEffect, useRef, useState } from 'react';
import { HOW_IT_WORKS_EYEBROW, HOW_IT_WORKS_HEADLINE, HOW_IT_WORKS_STEPS } from '../../../constants/landingHowItWorks';
import { usePrefersReducedMotion } from '../../../hooks/usePrefersReducedMotion';
import HowItWorksCopy from '../HowItWorksCopy';
import HowItWorksNav from '../HowItWorksNav';
import HowItWorksStage from '../HowItWorksStage';
import '../howItWorks.css';

const SEGMENTS = HOW_IT_WORKS_STEPS.length;
const WHEEL_STEP = 55;

/**
 * Page scroll moves the section normally.
 * Wheel / swipe on the white card flips through the 13 screens.
 */
export default function LandingHowItWorks() {
  const reduced = usePrefersReducedMotion();
  const panelRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const indexRef = useRef(2);
  const wheelAcc = useRef(0);
  const [index, setIndex] = useState(2);

  useEffect(() => {
    indexRef.current = index;
  }, [index]);

  useEffect(() => {
    HOW_IT_WORKS_STEPS.slice(index + 1, index + 3).forEach((item) => {
      const img = new Image();
      img.src = item.image;
    });
  }, [index]);

  useEffect(() => {
    if (reduced) return undefined;
    const panel = panelRef.current;
    if (!panel) return undefined;

    /** @param {WheelEvent} event */
    const onWheel = (event) => {
      const dy = event.deltaY;
      if (dy === 0) return;
      const current = indexRef.current;
      const atStart = current <= 0 && dy < 0;
      const atEnd = current >= SEGMENTS - 1 && dy > 0;
      // At the edges, let the page keep scrolling past the section.
      if (atStart || atEnd) {
        wheelAcc.current = 0;
        return;
      }

      event.preventDefault();
      wheelAcc.current += dy;
      if (wheelAcc.current >= WHEEL_STEP) {
        wheelAcc.current = 0;
        setIndex((i) => Math.min(SEGMENTS - 1, i + 1));
      } else if (wheelAcc.current <= -WHEEL_STEP) {
        wheelAcc.current = 0;
        setIndex((i) => Math.max(0, i - 1));
      }
    };

    panel.addEventListener('wheel', onWheel, { passive: false });
    return () => panel.removeEventListener('wheel', onWheel);
  }, [reduced]);

  const step = HOW_IT_WORKS_STEPS[index];
  if (!step) return null;

  return (
    <section id="how-it-works" className="hiw-section scroll-mt-24">
      <div className="hiw-shell">
        <header className="hiw-header">
          <p className="hiw-eyebrow">{HOW_IT_WORKS_EYEBROW}</p>
          <h2 className="hiw-headline">{HOW_IT_WORKS_HEADLINE}</h2>
        </header>

        <div
          ref={panelRef}
          className="hiw-panel"
          onPointerDown={(event) => {
            event.currentTarget.dataset.startX = String(event.clientX);
            event.currentTarget.dataset.startY = String(event.clientY);
          }}
          onPointerUp={(event) => {
            const startX = Number(event.currentTarget.dataset.startX || 0);
            const startY = Number(event.currentTarget.dataset.startY || 0);
            const dx = event.clientX - startX;
            const dy = event.clientY - startY;
            if (Math.abs(dx) < 40 && Math.abs(dy) < 40) return;
            // Prefer vertical swipe inside the card for screen flips.
            if (Math.abs(dy) >= Math.abs(dx)) {
              if (dy < -40) setIndex((i) => Math.min(SEGMENTS - 1, i + 1));
              if (dy > 40) setIndex((i) => Math.max(0, i - 1));
              return;
            }
            if (dx > 40) setIndex((i) => Math.max(0, i - 1));
            if (dx < -40) setIndex((i) => Math.min(SEGMENTS - 1, i + 1));
          }}
        >
          <HowItWorksCopy step={step} total={SEGMENTS} />
          <HowItWorksStage step={step} />
          <HowItWorksNav index={index} onSelect={setIndex} />
        </div>

        <p className="hiw-scroll-hint">
          <span className="hiw-scroll-mouse" aria-hidden="true" />
          Scroll the card to explore
        </p>
      </div>
    </section>
  );
}
