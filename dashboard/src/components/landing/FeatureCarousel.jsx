import { useEffect, useRef, useState } from 'react';
import { useFeatureCarousel } from '../../hooks/useFeatureCarousel';
import { useMediaQuery } from '../../hooks/usePrefersReducedMotion';
import LinasStar from './LinasStar';
import { CardHead } from './cards/MiniFrame';

const CARD_PX = 280;
const GAP_PX = 16;

/**
 * @param {{
 *   id: string,
 *   kicker: string,
 *   title: string,
 *   accent: string,
 *   subtitle: string,
 *   cards: Array<{ id: string, title: string, description: string, core?: boolean, Mini: (p: {play: boolean}) => import('react').ReactNode }>,
 * }} props
 */
export default function FeatureCarousel({ id, kicker, title, accent, subtitle, cards }) {
  const { index, go, next, prev, pause, resume, reduced } = useFeatureCarousel(cards.length, 2);
  const mobile = useMediaQuery('(max-width: 767px)');
  const outerRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const trackRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const startX = useRef(0);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = outerRef.current;
    if (!el) return undefined;
    const sync = () => setWidth(el.clientWidth);
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!mobile) return;
    const node = trackRef.current?.children[index];
    if (node instanceof HTMLElement) {
      node.scrollIntoView({ inline: 'center', block: 'nearest', behavior: reduced ? 'auto' : 'smooth' });
    }
  }, [index, mobile, reduced]);

  const onScroll = () => {
    if (!mobile || !trackRef.current || !outerRef.current) return;
    const kids = [...trackRef.current.children];
    const mid = outerRef.current.scrollLeft + outerRef.current.clientWidth / 2;
    let best = 0;
    let dist = Infinity;
    kids.forEach((child, i) => {
      if (!(child instanceof HTMLElement)) return;
      const c = child.offsetLeft + child.offsetWidth / 2;
      const d = Math.abs(c - mid);
      if (d < dist) {
        dist = d;
        best = i;
      }
    });
    if (best !== index) go(best, true);
  };

  const x = width / 2 - CARD_PX / 2 - index * (CARD_PX + GAP_PX);

  return (
    <section
      id={id}
      className="scroll-mt-24 overflow-hidden py-16 sm:py-20"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          next();
        }
        if (event.key === 'ArrowLeft') {
          event.preventDefault();
          prev();
        }
      }}
      onMouseEnter={pause}
      onMouseLeave={resume}
      onFocusCapture={pause}
      onBlurCapture={resume}
      onTouchStart={pause}
      onTouchEnd={resume}
    >
      <div className="mx-auto max-w-6xl px-4 text-center sm:px-6">
        <p className="flex items-center justify-center gap-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#06715F]">
          {kicker}
          <LinasStar className="h-3.5 w-3.5" />
        </p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-[#171A19] sm:text-4xl">
          {title} <span className="text-[#06715F]">{accent}</span>
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-base text-[#6B746F]">{subtitle}</p>
      </div>

      <div className="relative mx-auto mt-10">
        <button type="button" onClick={prev} className="absolute left-3 top-1/2 z-10 hidden h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-[#E4E8E6] bg-white text-xl text-[#06715F] shadow-sm md:flex" aria-label="Previous capability">
          ‹
        </button>
        <button type="button" onClick={next} className="absolute right-3 top-1/2 z-10 hidden h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-[#E4E8E6] bg-white text-xl text-[#06715F] shadow-sm md:flex" aria-label="Next capability">
          ›
        </button>

        <div
          ref={outerRef}
          className={`lp-hide-scroll ${mobile ? 'snap-x snap-mandatory overflow-x-auto px-4 pb-3' : 'overflow-hidden px-4 md:px-16'}`}
          onScroll={mobile ? onScroll : undefined}
          onPointerDown={(e) => {
            startX.current = e.clientX;
            pause();
          }}
          onPointerUp={(e) => {
            const dx = e.clientX - startX.current;
            if (!mobile) {
              if (dx > 50) prev();
              else if (dx < -50) next();
            }
            resume();
          }}
        >
          <div
            ref={trackRef}
            className="flex items-stretch gap-4"
            style={
              mobile
                ? undefined
                : {
                    transform: `translateX(${x}px)`,
                    transition: reduced ? 'none' : 'transform 420ms cubic-bezier(.22,1,.36,1)',
                  }
            }
          >
            {cards.map((card, i) => {
              const active = i === index;
              const Mini = card.Mini;
              return (
                <article
                  key={card.id}
                  className={`w-[84vw] max-w-[20rem] shrink-0 rounded-[1.6rem] border bg-white p-5 md:w-[280px] md:max-w-none ${
                    mobile ? 'snap-center' : ''
                  } ${active ? 'border-[#06715F]/30 shadow-xl shadow-[#06715F]/10' : 'border-[#E6EBE8] shadow-sm'}`}
                  style={
                    mobile
                      ? undefined
                      : {
                          transform: `scale(${active ? 1.16 : 0.94})`,
                          opacity: active ? 1 : 0.78,
                          transition: reduced ? 'opacity 120ms linear' : 'transform 420ms cubic-bezier(.22,1,.36,1), opacity 420ms cubic-bezier(.22,1,.36,1)',
                        }
                  }
                  aria-hidden={!active}
                  aria-current={active ? 'true' : undefined}
                >
                  <CardHead title={card.title} description={card.description} core={card.core} />
                  <Mini play={Boolean(active && !reduced)} />
                </article>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-8 flex flex-col items-center gap-3">
        <div className="flex items-center gap-2">
          {cards.map((card, i) => (
            <button
              key={card.id}
              type="button"
              aria-label={`Show ${card.title}`}
              aria-current={i === index ? 'true' : undefined}
              onClick={() => go(i, true)}
              className={`h-2 rounded-full ${i === index ? 'w-7 bg-[#06715F]' : 'w-2 bg-[#D5DCD8]'}`}
            />
          ))}
        </div>
        <p className="text-sm text-[#8A938F]">Drag or use the arrows</p>
      </div>
    </section>
  );
}
