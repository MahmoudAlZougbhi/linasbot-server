export type HistoryEntry = { id: string; title: string; archived?: boolean };

type ListedConversation = {
  id: string;
  title: string;
  archived?: boolean;
  has_user_message?: boolean;
};

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
