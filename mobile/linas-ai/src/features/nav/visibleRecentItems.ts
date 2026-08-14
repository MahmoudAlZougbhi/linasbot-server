import type { HistoryItem } from './HistoryRows';

/** Active (non-archived) chats shown under Recent. */
export function visibleRecentItems(
  history: HistoryItem[],
  archivedIds: string[],
): HistoryItem[] {
  return history.filter((h) => !archivedIds.includes(h.id));
}
