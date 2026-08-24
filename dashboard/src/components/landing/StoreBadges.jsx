import { STORE_LINKS } from '../../constants/publicSite';

function AppleMark({ className = 'h-6 w-6' }) {
  return (
    <svg viewBox="0 0 16 16" className={className} aria-hidden="true" fill="currentColor">
      <path d="M12.5 10.4c-.03-.9.37-1.58.94-2.08-.52-.76-1.34-1.18-2.28-1.2-1-.1-1.9.58-2.38.58s-1.24-.56-2.08-.54c-1.07.03-2.06.62-2.6 1.58-1.12 1.94-.28 4.8.8 6.37.53.77 1.15 1.63 1.97 1.6.8-.03 1.1-.5 2.06-.5s1.23.5 2.08.48c.86-.01 1.4-.77 1.92-1.54.6-.88.85-1.74.86-1.78-.02 0-1.66-.64-1.7-2.47zM10.7 5.9c.44-.54.74-1.28.66-2.03-.64.04-1.4.43-1.86.96-.4.47-.76 1.23-.66 1.96.7.05 1.42-.36 1.86-.89z" />
    </svg>
  );
}

function PlayMark({ className = 'h-6 w-6' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path fill="#00A0FF" d="M3.2 2.4v19.2L12.8 12z" />
      <path fill="#FFCE00" d="M12.8 12 3.2 21.6 18.4 14.4z" />
      <path fill="#00DC5A" d="M18.4 9.6 12.8 12l5.6 2.4c1.2.5 1.2 1.4 0 1.9L3.2 21.6 20.2 13c1.2-.6 1.2-1.6 0-2.2L3.2 2.4 18.4 9.6z" />
      <path fill="#FF3A44" d="M3.2 2.4 12.8 12 18.4 9.6z" />
    </svg>
  );
}

function ArrowOut({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 16 16" className={className} aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M4.5 11.5 11.5 4.5M6.5 4.5h5v5" strokeLinecap="round" strokeLinejoin="round" />
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
    { key: 'ios', store: STORE_LINKS.appStore, top: 'Download on the', name: 'App Store', closeIcon: <AppleMark /> },
    { key: 'android', store: STORE_LINKS.playStore, top: 'Get it on', name: 'Google Play', closeIcon: <PlayMark /> },
  ];

  return (
    <div
      id={compact ? undefined : 'get-app'}
      className={`flex flex-wrap items-center gap-3 ${close ? 'flex-col items-stretch' : ''} ${compact ? '' : 'scroll-mt-24'}`}
      role="group"
      aria-label="Download Linas AI"
    >
      {items.map(({ key, store, top, name, closeIcon }) => {
        const live = store.status === 'live' && store.url;
        const className = close
          ? `inline-flex min-w-[15.5rem] items-center gap-3 rounded-[1.15rem] bg-white px-5 py-3.5 text-left text-[#171A19] shadow-[0_10px_28px_rgba(0,0,0,0.22)] ${live ? 'hover:bg-[#F4F7F5]' : 'cursor-default'}`
          : dark
            ? `inline-flex min-w-[10.5rem] items-center gap-3 rounded-xl bg-black px-4 py-2.5 text-left text-white ${live ? 'hover:bg-[#111]' : 'cursor-default'}`
            : `inline-flex min-w-[10.5rem] items-center gap-3 rounded-xl border border-[#E4E8E6] bg-white px-4 py-2.5 text-left ${live ? 'hover:border-[#06715F]/40' : 'cursor-default'}`;
        const inner = (
          <>
            {close ? (
              <span className="flex h-8 w-8 items-center justify-center text-[#171A19]">{closeIcon}</span>
            ) : (
              <span className="text-xl leading-none" aria-hidden="true">
                {key === 'ios' ? '' : '▶'}
              </span>
            )}
            <span className="flex-1">
              <span className={`block text-[0.62rem] tracking-wide ${close ? 'text-[#6B746F]' : dark ? 'text-white/70' : 'text-[#8A938F]'}`}>
                {top}
              </span>
              <span className={`block text-sm font-semibold ${close || !dark ? 'text-[#171A19]' : 'text-white'}`}>{name}</span>
            </span>
            {close ? <ArrowOut className="h-4 w-4 text-[#171A19]" /> : null}
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
