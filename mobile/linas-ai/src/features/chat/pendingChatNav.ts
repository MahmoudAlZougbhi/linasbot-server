/** In-memory handoff from module drawer → Owner chat (open / new). */

export type PendingChatNav =
  | { type: 'new' }
  | { type: 'open'; conversationId: string };

let pending: PendingChatNav | null = null;

export function queueNewChat(): void {
  pending = { type: 'new' };
}

export function queueOpenChat(conversationId: string): void {
  const id = conversationId.trim();
  pending = id ? { type: 'open', conversationId: id } : null;
}

export function takePendingChatNav(): PendingChatNav | null {
  const next = pending;
  pending = null;
  return next;
}
