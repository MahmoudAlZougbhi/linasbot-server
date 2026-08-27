import { useEffect, useRef, useState } from 'react';
import { useCarouselWheel } from '../../hooks/useCarouselWheel';
import { useFeatureCarousel } from '../../hooks/useFeatureCarousel';
import LinasStar from './LinasStar';
import { CardHead } from './cards/MiniFrame';

const CARD_PX = 280;
/** Visible peek per stacked card — moderate overlap, not glued. */
const OVERLAP_PX = 88;

/**
 * @param {number} from
 * @param {number} to
 * @param {number} n
 */
function shortestDelta(from, to, n) {
  let delta = to - from;
  if (delta > n / 2) delta -= n;
  if (delta < -n / 2) delta += n;
  return delta;
}

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
  const n = cards.length;
  const { index, go, next, prev, pause, resume, reduced } = useFeatureCarousel(n, 2);
  const outerRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const lastIndex = useRef(index);
  const [width, setWidth] = useState(0);
  const [cardW, setCardW] = useState(CARD_PX);
  const [loopIndex, setLoopIndex] = useState(n + index);
  const [snap, setSnap] = useState(false);
  const stepPx = cardW - OVERLAP_PX;
  const wheel = useCarouselWheel({ index, go, pause, resume, stepPx });
  const { resetOffset } = wheel;
  const slides = [...cards, ...cards, ...cards];

  useEffect(() => {
    const el = outerRef.current;
    if (!el) return undefined;
    const sync = () => {
      setWidth(el.clientWidth);
      const first = el.querySelector('[data-lp-card]');
      if (first instanceof HTMLElement) setCardW(first.offsetWidth);
    };
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (index === lastIndex.current) return;
    const delta = shortestDelta(lastIndex.current, index, n);
    lastIndex.current = index;
    setLoopIndex((current) => current + delta);
    resetOffset();
  }, [index, n, resetOffset]);

  useEffect(() => {
    if (!snap) return undefined;
    const id = requestAnimationFrame(() => {
      requestAnimationFrame(() => setSnap(false));
    });
    return () => cancelAnimationFrame(id);
  }, [snap]);

  useEffect(() => {
    if (n <= 0) return undefined;
    if (loopIndex < n || loopIndex >= n * 2) {
      const id = window.setTimeout(() => {
        setSnap(true);
        setLoopIndex(((loopIndex % n) + n) % n + n);
      }, reduced ? 0 : 420);
      return () => window.clearTimeout(id);
    }
    return undefined;
  }, [loopIndex, n, reduced]);

  const x = width / 2 - cardW / 2 - loopIndex * stepPx + wheel.offset;
  const moving = wheel.dragging || snap || reduced;

  return (
    <section
      id={id}
      className="scroll-mt-24 py-16 sm:py-20"
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

      <div
        className="relative mx-auto mt-4"
        onMouseEnter={pause}
        onMouseLeave={() => {
          if (!wheel.held.current) resume();
        }}
      >
        <button
          type="button"
          onClick={prev}
          className="absolute left-3 top-1/2 z-20 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-[#E4E8E6] bg-white text-xl text-[#06715F] shadow-sm"
          aria-label="Previous capability"
        >
          ‹
        </button>
        <button
          type="button"
          onClick={next}
          className="absolute right-3 top-1/2 z-20 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-[#E4E8E6] bg-white text-xl text-[#06715F] shadow-sm"
          aria-label="Next capability"
        >
          ›
        </button>

        <div
          ref={outerRef}
          className={`overflow-x-hidden py-16 ${wheel.dragging ? 'cursor-grabbing select-none' : 'cursor-grab'}`}
          style={{ touchAction: 'none' }}
          onPointerDown={wheel.onPointerDown}
          onDragStart={(event) => event.preventDefault()}
        >
          <div
            className="flex items-center"
            style={{
              transform: `translateX(${x}px)`,
              transition: moving ? 'none' : 'transform 420ms cubic-bezier(.22,1,.36,1)',
            }}
          >
            {slides.map((card, i) => {
              const active = i === loopIndex;
              const dist = Math.abs(i - loopIndex);
              const Mini = card.Mini;
              return (
                <article
                  key={`${card.id}-${i}`}
                  data-lp-card=""
                  draggable={false}
                  className={`relative isolate w-[84vw] max-w-[20rem] shrink-0 rounded-[1.6rem] border bg-white p-5 md:w-[280px] md:max-w-none ${
                    active ? 'border-[#06715F]/35 shadow-[0_22px_44px_rgba(6,113,95,0.14)]' : 'border-[#E6EBE8] shadow-none'
                  }`}
                  style={{
                    marginRight: i === slides.length - 1 ? 0 : -OVERLAP_PX,
                    zIndex: active ? 30 : Math.max(1, 20 - dist),
                    transform: `scale(${active ? 1.2 : dist === 1 ? 0.97 : 0.94})`,
                    transformOrigin: 'center center',
                    opacity: 1,
                    filter: active ? 'none' : 'saturate(0.52) brightness(1.04) contrast(0.94)',
                    transition: moving
                      ? 'none'
                      : 'transform 420ms cubic-bezier(.22,1,.36,1), filter 420ms cubic-bezier(.22,1,.36,1), box-shadow 420ms cubic-bezier(.22,1,.36,1), border-color 420ms cubic-bezier(.22,1,.36,1)',
                  }}
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

      <div className="mt-2 flex flex-col items-center gap-3">
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
