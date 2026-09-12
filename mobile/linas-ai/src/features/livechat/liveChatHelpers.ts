import type { ChatChannel, ChannelFilter, LiveChatItem, LiveChatMessage } from './liveChatTypes';
import { normalizeStatus } from './liveChatTypes';

function blobHasChannelToken(blob: string, token: string): boolean {
  return blob.includes(`${token}:`) || blob.split(/[\s|/]+/).includes(token);
}

function customerInfoChannel(item: LiveChatItem): string {
  const info = item.customer_info;
  if (!info || typeof info !== 'object') return '';
  const rec = info as { channel?: unknown; platform?: unknown };
  return String(rec.channel || rec.platform || '').toLowerCase().trim();
}

const PREFIX_CHANNELS: Record<string, ChatChannel> = {
  web: 'web',
  tiktok: 'tiktok',
  instagram: 'instagram',
  facebook: 'facebook',
  messenger: 'facebook',
  whatsapp: 'whatsapp',
};

function channelFromUserId(userId: string | null | undefined): ChatChannel | null {
  const uid = String(userId || '').trim().toLowerCase();
  if (!uid) return null;
  const parts = uid.split(':').filter(Boolean);
  if (!parts.length) return null;
  if (PREFIX_CHANNELS[parts[0]]) return PREFIX_CHANNELS[parts[0]];
  if (parts[1] && PREFIX_CHANNELS[parts[1]]) return PREFIX_CHANNELS[parts[1]];
  return null;
}

function isWhatsAppUserId(userId: string | null | undefined): boolean {
  const uid = String(userId || '').trim();
  if (!uid) return false;
  if (uid.toLowerCase().startsWith('whatsapp:')) return true;
  if (/^\+[0-9]{8,15}$/.test(uid)) return true;
  const digits = uid.replace(/\D/g, '');
  return /^961[0-9]{7,9}$/.test(digits);
}

function normalizeKnownChannel(raw: string): ChatChannel | null {
  const ch = String(raw || '').toLowerCase().trim();
  if (ch === 'tiktok') return 'tiktok';
  if (ch === 'web' || ch === 'web_chat' || ch === 'website') return 'web';
  if (ch === 'instagram' || ch === 'instagram_dm' || ch === 'ig') return 'instagram';
  if (ch === 'facebook' || ch === 'messenger' || ch === 'facebook_messenger') return 'facebook';
  if (ch === 'whatsapp' || ch === 'whatsapp_cloud' || ch === 'wa') return 'whatsapp';
  return null;
}

/** Infer platform from user_id prefixes first. Never invents TikTok. Never labels web/tiktok as WhatsApp. */
export function chatChannel(item: LiveChatItem): ChatChannel {
  const fromId = channelFromUserId(item.user_id);
  if (fromId) return fromId;
  const fromPayload = normalizeKnownChannel(String(item.channel || customerInfoChannel(item) || ''));
  if (fromPayload) return fromPayload;
  const blob = [item.user_id, item.user_phone, item.phone_number, item.phone_clean]
    .map((v) => String(v || '').toLowerCase())
    .join(' ');
  if (blobHasChannelToken(blob, 'tiktok')) return 'tiktok';
  if (blobHasChannelToken(blob, 'web')) return 'web';
  if (blobHasChannelToken(blob, 'instagram')) return 'instagram';
  if (blobHasChannelToken(blob, 'facebook') || blobHasChannelToken(blob, 'messenger')) return 'facebook';
  if (blobHasChannelToken(blob, 'whatsapp')) return 'whatsapp';
  if (isWhatsAppUserId(item.user_id) || isWhatsAppUserId(item.user_phone) || isWhatsAppUserId(item.phone_number)) {
    return 'whatsapp';
  }
  return 'unknown';
}

/** All keeps every parsed row, including unlabeled (missing channel). */
export function matchesChannelFilter(item: LiveChatItem, filter: ChannelFilter): boolean {
  if (filter === 'all') return true;
  return chatChannel(item) === filter;
}

export function matchesAllowedChannels(item: LiveChatItem, allowed: ChatChannel[] | null): boolean {
  if (!allowed) return true;
  if (allowed.length === 0) return false;
  return allowed.includes(chatChannel(item));
}

export function channelLabel(item: LiveChatItem): string {
  const ch = chatChannel(item);
  if (ch === 'instagram') return 'Instagram';
  if (ch === 'facebook') return 'Messenger';
  if (ch === 'tiktok') return 'TikTok';
  if (ch === 'web') return 'Website';
  if (ch === 'unknown') return 'Chat';
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

function rawMessageText(msg: LiveChatMessage): string {
  return String(msg.content || msg.text || '').trim();
}

function isVoicePlaceholder(text: string): boolean {
  const t = text.toLowerCase();
  return !t || /^\[?voice (message|send)/i.test(t) || t.includes('voice message from operator');
}

export function isVoiceMessage(msg: LiveChatMessage): boolean {
  const t = String(msg.type || '').toLowerCase();
  if (t === 'voice' || t === 'audio') return true;
  if (msg.audio_url) return true;
  return isVoicePlaceholder(rawMessageText(msg)) && /voice/i.test(rawMessageText(msg));
}

export function messageBody(msg: LiveChatMessage): string {
  const t = String(msg.type || 'text').toLowerCase();
  if (t === 'voice' || t === 'audio' || isVoiceMessage(msg)) {
    const raw = rawMessageText(msg);
    return isVoicePlaceholder(raw) ? 'Voice message' : raw || 'Voice message';
  }
  if (t === 'image') return msg.content || msg.text || 'Image';
  return rawMessageText(msg) || '(empty)';
}

/** Web parity: Like only on AI text replies (not bot/FAQ, not media). */
export function isLikeableAiReply(msg: LiveChatMessage): boolean {
  if (msg.is_user) return false;
  const type = String(msg.type || 'text').toLowerCase();
  if (type === 'voice' || type === 'audio' || type === 'image' || isVoiceMessage(msg)) return false;
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
  const client = String(msg.client_send_id || '').trim();
  if (client) return client;
  return msg.message_id || `${msg.timestamp || 't'}|${msg.is_user ? 'u' : 'a'}|${index}`;
}

export function clientSendId(): string {
  return `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}
