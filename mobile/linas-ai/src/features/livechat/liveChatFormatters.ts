type InboxLastMessageSource = {
  last_message_at?: string | null;
  last_activity?: string | null;
  last_message_text?: string | null;
  last_message?:
    | string
    | {
        content?: string | null;
        text?: string | null;
        timestamp?: string | null;
        is_user?: boolean | null;
      }
    | null;
};

type MessageKeySource = {
  message_id?: string | null;
  timestamp?: string | null;
  is_user?: boolean | null;
};

function lastMessageParts(item: InboxLastMessageSource): {
  text: string;
  isUser: boolean | null;
  at: string | null;
} {
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

export function chatLastAt(item: InboxLastMessageSource): string | null {
  return lastMessageParts(item).at;
}

/** WhatsApp-style inbox preview. Direction prefix only when inbound is explicit. */
export function chatPreview(item: InboxLastMessageSource): string {
  const { text, isUser } = lastMessageParts(item);
  if (!text) return 'No messages yet';
  if (isUser === true) return text;
  if (isUser === false) return text;
  return text;
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

export function messageKey(msg: MessageKeySource, index = 0): string {
  return msg.message_id || `${msg.timestamp || 't'}|${msg.is_user ? 'u' : 'a'}|${index}`;
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}
