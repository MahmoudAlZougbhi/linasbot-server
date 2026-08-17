export type HistoryEntry = { id: string; title: string; archived?: boolean };

type ListedConversation = {
  id: string;
  title: string;
  archived?: boolean;
  has_user_message?: boolean;
};

const WEAK_TITLES = new Set(['New chat', 'Chat', 'Untitled', 'Linas AI', '']);

function isWeakHistoryTitle(title: string | null | undefined): boolean {
  return WEAK_TITLES.has((title || '').trim());
}

/** History/recent only includes threads after the first user turn. */
export function listedHistoryEntries(conversations: ListedConversation[]): HistoryEntry[] {
  return conversations
    .filter((c) => c.has_user_message !== false)
    .map((c) => ({
      id: c.id,
      title: c.title,
      archived: Boolean(c.archived),
    }));
}

/**
 * Apply a fresh list response without letting a stale/default title wipe a
 * better title already shown for the same conversation id.
 */
export function mergeListedHistory(prev: HistoryEntry[], next: HistoryEntry[]): HistoryEntry[] {
  if (!prev.length) return next;
  const prevById = new Map(prev.map((h) => [h.id, h]));
  return next.map((n) => {
    const p = prevById.get(n.id);
    if (p && isWeakHistoryTitle(n.title) && !isWeakHistoryTitle(p.title)) {
      return { ...n, title: p.title };
    }
    return n;
  });
}

export function conversationHasUserTurn(messages: Array<{ role: string }>): boolean {
  return messages.some((m) => m.role === 'user');
}

export function upsertStartedHistoryEntry(prev: HistoryEntry[], entry: HistoryEntry): HistoryEntry[] {
  if (prev.some((h) => h.id === entry.id)) {
    return prev.map((h) =>
      h.id === entry.id ? { ...h, title: entry.title, archived: entry.archived ?? h.archived } : h,
    );
  }
  return [entry, ...prev];
}

export function dropUnstartedHistoryEntry(
  prev: HistoryEntry[],
  conversationId: string | null,
  messages: Array<{ role: string }>,
): HistoryEntry[] {
  if (!conversationId || conversationHasUserTurn(messages)) return prev;
  return prev.filter((h) => h.id !== conversationId);
}
