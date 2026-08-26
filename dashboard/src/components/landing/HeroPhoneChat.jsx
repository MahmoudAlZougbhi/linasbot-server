import { useEffect, useRef } from 'react';
import LinasStar from './LinasStar';
import useHeroChatPlayback from './useHeroChatPlayback';

function StatusIcons() {
  return (
    <span className="flex items-center gap-[3px] text-[#171A19]" aria-hidden="true">
      <svg viewBox="0 0 18 12" className="h-2.5 w-[1.05rem]" fill="currentColor">
        <rect x="0" y="7" width="3" height="5" rx="0.6" />
        <rect x="5" y="5" width="3" height="7" rx="0.6" />
        <rect x="10" y="2.5" width="3" height="9.5" rx="0.6" />
        <rect x="15" y="0" width="3" height="12" rx="0.6" />
      </svg>
      <svg viewBox="0 0 16 12" className="h-2.5 w-3.5" fill="currentColor">
        <path d="M8 9.4a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8zm0-3.3c1.6 0 3.1.6 4.2 1.7l-1.1 1.1A4.1 4.1 0 0 0 8 7.6c-1.1 0-2.1.4-2.9 1.2L4 7.8A5.8 5.8 0 0 1 8 6.1zm0-3.3c2.5 0 4.8 1 6.5 2.7L13.4 7A7.3 7.3 0 0 0 8 4.3 7.3 7.3 0 0 0 2.6 7L1.5 5.5A9.3 9.3 0 0 1 8 2.8z" />
      </svg>
      <svg viewBox="0 0 25 12" className="h-2.5 w-[1.45rem]" fill="currentColor">
        <rect x="0.6" y="1.2" width="20.5" height="9.6" rx="2" fill="none" stroke="currentColor" strokeWidth="1.2" />
        <rect x="2.2" y="2.8" width="16.2" height="6.4" rx="1" />
        <rect x="21.8" y="4" width="1.8" height="4" rx="0.6" />
      </svg>
    </span>
  );
}

function TypingBubble() {
  return (
    <div className="flex items-start gap-1.5">
      <LinasStar className="mt-2 h-4 w-4 shrink-0" />
      <div>
        <p className="mb-1 text-[0.62rem] font-semibold text-[#171A19]">Linas</p>
        <p className="inline-flex items-center rounded-[1.15rem] rounded-bl-md bg-white px-3 py-2.5 shadow-[0_2px_8px_rgba(23,26,25,0.06)] ring-1 ring-black/[0.04]">
          <span className="lp-typing" aria-label="Linas is typing">
            <span />
            <span />
            <span />
          </span>
        </p>
      </div>
    </div>
  );
}

/**
 * @param {{ line: { role: string, text: string } }} props
 */
function ChatRow({ line }) {
  if (line.role === 'you') {
    return (
      <div className="flex justify-end">
        <p className="max-w-[13.6rem] rounded-[1.15rem] rounded-br-md bg-[#E4EDE9] px-3 py-2 text-[0.78rem] leading-snug text-[#171A19]">
          {line.text}
        </p>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-1.5">
      <LinasStar className="mt-2 h-4 w-4 shrink-0" />
      <div className="min-w-0">
        <p className="mb-1 text-[0.62rem] font-semibold text-[#171A19]">Linas</p>
        <p className="max-w-[13.6rem] rounded-[1.15rem] rounded-bl-md bg-white px-3 py-2 text-[0.78rem] leading-snug text-[#171A19] shadow-[0_2px_8px_rgba(23,26,25,0.06)] ring-1 ring-black/[0.04]">
          {line.text}
        </p>
      </div>
    </div>
  );
}

export default function HeroPhoneChat() {
  const { lines, typing } = useHeroChatPlayback();
  const scrollerRef = useRef(/** @type {HTMLDivElement | null} */ (null));

  useEffect(() => {
    const node = scrollerRef.current;
    if (!node) return;
    if (typeof node.scrollTo === 'function') {
      node.scrollTo({ top: node.scrollHeight, behavior: 'smooth' });
    } else {
      node.scrollTop = node.scrollHeight;
    }
  }, [lines, typing]);

  return (
    <div className="relative z-[1] w-[16.75rem] shrink-0 rounded-[2.7rem] bg-[#1A1C1B] p-[0.42rem] shadow-[0_40px_80px_rgba(23,26,25,0.28)] lg:w-[21.25rem] xl:w-[22.5rem]">
      <div className="relative flex h-[36.5rem] flex-col overflow-hidden rounded-[2.28rem] bg-[#F3F6F4] lg:h-[44rem] xl:h-[46rem]">
        <div
          className="absolute left-1/2 top-[0.68rem] z-[2] h-[1.32rem] w-[5.8rem] -translate-x-1/2 rounded-full bg-[#1A1C1B]"
          aria-hidden="true"
        />
        <div className="relative z-[1] flex items-center justify-between px-7 pt-3.5 text-[0.72rem] font-semibold text-[#171A19]">
          <span>9:41</span>
          <StatusIcons />
        </div>
        <div className="mt-0.5 flex items-center border-b border-black/[0.04] px-2.5 pb-2.5">
          <span className="flex h-8 w-8 items-center justify-center text-[#171A19]" aria-hidden="true">
            <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none">
              <path
                d="M12.5 4.5 6.5 10l6 5.5"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          <p className="flex flex-1 items-center justify-center gap-1.5 pr-8 text-[0.98rem] font-semibold text-[#171A19]">
            <LinasStar className="h-4 w-4" />
            Linas
          </p>
        </div>
        <div
          ref={scrollerRef}
          className="lp-hide-scroll min-h-0 flex-1 space-y-2.5 overflow-y-auto px-3 py-2.5"
          aria-live="polite"
        >
          {lines.map((line, index) => (
            <ChatRow key={`${line.role}-${index}`} line={line} />
          ))}
          {typing ? <TypingBubble /> : null}
        </div>
        <div className="px-3 pb-2 pt-1">
          <div className="flex items-center gap-1 rounded-full bg-white py-1 pl-1 pr-1 shadow-[0_4px_14px_rgba(23,26,25,0.08)] ring-1 ring-[#E6E8E4]">
            <span className="flex h-8 w-8 items-center justify-center text-xl font-light text-[#6B746F]" aria-hidden="true">
              +
            </span>
            <span className="flex-1 text-[0.78rem] text-[#8A938F]">Work with Linas</span>
            <span className="pr-0.5 text-[#6B746F]" aria-hidden="true">
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none">
                <path
                  d="M10 3.4c1.4 0 2.4 1.1 2.4 2.5v4.2c0 1.4-1 2.5-2.4 2.5s-2.4-1.1-2.4-2.5V5.9c0-1.4 1-2.5 2.4-2.5Z"
                  stroke="currentColor"
                  strokeWidth="1.6"
                />
                <path
                  d="M5.6 10.2a4.4 4.4 0 0 0 8.8 0M10 14.6V16.6"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#06715F] text-white" aria-hidden="true">
              <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="currentColor">
                <path d="M10 3.2 4.6 8.4a1 1 0 1 0 1.4 1.4L9 7.8V16a1 1 0 1 0 2 0V7.8l3 2a1 1 0 1 0 1.4-1.4L10 3.2z" />
              </svg>
            </span>
          </div>
          <div className="mx-auto mt-2.5 h-[4px] w-[7rem] rounded-full bg-[#171A19]/18" aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}
