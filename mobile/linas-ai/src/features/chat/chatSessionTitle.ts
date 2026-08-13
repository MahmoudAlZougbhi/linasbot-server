const DEFAULT_TITLES = new Set(['New chat', 'Chat', 'Untitled', 'Linas AI', '']);

export function isDefaultConversationTitle(title: string | null | undefined): boolean {
  return DEFAULT_TITLES.has((title || '').trim());
}

/** Match server auto_title_from_first_message — first user text, single line, max 60. */
export function autoTitleFromFirstMessage(content: string, maxLen = 60): string {
  const cleaned = String(content || '')
    .replace(/\r/g, '\n')
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');
  if (!cleaned) return 'New chat';
  if (cleaned.length <= maxLen) return cleaned;
  return cleaned.slice(0, maxLen).trimEnd();
}
