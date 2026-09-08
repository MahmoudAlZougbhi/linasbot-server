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
import { mergeThreadMessages } from './liveChatThreadMerge';
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
  const [sending, setSending] = useState(false);
  const loadingMoreRef = useRef(false);
  const sendingRef = useRef(false);
  const requestIdRef = useRef(0);

  const social = chat ? isSocialChannelUser(chat.user_id, chat.channel) : false;

  const load = useCallback(
    async (mode: 'initial' | 'poll' = 'initial') => {
      if (!chat) return;
      const requestId = ++requestIdRef.current;
      if (mode === 'initial') {
        setLoading(true);
        setError(null);
      }
      try {
        const data = await fetchConversation(chat.user_id, chat.conversation_id, {
          days: 1,
          limit: 50,
        });
        if (requestId !== requestIdRef.current) return;
        if (!data.success) throw new Error(data.error || 'Failed to load thread');
        const next = data.messages || [];
        setMessages((prev) => (mode === 'poll' ? mergeThreadMessages(prev, next) : next));
        if (mode === 'initial') {
          setHasMore(Boolean(data.has_more) || next.length >= 50);
        }
        if (data.status) setLocalStatus(data.status);
        if (mode === 'initial') {
          void markConversationRead(chat.user_id, chat.conversation_id);
        }
        if (mode === 'initial') setError(null);
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        if (mode === 'initial') {
          setError(err instanceof Error ? err.message : 'Could not load messages.');
          setMessages([]);
        }
      } finally {
        if (mode === 'initial' && requestId === requestIdRef.current) setLoading(false);
      }
    },
    [chat],
  );

  useEffect(() => {
    setLocalStatus(chat?.status ?? 'bot');
    setMessages([]);
    setHasMore(false);
    void load('initial');
    if (!chat) return;
    const id = setInterval(() => void load('poll'), 15_000);
    return () => clearInterval(id);
  }, [chat, load]);

  const loadOlder = useCallback(async () => {
    if (!chat || !messages.length || loadingMoreRef.current || !hasMore) return;
    const oldest = messages[0]?.timestamp;
    if (!oldest) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const data = await fetchConversation(chat.user_id, chat.conversation_id, {
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
  }, [chat, hasMore, messages]);

  async function runAction(fn: () => Promise<{ success: boolean; error?: string; message?: string; status?: string }>) {
    if (!chat) return;
    setBusy(true);
    setError(null);
    try {
      const result = await fn();
      if (!result.success) throw new Error(result.error || result.message || 'Action failed');
      if (result.status) setLocalStatus(result.status);
      await load('initial');
      onChatUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed.');
    } finally {
      setBusy(false);
    }
  }

  function appendOptimisticOperatorMessage(partial: LiveChatMessage) {
    setMessages((prev) => [...prev, partial]);
  }

  function dispatchOperatorSend(
    payload: string,
    messageType: 'text' | 'voice' | 'image',
    optimistic: LiveChatMessage,
  ) {
    if (!chat || !payload || sendingRef.current) return false;
    sendingRef.current = true;
    setSending(true);
    setError(null);
    appendOptimisticOperatorMessage(optimistic);
    void (async () => {
      try {
        const result = await sendOperatorMessage(chat, payload, messageType);
        if (!result.success) throw new Error(result.error || 'Send failed');
        await load('poll');
        onChatUpdated?.();
      } catch (err) {
        const dropped = optimistic.client_send_id || optimistic.message_id;
        setMessages((prev) =>
          prev.filter((msg) => (msg.client_send_id || msg.message_id) !== dropped),
        );
        setError(err instanceof Error ? err.message : 'Send failed.');
      } finally {
        sendingRef.current = false;
        setSending(false);
      }
    })();
    return true;
  }

  return {
    messages,
    loading,
    loadingMore,
    busy,
    sending,
    error,
    hasMore,
    social,
    localStatus,
    setError,
    reload: () => load('initial'),
    loadOlder,
    takeover: (assignToUserId?: string) =>
      runAction(() => takeoverConversation(chat!, assignToUserId)),
    release: () => runAction(() => releaseConversation(chat!)),
    end: () => runAction(() => endConversation(chat!)),
    sendText: async (text: string) => {
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
    sendMedia: async (base64: string, type: 'voice' | 'image', mime?: string) => {
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
