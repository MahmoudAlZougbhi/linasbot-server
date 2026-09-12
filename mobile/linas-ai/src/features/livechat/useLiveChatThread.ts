import { useCallback, useEffect, useRef, useState } from 'react';

import {
  endConversation,
  fetchConversation,
  markConversationRead,
  releaseConversation,
  sendOperatorMessage,
  takeoverConversation,
} from './liveChatApi';
import { clientSendId, previewMessagesFromInbox } from './liveChatHelpers';
import { sseEventMatchesChat } from './liveChatSseParse';
import { hasPendingOperatorSend, applyMessageStatus, mergeSseThreadMessage, mergeThreadMessages } from './liveChatThreadMerge';
import type { LiveChatItem, LiveChatMessage } from './liveChatTypes';
import { isSocialChannelUser, normalizeStatus } from './liveChatTypes';

function isBotThreadStatus(status: string | undefined): boolean {
  if (!status) return false;
  return normalizeStatus({ conversation_id: 'x', user_id: 'x', status } as LiveChatItem) === 'bot';
}

export function useLiveChatThread(chat: LiveChatItem | null, onChatUpdated?: () => void) {
  const [messages, setMessages] = useState<LiveChatMessage[]>(() => previewMessagesFromInbox(chat));
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [localStatus, setLocalStatus] = useState(chat?.status ?? 'bot');
  const userId = chat?.user_id || '';
  const conversationId = chat?.conversation_id || '';
  const loadingMoreRef = useRef(false);
  const requestIdRef = useRef(0);
  const holdHumanRef = useRef(false);
  const localStatusRef = useRef(localStatus);
  localStatusRef.current = localStatus;
  const chatRef = useRef(chat);
  chatRef.current = chat;
  const onChatUpdatedRef = useRef(onChatUpdated);
  onChatUpdatedRef.current = onChatUpdated;

  const social = chat ? isSocialChannelUser(chat.user_id, chat.channel) : false;

  const applyServerStatus = useCallback((incoming: string | null | undefined) => {
    if (!incoming) return;
    if (holdHumanRef.current && isBotThreadStatus(incoming)) return;
    setLocalStatus(incoming);
  }, []);

  const load = useCallback(
    async (mode: 'initial' | 'poll' = 'initial') => {
      if (!userId || !conversationId) return;
      const requestId = ++requestIdRef.current;
      const seeded = previewMessagesFromInbox(chatRef.current).length > 0;
      if (mode === 'initial') {
        if (!seeded) setLoading(true);
        setError(null);
      }
      try {
        const data = await fetchConversation(userId, conversationId, {
          limit: 50,
        });
        if (requestId !== requestIdRef.current) return;
        if (!data.success) throw new Error(data.error || 'Failed to load thread');
        const next = data.messages || [];
        setMessages((prev) =>
          mode === 'poll' || prev.length ? mergeThreadMessages(prev, next) : next,
        );
        if (mode === 'initial') {
          setHasMore(Boolean(data.has_more) || next.length >= 50);
        }
        applyServerStatus(data.status);
        if (mode === 'initial') {
          void markConversationRead(userId, conversationId);
        }
        if (mode === 'initial') setError(null);
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        if (mode === 'initial') {
          setError(err instanceof Error ? err.message : 'Could not load messages.');
          setMessages((prev) => (prev.length || hasPendingOperatorSend(prev) ? prev : []));
        }
      } finally {
        if (mode === 'initial' && requestId === requestIdRef.current) setLoading(false);
      }
    },
    [userId, conversationId, applyServerStatus],
  );

  useEffect(() => {
    holdHumanRef.current = false;
    setLocalStatus(chatRef.current?.status ?? 'bot');
    setMessages(previewMessagesFromInbox(chatRef.current));
    setHasMore(false);
    void load('initial');
  }, [userId, conversationId, load]);

  const loadOlder = useCallback(async () => {
    if (!userId || !conversationId || !messages.length || loadingMoreRef.current || !hasMore) return;
    const oldest = messages[0]?.timestamp;
    if (!oldest) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const data = await fetchConversation(userId, conversationId, {
        before: oldest,
        dayWindow: 1,
        limit: 50,
      });
      const older = data.messages || [];
      if (!older.length) {
        setHasMore(false);
        return;
      }
      setMessages((prev) => {
        const seen = new Set(
          prev.map((m) => `${m.timestamp}|${m.content || m.text}|${m.is_user ? 1 : 0}`),
        );
        const unique = older.filter(
          (m) => !seen.has(`${m.timestamp}|${m.content || m.text}|${m.is_user ? 1 : 0}`),
        );
        return unique.length ? [...unique, ...prev] : prev;
      });
      setHasMore(Boolean(data.has_more) || older.length >= 40);
    } catch {
      // keep thread
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, [userId, conversationId, hasMore, messages]);

  async function runAction(fn: () => Promise<{ success: boolean; error?: string; message?: string; status?: string }>) {
    if (!chat) return;
    setBusy(true);
    setError(null);
    try {
      const result = await fn();
      applyServerStatus(result.status);
      if (!result.success) throw new Error(result.error || result.message || 'Action failed');
      onChatUpdatedRef.current?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed.');
    } finally {
      setBusy(false);
    }
  }

  function applyRealtime(data: Record<string, unknown>, eventType?: string) {
    if (!sseEventMatchesChat(data, { user_id: userId, conversation_id: conversationId })) return;
    if (eventType === 'message_status' || eventType === 'message_updated') {
      setMessages((prev) => applyMessageStatus(prev, data));
      return;
    }
    setMessages((prev) => mergeSseThreadMessage(prev, data));
  }

  function patchOptimistic(
    sendId: string,
    patch: Partial<LiveChatMessage>,
  ) {
    setMessages((prev) =>
      prev.map((msg) => ((msg.client_send_id || msg.message_id) === sendId ? { ...msg, ...patch } : msg)),
    );
  }

  function dispatchOperatorSend(
    payload: string,
    messageType: 'text' | 'voice' | 'image',
    optimistic: LiveChatMessage,
  ) {
    if (!chat || !payload) return false;
    const target = chat;
    const sendId = String(optimistic.client_send_id || optimistic.message_id || '');
    const idempotency = String(optimistic.idempotency_key || sendId);
    setError(null);
    holdHumanRef.current = true;
    setMessages((prev) => {
      const exists = prev.some((msg) => (msg.client_send_id || msg.message_id) === sendId);
      if (exists) {
        return prev.map((msg) =>
          (msg.client_send_id || msg.message_id) === sendId
            ? { ...msg, ...optimistic, delivery_status: 'sending', delivery_error: undefined }
            : msg,
        );
      }
      return [...prev, optimistic];
    });
    setLocalStatus('human');
    void sendOperatorMessage(target, payload, messageType, { idempotencyKey: idempotency })
      .then((result) => {
        if (result.status) applyServerStatus(result.status);
        const status = String(result.delivery_status || (result.success ? 'sending' : 'failed'));
        if (!result.success) {
          patchOptimistic(sendId, { delivery_status: 'failed', delivery_error: result.error || 'Send failed' });
          setError(result.error || 'Send failed.');
          return;
        }
        patchOptimistic(sendId, {
          delivery_status: status === 'sent' ? 'sent' : 'sending',
        });
        onChatUpdatedRef.current?.();
      })
      .catch((err) => {
        patchOptimistic(sendId, {
          delivery_status: 'failed',
          delivery_error: err instanceof Error ? err.message : 'Send failed.',
        });
        setError(err instanceof Error ? err.message : 'Send failed.');
      });
    return true;
  }

  const claimOnOpen = useCallback(() => {
    const target = chatRef.current;
    if (!target) return;
    // Viewing must not pause AI. Take over / sending still pause. Assign to AI stays bot.
    void markConversationRead(target.user_id, target.conversation_id);
  }, []);

  return {
    messages,
    loading,
    loadingMore,
    busy,
    error,
    hasMore,
    social,
    localStatus,
    setError,
    reload: () => load('initial'),
    reloadQuiet: () => void load('poll'),
    applyRealtime,
    claimOnOpen,
    retryFailedSend: (msg: LiveChatMessage) => {
      if (!chat) return false;
      const type = String(msg.type || 'text').toLowerCase();
      if (type === 'voice' || type === 'image' || type === 'audio') return false;
      const payload = String(msg.content || msg.text || '').trim();
      if (!payload) return false;
      const sendId = String(msg.client_send_id || msg.idempotency_key || msg.message_id || clientSendId());
      return dispatchOperatorSend(payload, 'text', {
        ...msg,
        message_id: msg.message_id || sendId,
        client_send_id: sendId,
        idempotency_key: String(msg.idempotency_key || sendId),
        delivery_status: 'sending',
        delivery_error: undefined,
        is_user: false,
        role: 'operator',
        handled_by: 'human',
      });
    },
    loadOlder,
    takeover: (assignToUserId?: string) => {
      holdHumanRef.current = true;
      setLocalStatus('human');
      return runAction(() => takeoverConversation(chat!, assignToUserId));
    },
    release: () => {
      const previous = localStatusRef.current;
      holdHumanRef.current = false;
      setLocalStatus('bot');
      return runAction(async () => {
        const result = await releaseConversation(chat!);
        if (!result.success) {
          holdHumanRef.current = true;
          setLocalStatus(previous);
        }
        return result;
      });
    },
    end: () => runAction(() => endConversation(chat!)),
    sendText: (text: string) => {
      if (!chat || !text.trim()) return false;
      const trimmed = text.trim();
      const sendId = clientSendId();
      return dispatchOperatorSend(trimmed, 'text', {
        timestamp: new Date().toISOString(),
        is_user: false,
        content: trimmed,
        text: trimmed,
        role: 'operator',
        handled_by: 'human',
        message_id: sendId,
        client_send_id: sendId,
        idempotency_key: sendId,
        delivery_status: 'sending',
      });
    },
    sendMedia: (base64: string, type: 'voice' | 'image', mime?: string) => {
      if (!chat || !base64) return false;
      const label = type === 'voice' ? '[Voice Message from Operator]' : '[Image Message from Operator]';
      const sendId = clientSendId();
      return dispatchOperatorSend(base64, type, {
        timestamp: new Date().toISOString(),
        is_user: false,
        content: label,
        text: label,
        type,
        role: 'operator',
        handled_by: 'human',
        message_id: sendId,
        client_send_id: sendId,
        idempotency_key: sendId,
        delivery_status: 'sending',
        audio_url: type === 'voice' ? `data:${mime || 'audio/mp4'};base64,${base64}` : undefined,
      });
    },
  };
}
