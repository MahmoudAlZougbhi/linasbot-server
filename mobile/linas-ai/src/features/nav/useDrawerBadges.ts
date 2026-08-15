import { useEffect, useState } from 'react';

import { tokenStore } from '../../auth/tokenStore';
import { fetchCmSetupProgress, summarizeHubProgress } from '../cm/cmProgressApi';
import { fetchUnifiedChats } from '../livechat/liveChatApi';
import { canViewRequests } from '../requests/requestsPermissions';
import { listRequests } from '../requests/requestsApi';
import {
  EMPTY_DRAWER_BADGES,
  clearDrawerSessionCache,
  getCachedDrawerBadges,
  setCachedDrawerBadges,
  type DrawerBadgeSnapshot,
} from './drawerSessionCache';

export type DrawerBadges = DrawerBadgeSnapshot;

let badgesInFlight: Promise<DrawerBadges> | null = null;

async function refreshDrawerBadges(): Promise<DrawerBadges> {
  if (badgesInFlight) return badgesInFlight;

  badgesInFlight = (async () => {
    const next: DrawerBadges = { ...getCachedDrawerBadges() };
    await Promise.all([
      (async () => {
        try {
          const prog = await fetchCmSetupProgress();
          const rows = prog.progress ?? [];
          if (rows.length) {
            next.aiSetupPercent = summarizeHubProgress(rows).percent;
          } else if (typeof prog.summary?.percent === 'number') {
            next.aiSetupPercent = Math.round(prog.summary.percent);
          }
        } catch {
          /* keep last known percent */
        }
      })(),
      (async () => {
        try {
          const data = await fetchUnifiedChats({ page: 1, pageSize: 50, filter: 'all' });
          if (!data.success) return;
          next.liveChatUnread = data.chats.reduce(
            (sum, c) => sum + Math.max(0, c.unread_count ?? 0),
            0,
          );
        } catch {
          /* keep last known unread */
        }
      })(),
      (async () => {
        try {
          const user = await tokenStore.getUser();
          if (!canViewRequests(user)) return;
          const page = await listRequests({ limit: 1 });
          const counts = page.counts ?? {};
          next.requestsPending =
            (counts.NEW ?? 0) + (counts.IN_REVIEW ?? 0) + (counts.WAITING_FOR_CUSTOMER ?? 0);
        } catch {
          /* keep last known pending */
        }
      })(),
    ]);
    setCachedDrawerBadges(next);
    return next;
  })().finally(() => {
    badgesInFlight = null;
  });

  return badgesInFlight;
}

/** Session-cached badge counts. Prefetch while authenticated; refresh on drawer open. */
export function useDrawerBadges(enabled: boolean, drawerOpen: boolean): DrawerBadges {
  const [badges, setBadges] = useState<DrawerBadges>(getCachedDrawerBadges);

  useEffect(() => {
    if (!enabled) {
      clearDrawerSessionCache();
      setBadges(EMPTY_DRAWER_BADGES);
      return;
    }
    setBadges(getCachedDrawerBadges());
    let cancelled = false;
    void refreshDrawerBadges().then((next) => {
      if (!cancelled) setBadges(next);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  useEffect(() => {
    if (!enabled || !drawerOpen) return;
    let cancelled = false;
    void refreshDrawerBadges().then((next) => {
      if (!cancelled) setBadges(next);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled, drawerOpen]);

  return badges;
}
