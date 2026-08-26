import { useEffect, useId, useRef, useState } from 'react';
import { STORE_LINKS } from '../../constants/publicSite';

function AppleGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 512 512" className={className} aria-hidden="true" fill="currentColor">
      <path d="M349.13 136.86c-40.32 0-57.36 19.24-85.44 19.24-28.79 0-50.75-19.1-85.69-19.1-34.2 0-70.67 20.88-93.83 56.45-32.52 50.16-27 144.63 25.67 225.11 18.84 28.81 44 61.12 77 61.47h.6c28.68 0 37.2-18.78 76.67-19h.6c38.88 0 46.68 18.89 75.24 18.89h.6c33-.35 59.51-36.15 78.35-64.85 13.56-20.64 18.6-31 29-54.35-76.19-28.92-88.43-136.93-13.08-178.34-23-28.8-55.32-45.48-85.79-45.48z" />
      <path d="M340.25 32c-24 1.63-52 16.91-68.4 36.86-14.88 18.08-27.12 44.9-22.32 70.91h1.92c25.56 0 51.72-15.39 67-35.11 14.72-18.77 25.88-45.37 21.8-72.66z" />
    </svg>
  );
}

/** White Play mark for the green header button. */
function PlayStoreGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="currentColor">
      <path d="M3.6 2.05v19.9c0 .7.76 1.14 1.36.78L20.7 13.4c.58-.34.58-1.22 0-1.56L4.96 1.27C4.36.91 3.6 1.35 3.6 2.05z" />
    </svg>
  );
}

/** Official Google Play logo (Ionicons paths + Google brand colors). */
function PlayStoreColor({ className = 'h-6 w-6' }) {
  return (
    <svg viewBox="0 0 512 512" className={className} aria-hidden="true">
      <path fill="#4285F4" d="M48 59.49v393a4.33 4.33 0 007.37 3.07L260 256 55.37 56.42A4.33 4.33 0 0048 59.49z" />
      <path fill="#EA4335" d="M345.8 174 89.22 32.64l-.16-.09c-4.42-2.4-8.62 3.58-5 7.06l201.13 192.32z" />
      <path fill="#34A853" d="M84.08 472.39c-3.64 3.48.56 9.46 5 7.06l.16-.09L345.8 338l-60.61-57.95z" />
      <path fill="#FBBC04" d="M449.38 231l-71.65-39.46L310.36 256l67.37 64.43L449.38 281c19.49-10.77 19.49-39.23 0-50z" />
    </svg>
  );
}

function ChevronRight() {
  return (
    <svg viewBox="0 0 12 12" className="h-3.5 w-3.5 text-[#9AA39F]" aria-hidden="true" fill="none">
      <path d="M4.2 2.2 8 6l-3.8 3.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * @param {{
 *   store: { status: string, url?: string | null, blocker?: string },
 *   title: string,
 *   subtitle: string,
 *   icon: import('react').ReactNode,
 * }} props
 */
function StoreRow({ store, title, subtitle, icon }) {
  const live = store.status === 'live' && store.url;
  const inner = (
    <>
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[0.85rem] bg-[#F3F5F2]">{icon}</span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block text-[0.92rem] font-semibold leading-tight text-[#171A19]">{title}</span>
        <span className="mt-0.5 block text-[0.78rem] text-[#6B746F]">{subtitle}</span>
      </span>
      <ChevronRight />
    </>
  );
  const className =
    'flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left transition-colors hover:bg-[#F7F8F5] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]';
  if (live && store.url) {
    return (
      <a href={store.url} className={className} target="_blank" rel="noopener noreferrer" role="menuitem">
        {inner}
      </a>
    );
  }
  return (
    <div className={`${className} cursor-default`} title={store.blocker} aria-disabled="true" role="menuitem">
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
        className="inline-flex h-10 items-center rounded-full bg-[#06715F] pl-3.5 pr-3.5 text-[0.9rem] font-semibold text-white shadow-[0_8px_18px_rgba(6,113,95,0.28)] hover:bg-[#056655] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F] focus-visible:ring-offset-2"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="inline-flex items-center gap-2">
          <AppleGlyph className="h-4 w-4 text-white" />
          <PlayStoreGlyph className="h-3.5 w-3.5 text-white" />
        </span>
        <span className="ml-2">Download app</span>
        <svg
          viewBox="0 0 12 12"
          className={`ml-1.5 h-3 w-3 opacity-90 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
          fill="none"
        >
          <path d="M2.2 4.2 6 8l3.8-3.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label="Download Linas AI"
          className="absolute right-0 z-50 mt-2.5 w-[21.5rem] rounded-[1.25rem] bg-white p-3.5 shadow-[0_22px_55px_rgba(23,26,25,0.16)] ring-1 ring-black/[0.06]"
        >
          <p className="px-2 pb-2.5 text-[0.82rem] font-semibold text-[#171A19]">Download Linas AI</p>
          <StoreRow
            store={STORE_LINKS.appStore}
            title="Download on the App Store"
            subtitle="For iPhone and iPad"
            icon={<AppleGlyph className="h-6 w-6 text-[#171A19]" />}
          />
          <div className="mx-2 my-0.5 border-t border-[#EEEFEA]" />
          <StoreRow
            store={STORE_LINKS.playStore}
            title="Get it on Google Play"
            subtitle="For Android devices"
            icon={<PlayStoreColor className="h-6 w-6" />}
          />
        </div>
      ) : null}
    </div>
  );
}
