import type { LiveChatItem, LiveChatMessage } from './liveChatTypes';

export type LiveChatSseEvent = {
  type: string;
  data: Record<string, unknown>;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function firstText(...vals: unknown[]): string {
  for (const value of vals) {
    if (value == null || typeof value === 'object') continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return '';
}

function parseSseBlock(block: string): LiveChatSseEvent | null {
  let type = 'message';
  const dataLines: string[] = [];
  for (const rawLine of block.split('\n')) {
    const line = rawLine.replace(/\r$/, '');
    if (!line || line.startsWith(':')) continue;
    if (line.startsWith('event:')) type = line.slice(6).trim() || type;
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  const raw = dataLines.join('\n');
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return { type, data: parsed as Record<string, unknown> };
    }
    return { type, data: { value: parsed } };
  } catch {
    return { type, data: { raw } };
  }
}

/** Progressive XHR SSE: keep an incomplete trailing block in `carry`. */
export function drainLiveChatSse(carry: string, chunk: string): { carry: string; events: LiveChatSseEvent[] } {
  const parts = (carry + chunk).split('\n\n');
  const nextCarry = parts.pop() || '';
  const events: LiveChatSseEvent[] = [];
  for (const part of parts) {
    const parsed = parseSseBlock(part);
    if (parsed) events.push(parsed);
  }
  return { carry: nextCarry, events };
}

export function sseEventMatchesChat(
  data: { user_id?: unknown; conversation_id?: unknown },
  chat: Pick<LiveChatItem, 'user_id' | 'conversation_id'> | null,
): boolean {
  if (!chat) return false;
  const conversationId = String(data.conversation_id || '').trim();
  const userId = String(data.user_id || '').trim();
  if (conversationId && conversationId === chat.conversation_id) return true;
  return Boolean(userId && !conversationId && userId === chat.user_id);
}

export function liveChatMessageFromSseData(data: Record<string, unknown>): LiveChatMessage | null {
  const rec = asRecord(data.message) || {};
  const text = firstText(rec.content, rec.text, data.text);
  const messageId = firstText(rec.message_id, rec.messageId);
  const timestamp = firstText(rec.timestamp) || new Date().toISOString();
  const role = String(rec.role || data.role || '').toLowerCase();
  let isUser: boolean | undefined;
  if (typeof rec.is_user === 'boolean') isUser = rec.is_user;
  else if (role === 'user') isUser = true;
  else if (role === 'operator' || role === 'assistant' || role === 'bot') isUser = false;
  const audio = firstText(rec.audio_url);
  const image = firstText(rec.image_url);
  if (!text && !messageId && !audio && !image) return null;
  const clientId = firstText(rec.client_send_id, rec.client_message_id, data.client_message_id, data.client_send_id);
  const delivery = firstText(rec.delivery_status, data.delivery_status);
  return {
    message_id: messageId || undefined,
    timestamp,
    is_user: isUser,
    content: text,
    text,
    type: rec.type != null ? String(rec.type) : undefined,
    handled_by: rec.handled_by != null ? String(rec.handled_by) : undefined,
    role: role || undefined,
    audio_url: audio || undefined,
    image_url: image || undefined,
    client_send_id: clientId || undefined,
    delivery_status: delivery || undefined,
  };
}
