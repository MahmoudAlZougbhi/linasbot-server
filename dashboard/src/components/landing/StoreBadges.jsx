import { STORE_LINKS } from '../../constants/publicSite';

/**
 * App Store / Google Play badges. Links only when a real listing URL exists.
 * Design ZIP download section uses dark “Coming soon on …” badges.
 * @param {{ compact?: boolean, variant?: 'light' | 'dark' }} props
 */
export default function StoreBadges({ compact = false, variant = 'light' }) {
  const dark = variant === 'dark';
  const items = [
    {
      key: 'ios',
      store: STORE_LINKS.appStore,
      badgeLabel: dark ? 'Coming soon on the App Store' : 'Download on the App Store',
      sub: 'iOS',
      glyph: '',
    },
    {
      key: 'android',
      store: STORE_LINKS.playStore,
      badgeLabel: dark ? 'Coming soon on Google Play' : 'Get it on Google Play',
      sub: 'Android',
      glyph: '▶',
    },
  ];

  return (
    <div
      id={compact ? undefined : 'get-app'}
      className={`flex flex-wrap items-center gap-3 ${compact ? '' : 'scroll-mt-24'}`}
      role="group"
      aria-label="Download Linas AI"
    >
      {items.map(({ key, store, badgeLabel, sub, glyph }) => {
        const live = store.status === 'live' && store.url;
        const className = dark
          ? `inline-flex min-w-[11rem] items-center gap-3 rounded-xl border border-white/25 bg-black px-4 py-3 text-left text-white ${
              live ? 'hover:border-white/50' : 'cursor-default opacity-95'
            }`
          : `inline-flex min-w-[10.5rem] flex-col justify-center rounded-xl border px-4 py-2.5 text-left transition ${
              live
                ? 'border-[#06715F]/35 bg-[#171A19] text-white hover:bg-black focus-visible:ring-2 focus-visible:ring-[#06715F]'
                : 'cursor-default border-[#E4E8E6] bg-white text-[#171A19]'
            }`;

        const inner = dark ? (
          <>
            <span className="text-lg leading-none" aria-hidden="true">
              {glyph}
            </span>
            <span className="text-sm font-medium leading-snug">{live ? store.label : badgeLabel}</span>
          </>
        ) : (
          <>
            <span className={`text-[0.65rem] font-semibold uppercase tracking-[0.14em] ${live ? 'text-[#54C7AC]' : 'text-[#8A938F]'}`}>
              {sub}
            </span>
            <span className="text-sm font-bold leading-tight">{store.label}</span>
            {!live && <span className="mt-0.5 text-xs font-medium text-[#5C6663]">Coming soon</span>}
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
