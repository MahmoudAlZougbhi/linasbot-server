/**
 * Merge a voice transcript into an existing composer draft.
 * Appends with a space when needed; preserves trailing whitespace/newlines.
 */
export function appendVoiceTranscript(existing: string, transcript: string): string {
  const next = transcript.trim();
  if (!next) return existing;
  if (!existing) return next;
  if (/\s$/.test(existing)) return `${existing}${next}`;
  return `${existing} ${next}`;
}
