import { useEffect, useRef, useState } from 'react';
import { HOW_IT_WORKS_STEPS } from '../../../constants/landingHowItWorks';
import { useMediaQuery, usePrefersReducedMotion } from '../../../hooks/usePrefersReducedMotion';
import HowItWorksCopy from '../HowItWorksCopy';
import HowItWorksStage from '../HowItWorksStage';
import '../howItWorks.css';

const SEGMENTS = HOW_IT_WORKS_STEPS.length;

export default function LandingHowItWorks() {
  const reduced = usePrefersReducedMotion();
  const mobile = useMediaQuery('(max-width: 767px)');
  const pin = !reduced && !mobile;
  const ref = useRef(/** @type {HTMLElement | null} */ (null));
  const [index, setIndex] = useState(2);

  useEffect(() => {
    if (!pin) return undefined;
    const onScroll = () => {
      const el = ref.current;
      if (!el) return;
      const scrolled = -el.getBoundingClientRect().top;
      const total = el.offsetHeight - window.innerHeight;
      if (total <= 0) return;
      const p = Math.min(1, Math.max(0, scrolled / total));
      setIndex(Math.min(SEGMENTS - 1, Math.floor(p * SEGMENTS + 1e-4)));
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, [pin]);

  useEffect(() => {
    HOW_IT_WORKS_STEPS.slice(index + 1, index + 3).forEach((item) => {
      const img = new Image();
      img.src = item.image;
    });
  }, [index]);

  const step = HOW_IT_WORKS_STEPS[index];
  if (!step) return null;
  const prev = HOW_IT_WORKS_STEPS[index - 1] || null;
  const next = HOW_IT_WORKS_STEPS[index + 1] || null;

  const frame = (
    <div className="mx-auto grid w-full max-w-6xl items-center gap-6 px-4 py-10 sm:px-6 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:gap-4">
      <HowItWorksCopy step={step} />
      <HowItWorksStage step={step} prev={prev} next={next} />
    </div>
  );

  if (!pin) {
    return (
      <section
        id="how-it-works"
        className="scroll-mt-24 bg-[#F4F6F3] py-16"
        onPointerDown={(event) => {
          event.currentTarget.dataset.startX = String(event.clientX);
        }}
        onPointerUp={(event) => {
          const start = Number(event.currentTarget.dataset.startX || 0);
          const dx = event.clientX - start;
          if (dx > 40) setIndex((i) => Math.max(0, i - 1));
          if (dx < -40) setIndex((i) => Math.min(SEGMENTS - 1, i + 1));
        }}
      >
        {frame}
        <div className="mx-auto mt-4 flex max-w-6xl items-center justify-center gap-2 px-4">
          {HOW_IT_WORKS_STEPS.map((row, i) => (
            <button
              key={row.n}
              type="button"
              aria-label={`Screen ${row.n}`}
              aria-current={i === index ? 'true' : undefined}
              className={`h-2 rounded-full ${i === index ? 'w-5 bg-[#06715F]' : 'w-2 bg-[#D5DCD8]'}`}
              onClick={() => setIndex(i)}
            />
          ))}
        </div>
      </section>
    );
  }

  return (
    <section id="how-it-works" ref={ref} className="relative bg-[#F4F6F3]" style={{ height: `${SEGMENTS * 85}vh` }}>
      <div className="sticky top-0 flex min-h-screen items-center overflow-visible">{frame}</div>
    </section>
  );
}
