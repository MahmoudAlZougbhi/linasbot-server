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

/** Keep already-loaded older messages; refresh the latest window from server. */
export function mergeLatestWindow(prev: ChatMessage[], latest: ChatMessage[]): ChatMessage[] {
  if (!latest.length) return prev;
  const latestIds = new Set(latest.map((m) => m.id));
  const firstHit = prev.findIndex((m) => latestIds.has(m.id));
  const older =
    firstHit > 0
      ? prev.slice(0, firstHit)
      : firstHit === 0
        ? []
        : prev.filter((m) => !m.id.startsWith('local-') && m.created_at < latest[0].created_at);
  const locals = prev.filter(
    (m) =>
      m.id.startsWith('local-') &&
      !latest.some((l) => l.role === 'user' && l.content === m.content),
  );
  return [...older, ...latest, ...locals];
}

export function prependOlderUnique(prev: ChatMessage[], older: ChatMessage[]): ChatMessage[] {
  if (!older.length) return prev;
  const seen = new Set(prev.map((m) => m.id));
  const fresh = older.filter((m) => !seen.has(m.id));
  return fresh.length ? [...fresh, ...prev] : prev;
}

/** Match streamed reply text to a persisted assistant message (prefix compare). */
export function messagesIncludeAssistantReply(
  messages: ChatMessage[],
  replyText: string,
): boolean {
  const needle = replyText.trim().slice(0, 80);
  if (!needle) return true;
  const short = needle.slice(0, 40);
  return messages.some(
    (m) => m.role === 'assistant' && !m.id.startsWith('local-') && m.content.includes(short),
  );
}
