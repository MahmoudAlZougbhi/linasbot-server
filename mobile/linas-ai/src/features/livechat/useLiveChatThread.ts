import { useCallback, useEffect, useState } from 'react';

import {
  endConversation,
  fetchConversation,
  markConversationRead,
  releaseConversation,
  sendOperatorMessage,
  takeoverConversation,
} from './liveChatApi';
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

  const social = chat ? isSocialChannelUser(chat.user_id, chat.channel) : false;

  const load = useCallback(async () => {
    if (!chat) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchConversation(chat.user_id, chat.conversation_id, {
        days: 1,
        limit: 50,
      });
      if (!data.success) throw new Error(data.error || 'Failed to load thread');
      setMessages(data.messages);
      setHasMore(Boolean(data.has_more) || (data.messages?.length ?? 0) >= 50);
      if (data.status) setLocalStatus(data.status);
      void markConversationRead(chat.user_id, chat.conversation_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load messages.');
      setMessages([]);
    } finally {
      setLoading(false);
    }
  }, [chat]);

  useEffect(() => {
    setLocalStatus(chat?.status ?? 'bot');
    void load();
    if (!chat) return;
    const id = setInterval(() => void load(), 15_000);
    return () => clearInterval(id);
  }, [chat, load]);

  const loadOlder = useCallback(async () => {
    if (!chat || !messages.length || loadingMore) return;
    const oldest = messages[0]?.timestamp;
    if (!oldest) return;
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
        const seen = new Set(prev.map((m) => `${m.timestamp}|${m.content}|${m.text}`));
        const merged = [...older.filter((m) => !seen.has(`${m.timestamp}|${m.content}|${m.text}`)), ...prev];
        return merged;
      });
      setHasMore(older.length >= 20);
    } catch {
      // keep thread
    } finally {
      setLoadingMore(false);
    }
  }, [chat, loadingMore, messages]);

  async function runAction(fn: () => Promise<{ success: boolean; error?: string; message?: string; status?: string }>) {
    if (!chat || social) return;
    setBusy(true);
    setError(null);
    try {
      const result = await fn();
      if (!result.success) throw new Error(result.error || result.message || 'Action failed');
      if (result.status) setLocalStatus(result.status);
      await load();
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
    reload: load,
    loadOlder,
    takeover: () => runAction(() => takeoverConversation(chat!)),
    release: () => runAction(() => releaseConversation(chat!)),
    end: () => runAction(() => endConversation(chat!)),
    sendText: async (text: string) => {
      if (!chat || social || !text.trim()) return false;
      setBusy(true);
      setError(null);
      try {
        const result = await sendOperatorMessage(chat, text.trim(), 'text');
        if (!result.success) throw new Error(result.error || 'Send failed');
        await load();
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
      if (!chat || social || !base64) return false;
      setBusy(true);
      setError(null);
      try {
        const result = await sendOperatorMessage(chat, base64, type);
        if (!result.success) throw new Error(result.error || 'Send failed');
        await load();
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
