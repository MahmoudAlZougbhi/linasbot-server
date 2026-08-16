import { useEffect, useRef, useState } from 'react';
import { HOW_IT_WORKS_STEPS } from '../../../constants/landingHowItWorks';
import { useMediaQuery, usePrefersReducedMotion } from '../../../hooks/usePrefersReducedMotion';

const SEGMENTS = HOW_IT_WORKS_STEPS.length;

function FlowPill({ flow }) {
  return (
    <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-[#E4E8E6] bg-white px-4 py-2 text-sm text-[#06715F] shadow-sm">
      <span className="h-2.5 w-2.5 rounded-full bg-[#06715F]" />
      {flow.map((step, i) => (
        <span key={step} className="flex items-center gap-2">
          {i > 0 ? <span className="text-[#9AA39F]">→</span> : null}
          <span className={i === 0 ? 'font-semibold' : ''}>{step}</span>
        </span>
      ))}
    </div>
  );
}

function Story({ step }) {
  return (
    <div>
      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#06715F]">+ How it works</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-[#171A19] sm:text-4xl">One app. Every step clear.</h2>
      <div className="relative mt-10">
        <p className="text-7xl font-semibold text-[#D7EFE8]">{step.n}</p>
        <p className="mt-1 text-sm font-semibold uppercase tracking-[0.14em] text-[#06715F]">{step.kicker}</p>
        <h3 className="mt-3 text-2xl font-semibold text-[#171A19]">{step.title}</h3>
        <p className="mt-3 max-w-md text-base leading-relaxed text-[#5C6663]">{step.body}</p>
        <FlowPill flow={step.flow} />
      </div>
    </div>
  );
}

function Phone({ step, reduced }) {
  return (
    <img
      src={step.image}
      alt={step.alt}
      width={880}
      height={1021}
      className="mx-auto h-auto w-full max-w-[28rem] object-contain"
      style={{ transition: reduced ? 'opacity 120ms linear' : 'opacity 420ms cubic-bezier(.22,1,.36,1), transform 420ms cubic-bezier(.22,1,.36,1)' }}
    />
  );
}

function Progress({ index }) {
  const pct = ((index + 1) / SEGMENTS) * 100;
  return (
    <div className="mt-10 max-w-sm">
      <div className="h-1.5 overflow-hidden rounded-full bg-[#E4EBE8]">
        <div className="h-full rounded-full bg-[#06715F] lp-ease" style={{ width: `${pct}%`, transitionDuration: '420ms' }} />
      </div>
      <p className="mt-2 text-sm text-[#5C6663]">
        {HOW_IT_WORKS_STEPS[index].n} / {String(SEGMENTS).padStart(2, '0')}
      </p>
    </div>
  );
}

export default function LandingHowItWorks() {
  const reduced = usePrefersReducedMotion();
  const mobile = useMediaQuery('(max-width: 767px)');
  const pin = !reduced && !mobile;
  const ref = useRef(/** @type {HTMLElement | null} */ (null));
  const [index, setIndex] = useState(0);

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

  const step = HOW_IT_WORKS_STEPS[index];

  useEffect(() => {
    HOW_IT_WORKS_STEPS.slice(index + 1, index + 3).forEach((item) => {
      const img = new Image();
      img.src = item.image;
    });
  }, [index]);

  if (!pin) {
    const item = HOW_IT_WORKS_STEPS[index];
    return (
      <section
        id="how-it-works"
        className="scroll-mt-24 bg-[#F7F8F5] py-16"
        onPointerUp={(event) => {
          const el = event.currentTarget;
          const start = Number(el.dataset.startX || 0);
          const dx = event.clientX - start;
          if (dx > 40) setIndex((i) => Math.max(0, i - 1));
          if (dx < -40) setIndex((i) => Math.min(SEGMENTS - 1, i + 1));
        }}
        onPointerDown={(event) => {
          event.currentTarget.dataset.startX = String(event.clientX);
        }}
      >
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <Phone step={item} reduced={reduced} />
          <div className="mt-6">
            <Story step={item} />
            <Progress index={index} />
          </div>
          <div className="mt-6 flex items-center justify-between gap-3">
            <button
              type="button"
              className="rounded-full border border-[#E4E8E6] bg-white px-4 py-2 text-sm font-semibold text-[#171A19]"
              onClick={() => setIndex((i) => Math.max(0, i - 1))}
            >
              Previous
            </button>
            <div className="flex gap-1.5">
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
            <button
              type="button"
              className="rounded-full border border-[#E4E8E6] bg-white px-4 py-2 text-sm font-semibold text-[#171A19]"
              onClick={() => setIndex((i) => Math.min(SEGMENTS - 1, i + 1))}
            >
              Next
            </button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section id="how-it-works" ref={ref} className="relative bg-[#F7F8F5]" style={{ height: `${SEGMENTS * 85}vh` }}>
      <div className="sticky top-0 flex min-h-screen items-center">
        <div className="mx-auto grid w-full max-w-6xl items-center gap-10 px-4 py-10 sm:px-6 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <div key={step.n} className="lp-fade-up">
            <Story step={step} />
            <Progress index={index} />
          </div>
          <div key={`${step.n}-img`} className="lp-fade-up" style={{ transform: reduced ? undefined : 'translateY(-24px)' }}>
            <Phone step={step} reduced={reduced} />
          </div>
        </div>
      </div>
    </section>
  );
}
