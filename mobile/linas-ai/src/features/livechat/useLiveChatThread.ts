import { useCallback, useEffect, useRef, useState } from 'react';

import {
  endConversation,
  fetchConversation,
  markConversationRead,
  releaseConversation,
  sendOperatorMessage,
  takeoverConversation,
} from './liveChatApi';
import { clientSendId } from './liveChatHelpers';
import { sseEventMatchesChat } from './liveChatSseParse';
import { hasPendingOperatorSend, mergeSseThreadMessage, mergeThreadMessages } from './liveChatThreadMerge';
import type { LiveChatItem, LiveChatMessage } from './liveChatTypes';
import { isSocialChannelUser } from './liveChatTypes';

export function useLiveChatThread(chat: LiveChatItem | null, onChatUpdated?: () => void) {
  const [messages, setMessages] = useState<LiveChatMessage[]>([]);
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

  const social = chat ? isSocialChannelUser(chat.user_id, chat.channel) : false;

  const load = useCallback(
    async (mode: 'initial' | 'poll' = 'initial') => {
      if (!userId || !conversationId) return;
      const requestId = ++requestIdRef.current;
      if (mode === 'initial') {
        setLoading(true);
        setError(null);
      }
      try {
        const data = await fetchConversation(userId, conversationId, {
          days: 1,
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
        if (data.status) setLocalStatus(data.status);
        if (mode === 'initial') {
          void markConversationRead(userId, conversationId);
        }
        if (mode === 'initial') setError(null);
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        if (mode === 'initial') {
          setError(err instanceof Error ? err.message : 'Could not load messages.');
          setMessages((prev) => (hasPendingOperatorSend(prev) ? prev : []));
        }
      } finally {
        if (mode === 'initial' && requestId === requestIdRef.current) setLoading(false);
      }
    },
    [userId, conversationId],
  );

  useEffect(() => {
    setLocalStatus(chat?.status ?? 'bot');
    setMessages([]);
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
      if (result.status) setLocalStatus(result.status);
      if (!result.success) throw new Error(result.error || result.message || 'Action failed');
      await load('initial');
      onChatUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed.');
    } finally {
      setBusy(false);
    }
  }

  function applyRealtime(data: Record<string, unknown>) {
    if (!sseEventMatchesChat(data, { user_id: userId, conversation_id: conversationId })) return;
    setMessages((prev) => mergeSseThreadMessage(prev, data));
  }

  function dispatchOperatorSend(
    payload: string,
    messageType: 'text' | 'voice' | 'image',
    optimistic: LiveChatMessage,
  ) {
    if (!chat || !payload) return false;
    const target = chat;
    setError(null);
    setMessages((prev) => [...prev, optimistic]);
    setLocalStatus('human');
    void sendOperatorMessage(target, payload, messageType)
      .then((result) => {
        if (result.status) setLocalStatus(result.status);
        if (!result.success) throw new Error(result.error || 'Send failed');
        onChatUpdated?.();
      })
      .catch((err) => {
        const dropped = optimistic.client_send_id || optimistic.message_id;
        setMessages((prev) =>
          prev.filter((msg) => (msg.client_send_id || msg.message_id) !== dropped),
        );
        setError(err instanceof Error ? err.message : 'Send failed.');
      });
    return true;
  }

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
    loadOlder,
    takeover: (assignToUserId?: string) =>
      runAction(() => takeoverConversation(chat!, assignToUserId)),
    release: () => runAction(() => releaseConversation(chat!)),
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
        audio_url: type === 'voice' ? `data:${mime || 'audio/mp4'};base64,${base64}` : undefined,
      });
    },
  };
}
