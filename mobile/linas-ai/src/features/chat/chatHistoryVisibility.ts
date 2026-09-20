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
 * Apply a fresh list response without reshuffling rows the owner already sees.
 * Keep local optimistic ids in `retainIds` when the snapshot has not listed them yet.
 */
export function mergeListedHistory(
  prev: HistoryEntry[],
  next: HistoryEntry[],
  opts?: { retainIds?: string[] },
): HistoryEntry[] {
  if (!prev.length) return next;
  const retain = new Set(opts?.retainIds || []);
  const nextById = new Map(next.map((h) => [h.id, h]));
  const seen = new Set<string>();
  const merged: HistoryEntry[] = [];
  for (const p of prev) {
    const n = nextById.get(p.id);
    if (n) {
      merged.push(preferListedTitle(p, n));
      seen.add(p.id);
      continue;
    }
    if (retain.has(p.id)) {
      merged.push(p);
      seen.add(p.id);
    }
  }
  for (const n of next) {
    if (!seen.has(n.id)) merged.push(n);
  }
  return merged;
}

function preferListedTitle(prev: HistoryEntry, incoming: HistoryEntry): HistoryEntry {
  if (isWeakHistoryTitle(incoming.title) && !isWeakHistoryTitle(prev.title)) {
    return { ...incoming, title: prev.title };
  }
  return incoming;
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
