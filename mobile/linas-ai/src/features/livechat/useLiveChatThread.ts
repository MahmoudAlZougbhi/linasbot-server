import { useCallback, useEffect, useRef, useState } from 'react';

import {
  endConversation,
  fetchConversation,
  markConversationRead,
  releaseConversation,
  sendOperatorMessage,
  takeoverConversation,
} from './liveChatApi';
import type { LiveChatItem, LiveChatMessage } from './liveChatTypes';
import { isSocialChannelUser, messageKey } from './liveChatTypes';

function mergeChronological(prev: LiveChatMessage[], incoming: LiveChatMessage[]): LiveChatMessage[] {
  if (!prev.length) return incoming;
  if (!incoming.length) return prev;
  const seen = new Set(prev.map((m, i) => messageKey(m, i)));
  const extras: LiveChatMessage[] = [];
  for (let i = 0; i < incoming.length; i++) {
    const m = incoming[i];
    const key = messageKey(m, i);
    if (!seen.has(key)) {
      // Also match by timestamp+content when message_id missing on one side.
      const loose = `${m.timestamp}|${m.content || m.text}|${m.is_user ? 1 : 0}`;
      const exists = prev.some(
        (p) => `${p.timestamp}|${p.content || p.text}|${p.is_user ? 1 : 0}` === loose,
      );
      if (!exists) extras.push(m);
    }
  }
  if (!extras.length) {
    // Prefer server copy for overlapping recent window (delivery updates).
    const oldestIncoming = incoming[0]?.timestamp;
    if (!oldestIncoming) return prev;
    const keepOlder = prev.filter((p) => String(p.timestamp || '') < String(oldestIncoming));
    return [...keepOlder, ...incoming];
  }
  const merged = [...prev, ...extras];
  merged.sort((a, b) => String(a.timestamp || '').localeCompare(String(b.timestamp || '')));
  return merged;
}

export function useLiveChatThread(chat: LiveChatItem | null, onChatUpdated?: () => void) {
  const [messages, setMessages] = useState<LiveChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [localStatus, setLocalStatus] = useState(chat?.status ?? 'bot');
  const loadingMoreRef = useRef(false);

  const social = chat ? isSocialChannelUser(chat.user_id, chat.channel) : false;

  const load = useCallback(
    async (mode: 'initial' | 'poll' = 'initial') => {
      if (!chat) return;
      if (mode === 'initial') {
        setLoading(true);
        setError(null);
      }
      try {
        const data = await fetchConversation(chat.user_id, chat.conversation_id, {
          days: 1,
          limit: 50,
        });
        if (!data.success) throw new Error(data.error || 'Failed to load thread');
        const next = data.messages || [];
        setMessages((prev) => (mode === 'poll' ? mergeChronological(prev, next) : next));
        if (mode === 'initial') {
          setHasMore(Boolean(data.has_more) || next.length >= 50);
        }
        if (data.status) setLocalStatus(data.status);
        if (mode === 'initial') {
          void markConversationRead(chat.user_id, chat.conversation_id);
        }
        if (mode === 'initial') setError(null);
      } catch (err) {
        if (mode === 'initial') {
          setError(err instanceof Error ? err.message : 'Could not load messages.');
          setMessages([]);
        }
      } finally {
        if (mode === 'initial') setLoading(false);
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
    loadOlder,
    takeover: (assignToUserId?: string) =>
      runAction(() => takeoverConversation(chat!, assignToUserId)),
    release: () => runAction(() => releaseConversation(chat!)),
    end: () => runAction(() => endConversation(chat!)),
    sendText: async (text: string) => {
      if (!chat || !text.trim()) return false;
      setBusy(true);
      setError(null);
      try {
        const result = await sendOperatorMessage(chat, text.trim(), 'text');
        if (!result.success) throw new Error(result.error || 'Send failed');
        await load('initial');
        onChatUpdated?.();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Send failed.');
        return false;
      } finally {
        setBusy(false);
      }
    },
    sendMedia: async (base64: string, type: 'voice' | 'image') => {
      if (!chat || !base64) return false;
      setBusy(true);
      setError(null);
      try {
        const result = await sendOperatorMessage(chat, base64, type);
        if (!result.success) throw new Error(result.error || 'Send failed');
        await load('initial');
        onChatUpdated?.();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Send failed.');
        return false;
      } finally {
        setBusy(false);
      }
    },
  };
}
