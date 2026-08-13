import { useEffect, useState } from 'react';

import { tokenStore } from '../../auth/tokenStore';
import { fetchCmSetupProgress } from '../cm/cmProgressApi';
import { fetchUnifiedChats } from '../livechat/liveChatApi';
import { canViewRequests } from '../requests/requestsPermissions';
import { listRequests } from '../requests/requestsApi';

export type DrawerBadges = {
  aiSetupPercent: number | null;
  liveChatUnread: number;
  requestsPending: number;
};

const EMPTY: DrawerBadges = {
  aiSetupPercent: null,
  liveChatUnread: 0,
  requestsPending: 0,
};

/** Lightweight badge counts when the drawer opens — no polling while closed. */
export function useDrawerBadges(enabled: boolean, drawerOpen: boolean): DrawerBadges {
  const [badges, setBadges] = useState<DrawerBadges>(EMPTY);

  useEffect(() => {
    if (!enabled || !drawerOpen) return;
    let cancelled = false;

    void (async () => {
      const next: DrawerBadges = { ...EMPTY };

      await Promise.all([
        (async () => {
          try {
            const prog = await fetchCmSetupProgress();
            if (cancelled) return;
            const pct = prog.summary?.percent;
            next.aiSetupPercent = typeof pct === 'number' ? Math.round(pct) : null;
          } catch {
            /* keep null */
          }
        })(),
        (async () => {
          try {
            const data = await fetchUnifiedChats({ page: 1, pageSize: 50, filter: 'all' });
            if (cancelled || !data.success) return;
            next.liveChatUnread = data.chats.reduce(
              (sum, c) => sum + Math.max(0, c.unread_count ?? 0),
              0,
            );
          } catch {
            /* keep 0 */
          }
        })(),
        (async () => {
          try {
            const user = await tokenStore.getUser();
            if (cancelled || !canViewRequests(user)) return;
            const page = await listRequests({ limit: 1 });
            if (cancelled) return;
            const counts = page.counts ?? {};
            next.requestsPending =
              (counts.NEW ?? 0) + (counts.IN_REVIEW ?? 0) + (counts.WAITING_FOR_CUSTOMER ?? 0);
          } catch {
            /* keep 0 */
          }
        })(),
      ]);

      if (!cancelled) setBadges(next);
    })();

    return () => {
      cancelled = true;
    };
  }, [enabled, drawerOpen]);

  return badges;
}
