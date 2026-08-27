import { STORE_LINKS } from '../../constants/publicSite';

/** Official Apple logo glyph. */
function AppleMark({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 512 512" className={className} aria-hidden="true" fill="currentColor">
      <path d="M349.13 136.86c-40.32 0-57.36 19.24-85.44 19.24-28.79 0-50.75-19.1-85.69-19.1-34.2 0-70.67 20.88-93.83 56.45-32.52 50.16-27 144.63 25.67 225.11 18.84 28.81 44 61.12 77 61.47h.6c28.68 0 37.2-18.78 76.67-19h.6c38.88 0 46.68 18.89 75.24 18.89h.6c33-.35 59.51-36.15 78.35-64.85 13.56-20.64 18.6-31 29-54.35-76.19-28.92-88.43-136.93-13.08-178.34-23-28.8-55.32-45.48-85.79-45.48z" />
      <path d="M340.25 32c-24 1.63-52 16.91-68.4 36.86-14.88 18.08-27.12 44.9-22.32 70.91h1.92c25.56 0 51.72-15.39 67-35.11 14.72-18.77 25.88-45.37 21.8-72.66z" />
    </svg>
  );
}

/** Official Google Play mark (brand colors). */
function PlayMark({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 512 512" className={className} aria-hidden="true">
      <path fill="#4285F4" d="M48 59.49v393a4.33 4.33 0 007.37 3.07L260 256 55.37 56.42A4.33 4.33 0 0048 59.49z" />
      <path fill="#EA4335" d="M345.8 174 89.22 32.64l-.16-.09c-4.42-2.4-8.62 3.58-5 7.06l201.13 192.32z" />
      <path fill="#34A853" d="M84.08 472.39c-3.64 3.48.56 9.46 5 7.06l.16-.09L345.8 338l-60.61-57.95z" />
      <path fill="#FBBC04" d="M449.38 231l-71.65-39.46L310.36 256l67.37 64.43L449.38 281c19.49-10.77 19.49-39.23 0-50z" />
    </svg>
  );
}

/**
 * App Store / Google Play badges. Links only when a real listing URL exists.
 * @param {{ compact?: boolean, variant?: 'light' | 'dark' | 'hero' | 'close' }} props
 */
export default function StoreBadges({ compact = false, variant = 'light' }) {
  const dark = variant === 'dark' || variant === 'hero';
  const close = variant === 'close';
  const items = [
    { key: 'ios', store: STORE_LINKS.appStore, top: 'Download on the', name: 'App Store', Icon: AppleMark },
    { key: 'android', store: STORE_LINKS.playStore, top: 'Get it on', name: 'Google Play', Icon: PlayMark },
  ];

  return (
    <div
      id={compact ? undefined : 'get-app'}
      className={`flex flex-wrap items-center gap-2.5 ${close ? 'lp-store-close flex-col items-stretch' : ''} ${compact ? '' : 'scroll-mt-24'}`}
      role="group"
      aria-label="Download Linas AI"
    >
      {items.map(({ key, store, top, name, Icon }) => {
        const live = store.status === 'live' && store.url;
        const className = close
          ? `lp-store-close-btn ${live ? 'lp-store-close-btn--live' : 'lp-store-close-btn--idle'}`
          : dark
            ? `inline-flex min-w-[10.5rem] items-center gap-3 rounded-xl bg-black px-4 py-2.5 text-left text-white ${live ? 'hover:bg-[#111]' : 'cursor-default'}`
            : `inline-flex min-w-[10.5rem] items-center gap-3 rounded-xl border border-[#E4E8E6] bg-white px-4 py-2.5 text-left ${live ? 'hover:border-[#06715F]/40' : 'cursor-default'}`;
        const inner = close ? (
          <>
            <Icon className="lp-store-close-icon" />
            <span className="lp-store-close-copy">
              <span className="lp-store-close-top">{top}</span>
              <span className="lp-store-close-name">{name}</span>
            </span>
          </>
        ) : (
          <>
            <span className="text-xl leading-none" aria-hidden="true">
              {key === 'ios' ? '' : '▶'}
            </span>
            <span className="flex-1">
              <span className={`block text-[0.62rem] tracking-wide ${dark ? 'text-white/70' : 'text-[#8A938F]'}`}>{top}</span>
              <span className={`block text-sm font-semibold ${dark ? 'text-white' : 'text-[#171A19]'}`}>{name}</span>
            </span>
          </>
        );
        if (live && store.url) {
          return (
            <a key={key} href={store.url} className={className} target="_blank" rel="noopener noreferrer">
              {inner}
            </a>
          );
        }
        return (
          <div key={key} className={className} title={store.blocker || 'Store listing not published yet'} aria-disabled="true">
            {inner}
          </div>
        );
      })}
    </div>
  );
}
