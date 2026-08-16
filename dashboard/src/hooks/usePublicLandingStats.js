import { useCallback, useEffect, useState } from 'react';

const POLL_MS = 20_000;

/**
 * Live public landing aggregates. Pauses while the tab is hidden.
 * @returns {null | {
 *   businesses_using_linas: number | null,
 *   messages_replied: number,
 *   comments_replied: number,
 *   ai_replies: number,
 *   requests: number | null,
 *   refresh_seconds?: number,
 * }}
 */
export function usePublicLandingStats() {
  const [stats, setStats] = useState(/** @type {any} */ (null));

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/public/landing-stats', { headers: { Accept: 'application/json' } });
      const body = await res.json();
      if (res.ok && body?.success) {
        setStats(body);
      }
    } catch {
      /* keep last honest snapshot */
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    /** @type {ReturnType<typeof setTimeout> | undefined} */
    let timer;

    const tick = async (force = false) => {
      if (cancelled) return;
      if (!force && document.visibilityState === 'hidden') return;
      await load();
      if (cancelled) return;
      if (document.visibilityState === 'hidden') return;
      timer = setTimeout(() => {
        void tick(false);
      }, POLL_MS);
    };

    const onVis = () => {
      if (document.visibilityState === 'visible') {
        void tick(true);
      } else if (timer) {
        clearTimeout(timer);
      }
    };

    void tick(true);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [load]);

  return stats;
}
