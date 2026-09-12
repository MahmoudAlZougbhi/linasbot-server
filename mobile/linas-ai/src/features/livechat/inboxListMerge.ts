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
  const isUser =
    typeof msg?.is_user === 'boolean' ? msg.is_user : String(data.role || '').toLowerCase() === 'user';
  return {
    last_message: { content, text: content, timestamp, is_user: isUser },
    last_message_text: content || undefined,
    last_activity: timestamp,
    last_message_at: timestamp,
    inbound: isUser,
  };
}

function eventConversationId(data: Record<string, unknown>): string {
  return String(data.conversation_id || '').trim();
}

function eventUserId(data: Record<string, unknown>): string {
  return String(data.user_id || '').trim();
}

function eventDisplayName(data: Record<string, unknown>, fallback: string): string {
  const name = String(data.user_name || data.name || data.phone || '').trim();
  return name || fallback;
}

function findInboxIndex(prev: LiveChatItem[], data: Record<string, unknown>): number {
  const conversationId = eventConversationId(data);
  const userId = eventUserId(data);
  if (conversationId) {
    const byConv = prev.findIndex((chat) => chat.conversation_id === conversationId);
    if (byConv >= 0) return byConv;
  }
  if (!userId) return -1;
  return prev.findIndex((chat) => chat.user_id === userId);
}

function unreadFromEvent(
  data: Record<string, unknown>,
  current: number,
  inbound: boolean,
  open: boolean,
): number {
  if (open) return 0;
  if (typeof data.unread_count === 'number' && Number.isFinite(data.unread_count)) {
    return Math.max(0, Number(data.unread_count));
  }
  if (inbound) return current + 1;
  return current;
}

/**
 * Instant inbox row update for `new_message` / `new_conversation`.
 * Unknown conversations are inserted from the event (ids + preview from the
 * server event, not a placeholder). Caller skip-refetch when matched.
 */
export function applyInboxNewMessage(
  prev: LiveChatItem[],
  data: LiveChatSseEvent['data'],
  opts?: { openConversationId?: string | null },
): { chats: LiveChatItem[]; matched: boolean } {
  const conversationId = eventConversationId(data);
  const userId = eventUserId(data);
  if (!conversationId && !userId) return { chats: prev, matched: false };
  const patch = lastMessageFromEvent(data);
  const idx = findInboxIndex(prev, data);
  const open = Boolean(
    opts?.openConversationId &&
      (opts.openConversationId === conversationId || (idx >= 0 && prev[idx].conversation_id === opts.openConversationId)),
  );
  if (idx < 0) {
    const id = conversationId || userId;
    const unread = unreadFromEvent(data, 0, patch.inbound, open);
    const created: LiveChatItem = {
      conversation_id: conversationId || userId,
      user_id: userId || conversationId,
      user_name: eventDisplayName(data, id),
      user_phone: String(data.phone || '').trim() || undefined,
      unread_count: unread,
      channel: data.channel != null ? String(data.channel) : undefined,
      last_message: patch.last_message,
      last_message_text: patch.last_message_text,
      last_activity: patch.last_activity,
      last_message_at: patch.last_message_at,
    };
    return { chats: [created, ...prev], matched: true };
  }
  const current = prev[idx];
  const unread = unreadFromEvent(data, Number(current.unread_count || 0), patch.inbound, open);
  const name = eventDisplayName(data, '');
  const hasPreview = Boolean(patch.last_message_text);
  const updated: LiveChatItem = {
    ...current,
    user_name: name || current.user_name,
    last_message: hasPreview ? patch.last_message : current.last_message,
    last_message_text: patch.last_message_text || current.last_message_text,
    last_activity: hasPreview ? patch.last_activity : current.last_activity,
    last_message_at: patch.last_message_at || current.last_message_at,
    unread_count: unread,
  };
  const rest = prev.filter((_, i) => i !== idx);
  return { chats: [updated, ...rest], matched: true };
}
