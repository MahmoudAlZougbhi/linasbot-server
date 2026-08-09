import { z } from 'zod';

export const InboxFilterSchema = z.enum(['all', 'waiting', 'with_operator', 'bot', 'closed']);
export type InboxFilter = z.infer<typeof InboxFilterSchema>;

export const LastMessageSchema = z
  .object({
    content: z.string().optional().nullable(),
    text: z.string().optional().nullable(),
    timestamp: z.string().optional().nullable(),
    is_user: z.boolean().optional().nullable(),
  })
  .passthrough();

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

export function chatPreview(item: LiveChatItem): string {
  const fromLast =
    item.last_message_text ||
    item.last_message?.content ||
    item.last_message?.text ||
    '';
  return String(fromLast || 'No messages yet').trim();
}

export function channelLabel(item: LiveChatItem): string {
  if (isSocialChannelUser(item.user_id, item.channel)) {
    const id = String(item.user_id || '').toLowerCase();
    if (id.includes('instagram') || String(item.channel).toLowerCase() === 'instagram') return 'Instagram';
    if (id.includes('facebook') || String(item.channel).toLowerCase() === 'facebook') return 'Facebook';
    return 'Social';
  }
  return 'WhatsApp';
}

export function messageBody(msg: LiveChatMessage): string {
  const t = String(msg.type || 'text').toLowerCase();
  if (t === 'voice' || t === 'audio') return msg.content || msg.text || 'Voice message';
  if (t === 'image') return msg.content || msg.text || 'Image';
  return String(msg.content || msg.text || '').trim() || '(empty)';
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}
