import { z } from 'zod';

export const InboxFilterSchema = z.enum(['all', 'waiting', 'with_operator', 'bot', 'closed']);
export type InboxFilter = z.infer<typeof InboxFilterSchema>;

export const LastMessageSchema = z.union([
  z.string(),
  z
    .object({
      content: z.string().optional().nullable(),
      text: z.string().optional().nullable(),
      timestamp: z.string().optional().nullable(),
      is_user: z.boolean().optional().nullable(),
    })
    .passthrough(),
]);

export const LiveChatItemSchema = z
  .object({
    conversation_id: z.string(),
    user_id: z.string(),
    user_name: z.string().optional().nullable(),
    user_phone: z.string().optional().nullable(),
    phone_number: z.string().optional().nullable(),
    phone_clean: z.string().optional().nullable(),
    last_message_text: z.string().optional().nullable(),
    last_message_at: z.string().optional().nullable(),
    last_activity: z.string().optional().nullable(),
    conversation_state: z.string().optional().nullable(),
    status: z.string().optional().nullable(),
    channel: z.string().optional().nullable(),
    operator_id: z.string().optional().nullable(),
    operator_name: z.string().optional().nullable(),
    human_takeover_active: z.boolean().optional().nullable(),
    unread_count: z.number().optional().nullable(),
    language: z.string().optional().nullable(),
    sentiment: z.string().optional().nullable(),
    message_count: z.number().optional().nullable(),
    is_new_customer: z.boolean().optional().nullable(),
    last_message: LastMessageSchema.optional().nullable(),
  })
  .passthrough();

export type LiveChatItem = z.infer<typeof LiveChatItemSchema>;

export const UnifiedChatsSchema = z
  .object({
    success: z.boolean(),
    chats: z.array(LiveChatItemSchema).default([]),
    total: z.number().optional(),
    page: z.number().optional(),
    page_size: z.number().optional(),
    has_more: z.boolean().optional(),
    next_cursor: z.string().nullable().optional(),
    filter: z.string().optional(),
    error: z.string().optional(),
  })
  .passthrough();

export const LiveChatMessageSchema = z
  .object({
    timestamp: z.string().optional().nullable(),
    is_user: z.boolean().optional().nullable(),
    content: z.string().optional().nullable(),
    text: z.string().optional().nullable(),
    type: z.string().optional().nullable(),
    handled_by: z.string().optional().nullable(),
    role: z.string().optional().nullable(),
    message_id: z.string().optional().nullable(),
    audio_url: z.string().optional().nullable(),
    image_url: z.string().optional().nullable(),
    media_url: z.string().optional().nullable(),
  })
  .passthrough();

export type LiveChatMessage = z.infer<typeof LiveChatMessageSchema>;

export const ConversationDetailsSchema = z
  .object({
    success: z.boolean(),
    conversation_id: z.string().optional(),
    messages: z.array(LiveChatMessageSchema).default([]),
    total_messages: z.number().optional(),
    returned_messages: z.number().optional(),
    sentiment: z.string().optional().nullable(),
    status: z.string().optional().nullable(),
    has_more: z.boolean().optional(),
    error: z.string().optional(),
  })
  .passthrough();

export const ActionResultSchema = z
  .object({
    success: z.boolean(),
    message: z.string().optional(),
    error: z.string().optional(),
    conversation_id: z.string().optional(),
    status: z.string().optional(),
  })
  .passthrough();

export function isSocialChannelUser(userId: string | null | undefined, channel?: string | null): boolean {
  const ch = String(channel || '').toLowerCase();
  if (ch === 'instagram' || ch === 'facebook') return true;
  const id = String(userId || '');
  return /^(?:[a-z0-9][a-z0-9_-]{0,63}:)?(?:instagram|facebook):/i.test(id);
}

export function normalizeStatus(item: LiveChatItem): 'bot' | 'waiting_human' | 'human' | 'closed' {
  const raw = String(item.status || item.conversation_state || '').toLowerCase();
  if (raw.includes('waiting')) return 'waiting_human';
  if (raw === 'human' || raw.includes('assigned') || item.human_takeover_active) return 'human';
  if (raw.includes('resolved') || raw.includes('archived') || raw === 'closed') return 'closed';
  return 'bot';
}

export function statusLabel(status: ReturnType<typeof normalizeStatus>): string {
  if (status === 'waiting_human') return 'Waiting';
  if (status === 'human') return 'Human';
  if (status === 'closed') return 'Closed';
  return 'AI';
}

export function statusTone(status: ReturnType<typeof normalizeStatus>): 'warn' | 'ok' | 'neutral' | 'soon' {
  if (status === 'waiting_human') return 'warn';
  if (status === 'human') return 'ok';
  if (status === 'closed') return 'soon';
  return 'neutral';
}

export function chatTitle(item: LiveChatItem): string {
  return (
    item.user_name?.trim() ||
    item.user_phone?.trim() ||
    item.phone_number?.trim() ||
    item.phone_clean?.trim() ||
    item.user_id
  );
}

export function chatAvatarLetter(item: LiveChatItem): string {
  const title = chatTitle(item).trim();
  return (title.charAt(0) || '?').toUpperCase();
}

function lastMessageParts(item: LiveChatItem): { text: string; isUser: boolean | null; at: string | null } {
  const lm = item.last_message;
  let text = String(item.last_message_text || '').trim();
  let isUser: boolean | null = null;
  let at: string | null = item.last_message_at || item.last_activity || null;
  if (typeof lm === 'string') {
    if (!text) text = lm.trim();
  } else if (lm && typeof lm === 'object') {
    if (!text) text = String(lm.content || lm.text || '').trim();
    if (typeof lm.is_user === 'boolean') isUser = lm.is_user;
    if (lm.timestamp) at = String(lm.timestamp);
  }
  return { text, isUser, at };
}

export function chatLastAt(item: LiveChatItem): string | null {
  return lastMessageParts(item).at;
}

/** WhatsApp-style inbox preview. Direction prefix only when inbound is explicit. */
export function chatPreview(item: LiveChatItem): string {
  const { text, isUser } = lastMessageParts(item);
  if (!text) return 'No messages yet';
  if (isUser === true) return text;
  if (isUser === false) return text;
  return text;
}

export type ChatChannel = 'whatsapp' | 'instagram' | 'facebook' | 'tiktok';

/** Infer platform from API channel or user_id prefix. Never invents TikTok rows. */
export function chatChannel(item: LiveChatItem): ChatChannel {
  const ch = String(item.channel || '').toLowerCase();
  const id = String(item.user_id || '').toLowerCase();
  if (ch === 'tiktok' || id.includes('tiktok:')) return 'tiktok';
  if (ch === 'instagram' || id.includes('instagram:')) return 'instagram';
  if (ch === 'facebook' || ch === 'messenger' || id.includes('facebook:')) return 'facebook';
  if (ch === 'whatsapp') return 'whatsapp';
  return 'whatsapp';
}

export function channelLabel(item: LiveChatItem): string {
  const ch = chatChannel(item);
  if (ch === 'instagram') return 'Instagram';
  if (ch === 'facebook') return 'Messenger';
  if (ch === 'tiktok') return 'TikTok';
  return 'WhatsApp';
}

/** First token of a name, or local-part of an email — matches inbox "Mohammad" / "AI". */
export function assigneeFirstName(raw: string | null | undefined): string {
  const value = String(raw || '').trim();
  if (!value) return '';
  const local = value.includes('@') ? value.split('@')[0] : value;
  const token = local.split(/[\s._-]+/).filter(Boolean)[0] || local;
  return token.charAt(0).toUpperCase() + token.slice(1);
}

export function assigneeLabel(item: LiveChatItem): string {
  const status = normalizeStatus(item);
  if (status === 'bot' || status === 'closed') return 'AI';
  const named = assigneeFirstName(item.operator_name);
  if (named) return named;
  if (status === 'human' || status === 'waiting_human' || item.operator_id) return 'Human';
  return 'AI';
}

export function messageBody(msg: LiveChatMessage): string {
  const t = String(msg.type || 'text').toLowerCase();
  if (t === 'voice' || t === 'audio') return msg.content || msg.text || 'Voice message';
  if (t === 'image') return msg.content || msg.text || 'Image';
  return String(msg.content || msg.text || '').trim() || '(empty)';
}

/** Web parity: Like only on AI text replies (not bot/FAQ, not media). */
export function isLikeableAiReply(msg: LiveChatMessage): boolean {
  if (msg.is_user) return false;
  const type = String(msg.type || 'text').toLowerCase();
  if (type === 'voice' || type === 'audio' || type === 'image') return false;
  return String(msg.handled_by || '').toLowerCase() === 'ai';
}

/** Chronological messages: find the customer question before this AI reply. */
export function previousUserQuestion(
  messages: LiveChatMessage[],
  aiMessage: LiveChatMessage,
): string {
  const idx = messages.findIndex((m) => m === aiMessage);
  const start = idx >= 0 ? idx - 1 : messages.length - 1;
  for (let i = start; i >= 0; i--) {
    const candidate = messages[i];
    if (candidate?.is_user) {
      const text = String(candidate.content || candidate.text || '').trim();
      if (text) return text;
    }
  }
  return '';
}

export function parseChatDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Inbox row time — today HH:mm, yesterday, else short date (Beirut-friendly local). */
export function formatInboxTime(value: string | null | undefined): string {
  const d = parseChatDate(value);
  if (!d) return '';
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startMsg = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dayDiff = Math.round((startToday.getTime() - startMsg.getTime()) / 86_400_000);
  if (dayDiff === 0) {
    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
  }
  if (dayDiff === 1) return 'Yesterday';
  if (dayDiff < 7) return d.toLocaleDateString([], { weekday: 'short' });
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export function formatBubbleTime(value: string | null | undefined): string {
  const d = parseChatDate(value);
  if (!d) return '';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function messageKey(msg: LiveChatMessage, index = 0): string {
  return msg.message_id || `${msg.timestamp || 't'}|${msg.is_user ? 'u' : 'a'}|${index}`;
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}
