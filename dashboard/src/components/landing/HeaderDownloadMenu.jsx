import { useEffect, useId, useRef, useState } from 'react';
import { STORE_LINKS } from '../../constants/publicSite';

function AppleGlyph({ className = 'h-3.5 w-3.5' }) {
  return (
    <svg viewBox="0 0 16 16" className={className} aria-hidden="true" fill="currentColor">
      <path d="M12.5 10.4c-.03-.9.37-1.58.94-2.08-.52-.76-1.34-1.18-2.28-1.2-1-.1-1.9.58-2.38.58s-1.24-.56-2.08-.54c-1.07.03-2.06.62-2.6 1.58-1.12 1.94-.28 4.8.8 6.37.53.77 1.15 1.63 1.97 1.6.8-.03 1.1-.5 2.06-.5s1.23.5 2.08.48c.86-.01 1.4-.77 1.92-1.54.6-.88.85-1.74.86-1.78-.02 0-1.66-.64-1.7-2.47zM10.7 5.9c.44-.54.74-1.28.66-2.03-.64.04-1.4.43-1.86.96-.4.47-.76 1.23-.66 1.96.7.05 1.42-.36 1.86-.89z" />
    </svg>
  );
}

function PlayGlyph({ className = 'h-3.5 w-3.5' }) {
  return (
    <svg viewBox="0 0 16 16" className={className} aria-hidden="true" fill="currentColor">
      <path d="M2.2 1.6c-.13.22-.2.5-.2.84v11.12c0 .34.07.62.2.84l.06.04 6.3-6.44v-.16L2.26 1.56l-.06.04zm7.02 7.16 1.46-1.48-6.3-3.66 4.84 5.14zm1.46-1.48 1.7-1.74c.5-.5.5-.8.02-1.1L6.38 1.4l4.3 5.88zm0 1.8-4.3 5.88 6.02-3.5c.48-.28.48-.6-.02-1.1l-1.7-1.28z" />
    </svg>
  );
}

function PlayMark({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path fill="#00A0FF" d="M3.2 2.4v19.2L12.8 12z" />
      <path fill="#FFCE00" d="M12.8 12 3.2 21.6 18.4 14.4z" />
      <path fill="#00DC5A" d="M18.4 9.6 12.8 12l5.6 2.4c1.2.5 1.2 1.4 0 1.9L3.2 21.6 20.2 13c1.2-.6 1.2-1.6 0-2.2L3.2 2.4 18.4 9.6z" />
      <path fill="#FF3A44" d="M3.2 2.4 12.8 12 18.4 9.6z" />
    </svg>
  );
}

/**
 * @param {{
 *   store: { status: string, url?: string | null, blocker?: string },
 *   title: string,
 *   subtitle: string,
 *   icon: import('react').ReactNode,
 *   iconWrapClass: string,
 * }} props
 */
function StoreRow({ store, title, subtitle, icon, iconWrapClass }) {
  const live = store.status === 'live' && store.url;
  const inner = (
    <>
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${iconWrapClass}`}>
        {icon}
      </span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block text-sm font-semibold text-[#171A19]">{title}</span>
        <span className="block text-xs text-[#6B746F]">{subtitle}</span>
      </span>
      <span className="text-[#9AA39F]" aria-hidden="true">
        ›
      </span>
    </>
  );
  const className =
    'flex w-full items-center gap-3 rounded-xl px-1 py-2.5 text-left hover:bg-[#F7F8F5] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]';
  if (live && store.url) {
    return (
      <a href={store.url} className={className} target="_blank" rel="noopener noreferrer">
        {inner}
      </a>
    );
  }
  return (
    <div className={`${className} cursor-default`} title={store.blocker} aria-disabled="true">
      {inner}
    </div>
  );
}

export default function HeaderDownloadMenu() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const menuId = useId();

  useEffect(() => {
    if (!open) return undefined;
    /** @param {MouseEvent} event */
    const onPointer = (event) => {
      if (rootRef.current && event.target instanceof Node && !rootRef.current.contains(event.target)) setOpen(false);
    };
    /** @param {KeyboardEvent} event */
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div id="get-app" className="relative" ref={rootRef}>
      <button
        type="button"
        className="inline-flex items-center gap-2 rounded-full bg-[#06715F] px-3.5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#056655] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F] focus-visible:ring-offset-2"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
      >
        <AppleGlyph className="h-3.5 w-3.5 text-white" />
        <PlayGlyph className="h-3 w-3 text-white" />
        Download app
        <span className="text-[0.65rem] opacity-90" aria-hidden="true">
          ▾
        </span>
      </button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label="Download Linas AI"
          className="absolute right-0 z-50 mt-3 w-[20.5rem] rounded-2xl bg-white p-4 shadow-[0_18px_50px_rgba(23,26,25,0.14)] ring-1 ring-black/[0.06]"
        >
          <p className="px-1 pb-2 text-[0.8rem] font-semibold text-[#3A4240]">Download Linas AI</p>
          <StoreRow
            store={STORE_LINKS.appStore}
            title="Download on the App Store"
            subtitle="For iPhone and iPad"
            icon={<AppleGlyph className="h-5 w-5 text-white" />}
            iconWrapClass="bg-[#171A19] text-white"
          />
          <div className="mx-1 border-t border-[#EEEFEA]" />
          <StoreRow
            store={STORE_LINKS.playStore}
            title="Get it on Google Play"
            subtitle="For Android devices"
            icon={<PlayMark className="h-5 w-5" />}
            iconWrapClass="bg-[#F3F5F2]"
          />
        </div>
      ) : null}
    </div>
  );
}
