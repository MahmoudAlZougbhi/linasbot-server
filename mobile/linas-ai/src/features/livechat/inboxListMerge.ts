import type { LiveChatItem } from './liveChatTypes';

/**
 * Poll / page-1 refresh while older pages are already loaded: update overlapping
 * rows in place, prepend brand-new chats, never drop load-more rows.
 */
export function mergeInboxPollPage(prev: LiveChatItem[], page1: LiveChatItem[]): LiveChatItem[] {
  if (!prev.length) return page1;
  if (!page1.length) return prev;
  const pageById = new Map(page1.map((c) => [c.conversation_id, c]));
  const prevIds = new Set(prev.map((c) => c.conversation_id));
  const fresh = page1.filter((c) => !prevIds.has(c.conversation_id));
  const updated = prev.map((c) => pageById.get(c.conversation_id) ?? c);
  return [...fresh, ...updated];
}

/** Append load-more rows without duplicating conversation_id. */
export function appendInboxPage(prev: LiveChatItem[], page: LiveChatItem[]): LiveChatItem[] {
  if (!page.length) return prev;
  const seen = new Set(prev.map((c) => c.conversation_id));
  const merged = [...prev];
  for (const c of page) {
    if (!seen.has(c.conversation_id)) {
      seen.add(c.conversation_id);
      merged.push(c);
    }
  }
  return merged;
}
