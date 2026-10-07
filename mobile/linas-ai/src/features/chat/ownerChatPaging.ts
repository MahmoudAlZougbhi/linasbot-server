import type { ChatMessage } from '../../api/types';

/** Initial / load-more page size for owner conversations (20–30 band). */
export const OWNER_MESSAGE_PAGE = 25;

export function conversationMessagesUrl(
  conversationId: string,
  opts?: { limit?: number; before?: string },
): string {
  const limit = opts?.limit ?? OWNER_MESSAGE_PAGE;
  const params = new URLSearchParams({ limit: String(limit) });
  if (opts?.before) params.set('before', opts.before);
  return `/api/owner-ai/conversations/${conversationId}?${params.toString()}`;
}

function sameVisibleTurn(a: ChatMessage, b: ChatMessage): boolean {
  const left = a.content.trim();
  return Boolean(left) && a.role === b.role && left === b.content.trim();
}

/**
 * Refresh from the server page without dropping bubbles the screen already showed.
 * A short page (or a stale read) must not erase Sol's earlier replies.
 */
export function mergeLatestWindow(prev: ChatMessage[], latest: ChatMessage[]): ChatMessage[] {
  if (!latest.length) return prev;
  const serverIds = new Set(latest.map((m) => m.id));
  const kept = prev.filter((m) => {
    if (serverIds.has(m.id)) return false;
    if (m.id.startsWith('local-') && latest.some((l) => sameVisibleTurn(l, m))) return false;
    return true;
  });
  return [...kept, ...latest].sort(
    (a, b) => a.created_at - b.created_at || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  );
}

export function prependOlderUnique(prev: ChatMessage[], older: ChatMessage[]): ChatMessage[] {
  if (!older.length) return prev;
  const seen = new Set(prev.map((m) => m.id));
  const fresh = older.filter((m) => !seen.has(m.id));
  return fresh.length ? [...fresh, ...prev] : prev;
}

/** True when the newest assistant bubble is already this reply. Older bubbles do not count. */
export function messagesIncludeAssistantReply(
  messages: ChatMessage[],
  replyText: string,
): boolean {
  const needle = replyText.trim();
  if (!needle) return true;
  const head = needle.slice(0, 80);
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (!message || message.role !== 'assistant') continue;
    const body = message.content.trim();
    return body === needle || body.startsWith(head);
  }
  return false;
}
