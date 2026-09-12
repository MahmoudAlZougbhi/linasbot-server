import { liveChatMessageFromSseData, type LiveChatSseEvent } from './liveChatSseParse';
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

function lastMessageFromEvent(data: Record<string, unknown>) {
  const msg = liveChatMessageFromSseData(data);
  const content = String(msg?.content || msg?.text || data.text || '').trim();
  const timestamp = String(msg?.timestamp || new Date().toISOString());
  const isUser = Boolean(msg?.is_user);
  return {
    last_message: { content, text: content, timestamp, is_user: isUser },
    last_message_text: content || undefined,
    last_activity: timestamp,
    last_message_at: timestamp,
    inbound: isUser,
  };
}

/**
 * Instant inbox row update for `new_message`. Unknown conversations return matched:false
 * so the caller can quiet-reload the server list (names/status) instead of inventing a row.
 */
export function applyInboxNewMessage(
  prev: LiveChatItem[],
  data: LiveChatSseEvent['data'],
  opts?: { openConversationId?: string | null },
): { chats: LiveChatItem[]; matched: boolean } {
  const conversationId = String(data.conversation_id || '').trim();
  if (!conversationId) return { chats: prev, matched: false };
  const idx = prev.findIndex((chat) => chat.conversation_id === conversationId);
  if (idx < 0) return { chats: prev, matched: false };
  const patch = lastMessageFromEvent(data);
  const open = Boolean(opts?.openConversationId && opts.openConversationId === conversationId);
  const current = prev[idx];
  let unread = Number(current.unread_count || 0);
  if (open) unread = 0;
  else if (patch.inbound) unread += 1;
  const updated: LiveChatItem = {
    ...current,
    last_message: patch.last_message,
    last_message_text: patch.last_message_text,
    last_activity: patch.last_activity,
    last_message_at: patch.last_message_at,
    unread_count: unread,
  };
  const rest = prev.filter((_, i) => i !== idx);
  return { chats: [updated, ...rest], matched: true };
}
