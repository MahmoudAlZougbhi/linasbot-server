import type { HistoryItem } from './HistoryRows';

export type DrawerBadgeSnapshot = {
  aiSetupPercent: number | null;
  liveChatUnread: number;
  requestsPending: number;
};

export const EMPTY_DRAWER_BADGES: DrawerBadgeSnapshot = {
  aiSetupPercent: null,
  liveChatUnread: 0,
  requestsPending: 0,
};

type RecentsSnapshot = { history: HistoryItem[]; archivedIds: string[] };

let recents: RecentsSnapshot = { history: [], archivedIds: [] };
let badges: DrawerBadgeSnapshot = { ...EMPTY_DRAWER_BADGES };

export function getCachedDrawerRecents(): RecentsSnapshot {
  return recents;
}

/** Keep last known titles. Do not replace a filled list with an empty bootstrap. */
export function rememberDrawerRecents(history: HistoryItem[], archivedIds: string[]): void {
  if (history.length === 0 && recents.history.length > 0) return;
  recents = { history, archivedIds };
}

/** API / mutation result is source of truth, including a real empty list. */
export function replaceDrawerRecents(history: HistoryItem[], archivedIds: string[]): void {
  recents = { history, archivedIds };
}

export function getCachedDrawerBadges(): DrawerBadgeSnapshot {
  return badges;
}

export function setCachedDrawerBadges(next: DrawerBadgeSnapshot): void {
  badges = next;
}

export function clearDrawerSessionCache(): void {
  recents = { history: [], archivedIds: [] };
  badges = { ...EMPTY_DRAWER_BADGES };
}
