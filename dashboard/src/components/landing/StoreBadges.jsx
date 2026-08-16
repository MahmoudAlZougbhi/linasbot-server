import { STORE_LINKS } from '../../constants/publicSite';

/**
 * App Store / Google Play badges. Links only when a real listing URL exists.
 * @param {{ compact?: boolean, variant?: 'light' | 'dark' | 'hero' }} props
 */
export default function StoreBadges({ compact = false, variant = 'light' }) {
  const dark = variant === 'dark' || variant === 'hero';
  const items = [
    { key: 'ios', store: STORE_LINKS.appStore, glyph: '', top: 'Download on the', name: 'App Store' },
    { key: 'android', store: STORE_LINKS.playStore, glyph: '▶', top: 'GET IT ON', name: 'Google Play' },
  ];

  return (
    <div
      id={compact ? undefined : 'get-app'}
      className={`flex flex-wrap items-center gap-3 ${compact ? '' : 'scroll-mt-24'}`}
      role="group"
      aria-label="Download Linas AI"
    >
      {items.map(({ key, store, glyph, top, name }) => {
        const live = store.status === 'live' && store.url;
        const className = dark
          ? `inline-flex min-w-[10.5rem] items-center gap-3 rounded-xl bg-black px-4 py-2.5 text-left text-white ${live ? 'hover:bg-[#111]' : 'cursor-default'}`
          : `inline-flex min-w-[10.5rem] items-center gap-3 rounded-xl border border-[#E4E8E6] bg-white px-4 py-2.5 text-left ${live ? 'hover:border-[#06715F]/40' : 'cursor-default'}`;
        const inner = (
          <>
            <span className="text-xl leading-none" aria-hidden="true">
              {glyph}
            </span>
            <span>
              <span className={`block text-[0.6rem] uppercase tracking-wide ${dark ? 'text-white/70' : 'text-[#8A938F]'}`}>{top}</span>
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
