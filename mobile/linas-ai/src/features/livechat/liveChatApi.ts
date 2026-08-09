import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';
import { tokenStore } from '../../auth/tokenStore';
import {
  ActionResultSchema,
  ConversationDetailsSchema,
  type InboxFilter,
  type LiveChatItem,
  UnifiedChatsSchema,
  idempotencyKey,
} from './liveChatTypes';

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const body = err.body as { error?: string; detail?: string; message?: string } | null;
    if (body?.error) return String(body.error);
    if (body?.detail) return String(body.detail);
    if (body?.message) return String(body.message);
    if (err.status === 403) return 'Forbidden — liveChat permission required.';
    if (err.status === 401) return 'Not authenticated.';
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

function rethrow(err: unknown, fallback: string): never {
  if (err instanceof ApiError) throw err;
  throw new Error(errorMessage(err, fallback));
}

export async function fetchUnifiedChats(opts: {
  search?: string;
  page?: number;
  pageSize?: number;
  cursor?: string | null;
  filter?: InboxFilter;
}) {
  const params = new URLSearchParams();
  if (opts.search?.trim()) params.set('search', opts.search.trim());
  params.set('page', String(opts.page ?? 1));
  params.set('page_size', String(opts.pageSize ?? 30));
  if (opts.cursor) params.set('cursor', opts.cursor);
  if (opts.filter && opts.filter !== 'all') params.set('filter', opts.filter);
  try {
    return await apiFetch(`/api/live-chat/unified-chats?${params}`, { schema: UnifiedChatsSchema });
  } catch (err) {
    rethrow(err, 'Could not load conversations.');
  }
}

export async function fetchConversation(
  userId: string,
  conversationId: string,
  opts?: { before?: string; dayWindow?: number; limit?: number; days?: number },
) {
  const params = new URLSearchParams();
  if (opts?.days != null) params.set('days', String(opts.days));
  if (opts?.before) params.set('before', opts.before);
  if (opts?.dayWindow != null) params.set('day_window', String(opts.dayWindow));
  if (opts?.limit != null) params.set('limit', String(opts.limit));
  const q = params.toString();
  const path = `/api/live-chat/conversation/${encodeURIComponent(userId)}/${encodeURIComponent(conversationId)}${q ? `?${q}` : ''}`;
  try {
    return await apiFetch(path, { schema: ConversationDetailsSchema });
  } catch (err) {
    rethrow(err, 'Could not load messages.');
  }
}

export async function markConversationRead(userId: string, conversationId: string) {
  try {
    return await apiFetch('/api/live-chat/mark-read', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, conversation_id: conversationId }),
      schema: ActionResultSchema,
    });
  } catch {
    return { success: false };
  }
}

async function operatorId(): Promise<string> {
  const user = await tokenStore.getUser();
  return user?.id || 'operator';
}

export async function takeoverConversation(chat: LiveChatItem) {
  try {
    return await apiFetch('/api/live-chat/takeover', {
      method: 'POST',
      body: JSON.stringify({
        conversation_id: chat.conversation_id,
        user_id: chat.user_id,
        operator_id: await operatorId(),
      }),
      schema: ActionResultSchema,
    });
  } catch (err) {
    rethrow(err, 'Takeover failed.');
  }
}

export async function releaseConversation(chat: LiveChatItem) {
  try {
    return await apiFetch('/api/live-chat/release', {
      method: 'POST',
      body: JSON.stringify({
        conversation_id: chat.conversation_id,
        user_id: chat.user_id,
      }),
      schema: ActionResultSchema,
    });
  } catch (err) {
    rethrow(err, 'Release failed.');
  }
}

export async function endConversation(chat: LiveChatItem) {
  try {
    return await apiFetch('/api/live-chat/end-conversation', {
      method: 'POST',
      body: JSON.stringify({
        conversation_id: chat.conversation_id,
        user_id: chat.user_id,
        operator_id: await operatorId(),
      }),
      schema: ActionResultSchema,
    });
  } catch (err) {
    rethrow(err, 'Could not end conversation.');
  }
}

export async function sendOperatorMessage(
  chat: LiveChatItem,
  message: string,
  messageType: 'text' | 'voice' | 'image' = 'text',
) {
  try {
    return await apiFetch('/api/live-chat/send-message', {
      method: 'POST',
      body: JSON.stringify({
        conversation_id: chat.conversation_id,
        user_id: chat.user_id,
        message,
        operator_id: await operatorId(),
        message_type: messageType,
        idempotency_key: idempotencyKey(messageType),
      }),
      schema: ActionResultSchema,
    });
  } catch (err) {
    rethrow(err, 'Send failed.');
  }
}

export async function setOperatorAvailable() {
  try {
    await apiFetch('/api/live-chat/operator-status', {
      method: 'POST',
      body: JSON.stringify({ operator_id: await operatorId(), status: 'available' }),
      schema: z.object({ success: z.boolean() }).passthrough(),
    });
  } catch {
    // Non-blocking — inbox still works without status sync.
  }
}

export function classifyLiveChatError(err: unknown): 'forbidden' | 'auth' | 'other' {
  if (err instanceof ApiError) {
    if (err.status === 403) return 'forbidden';
    if (err.status === 401) return 'auth';
  }
  const msg = err instanceof Error ? err.message.toLowerCase() : '';
  if (msg.includes('forbidden') || msg.includes('permission')) return 'forbidden';
  if (msg.includes('not authenticated') || msg.includes('401')) return 'auth';
  return 'other';
}
