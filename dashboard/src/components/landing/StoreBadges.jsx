import { STORE_LINKS } from '../../constants/publicSite';

/**
 * App Store / Google Play badges. Links only when a real listing URL exists.
 * @param {{ compact?: boolean }} props
 */
export default function StoreBadges({ compact = false }) {
  const items = [
    {
      key: 'ios',
      store: STORE_LINKS.appStore,
      badgeLabel: 'Download on the App Store',
      sub: 'iOS',
    },
    {
      key: 'android',
      store: STORE_LINKS.playStore,
      badgeLabel: 'Get it on Google Play',
      sub: 'Android',
    },
  ];

  return (
    <div
      id={compact ? undefined : 'get-app'}
      className={`flex flex-wrap items-center gap-3 ${compact ? '' : 'scroll-mt-24'}`}
      role="group"
      aria-label="Download Linas AI"
    >
      {items.map(({ key, store, badgeLabel, sub }) => {
        const live = store.status === 'live' && store.url;
        const className = `inline-flex min-w-[10.5rem] flex-col justify-center rounded-xl border px-4 py-2.5 text-left transition ${
          live
            ? 'border-[#6D4AFF]/40 bg-[#2A1B4A] text-white hover:bg-[#3D2A6D] focus-visible:ring-2 focus-visible:ring-[#6D4AFF]'
            : 'cursor-default border-[#E4DCF2] bg-white/80 text-[#2A1B4A]'
        }`;

        const inner = (
          <>
            <span className={`text-[0.65rem] font-semibold uppercase tracking-[0.14em] ${live ? 'text-[#C4B0FF]' : 'text-[#9B8BB5]'}`}>
              {sub}
            </span>
            <span className="text-sm font-bold leading-tight">{badgeLabel}</span>
            {!live && (
              <span className="mt-0.5 text-xs font-medium text-[#6B5B85]">Coming soon</span>
            )}
          </>
        );

        if (live) {
          return (
            <a
              key={key}
              href={store.url}
              className={className}
              target="_blank"
              rel="noopener noreferrer"
            >
              {inner}
            </a>
          );
        }

        return (
          <div
            key={key}
            className={className}
            title={store.blocker || 'Store listing not published yet'}
            aria-disabled="true"
          >
            {inner}
          </div>
        );
      })}
    </div>
  );
}
