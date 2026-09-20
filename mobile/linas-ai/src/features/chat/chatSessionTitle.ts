const DEFAULT_TITLES = new Set(['New chat', 'Chat', 'Untitled', 'Linas AI', '']);

export function isDefaultConversationTitle(title: string | null | undefined): boolean {
  return DEFAULT_TITLES.has((title || '').trim());
}
