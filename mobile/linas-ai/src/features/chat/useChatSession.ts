import { useCallback, useEffect, useRef, useState } from 'react';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { getStoredAppLanguage } from '../../i18n/languageStore';
import type { ChatMessage } from '../../api/types';
import {
  CreateConvSchema,
  GetConvSchema,
  ListConvSchema,
  type ProposedPatch,
} from './chatSessionSchemas';
import {
  listedHistoryEntries,
  upsertStartedHistoryEntry,
  dropUnstartedHistoryEntry,
  type HistoryEntry,
} from './chatHistoryVisibility';
import {
  autoTitleFromFirstMessage,
  isDefaultConversationTitle,
} from './chatSessionTitle';
import {
  OWNER_MESSAGE_PAGE,
  conversationMessagesUrl,
  mergeLatestWindow,
  messagesIncludeAssistantReply,
  prependOlderUnique,
} from './ownerChatPaging';

const SYNC_AFTER_TURN_RETRY_MS = [0, 150, 350, 700];

export type SyncAfterTurnOptions = {
  /** Retry until this streamed reply appears in persisted messages. */
  expectReplyText?: string;
};

export type { ProposedPatch } from './chatSessionSchemas';
export type { HistoryEntry } from './chatHistoryVisibility';
export { autoTitleFromFirstMessage, isDefaultConversationTitle } from './chatSessionTitle';

async function createOwnerConversation() {
  return apiFetch('/api/owner-ai/conversations', {
    method: 'POST',
    body: JSON.stringify({ language: getStoredAppLanguage() }),
    schema: CreateConvSchema,
  });
}

function seedTypewriterId(messages: ChatMessage[]): string | null {
  const seed = messages[0];
  return seed?.role === 'assistant' && messages.length === 1 ? seed.id : null;
}

export function useChatSession(enabled = true) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [title, setTitle] = useState('Linas AI');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<string | null>(null);
  const [proposedPatch, setProposedPatch] = useState<ProposedPatch | null>(null);
  const [quickActions, setQuickActions] = useState<{ id: string; label: string }[]>([]);
  /** Message id of a freshly seeded greeting to type into the bubble once. */
  const [seedTypewriterMessageId, setSeedTypewriterMessageId] = useState<string | null>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const conversationIdRef = useRef(conversationId);
  conversationIdRef.current = conversationId;
  const hasMoreRef = useRef(hasMore);
  hasMoreRef.current = hasMore;
  const loadingMoreRef = useRef(false);

  const bootstrap = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      setConversationId(null);
      setTitle('Linas AI');
      setMessages([]);
      setHistory([]);
      setHasMore(false);
      setSeedTypewriterMessageId(null);
      setPendingConfirm(null);
      setProposedPatch(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const listed = await apiFetch('/api/owner-ai/conversations', { schema: ListConvSchema });
      setHistory(listedHistoryEntries(listed.conversations));
      const created = await createOwnerConversation();
      setConversationId(created.conversation.id);
      setTitle(created.conversation.title);
      setMessages(created.conversation.messages);
      setHasMore(false);
      setSeedTypewriterMessageId(seedTypewriterId(created.conversation.messages));
    } catch {
      setError('retry');
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  /** Soft sync after a stream turn — refresh history + latest page; keep older prepended pages. */
  const syncAfterTurn = useCallback(
    async (opts?: SyncAfterTurnOptions): Promise<boolean> => {
      if (!enabled) return false;
      const activeId = conversationId;
      if (!activeId) return false;
      const expectReply = opts?.expectReplyText?.trim() || '';
      try {
        let synced = false;
        for (let attempt = 0; attempt < SYNC_AFTER_TURN_RETRY_MS.length; attempt++) {
          if (SYNC_AFTER_TURN_RETRY_MS[attempt] > 0) {
            await new Promise((resolve) => setTimeout(resolve, SYNC_AFTER_TURN_RETRY_MS[attempt]));
          }
          const listed = await apiFetch('/api/owner-ai/conversations', { schema: ListConvSchema });
          setHistory(listedHistoryEntries(listed.conversations));
          const full = await apiFetch(conversationMessagesUrl(activeId), { schema: GetConvSchema });
          if (conversationIdRef.current !== activeId) return false;

          const merged = mergeLatestWindow(messagesRef.current, full.conversation.messages);
          setTitle(full.conversation.title);
          setMessages(merged);
          messagesRef.current = merged;

          if (!expectReply || messagesIncludeAssistantReply(merged, expectReply)) {
            synced = true;
            break;
          }
        }
        if (!synced && expectReply) {
          setMessages((prev) => {
            if (messagesIncludeAssistantReply(prev, expectReply)) return prev;
            return [
              ...prev,
              {
                id: `local-assistant-${Date.now()}`,
                role: 'assistant',
                content: expectReply,
                created_at: Date.now() / 1000,
              },
            ];
          });
          synced = true;
        }
        return synced;
      } catch {
        /* keep live stream bubble; user can retry via error banner */
        return false;
      }
    },
    [conversationId, enabled],
  );

  const applyConversationTitle = useCallback(
    (id: string, nextTitle: string, opts?: { onlyIfDefault?: boolean }) => {
      const cleaned = (nextTitle || '').trim();
      if (!cleaned) return;
      setHistory((prev) => {
        const current = prev.find((h) => h.id === id);
        if (current && opts?.onlyIfDefault && !isDefaultConversationTitle(current.title)) {
          return prev;
        }
        return upsertStartedHistoryEntry(prev, { id, title: cleaned, archived: current?.archived });
      });
      setConversationId((current) => {
        if (current === id) {
          setTitle((prevTitle) => {
            if (opts?.onlyIfDefault && !isDefaultConversationTitle(prevTitle)) return prevTitle;
            return cleaned;
          });
        }
        return current;
      });
    },
    [],
  );

  /** Optimistic ChatGPT-style title from first user message while still untitled. */
  const autoTitleFromOutgoing = useCallback(
    (content: string) => {
      if (!conversationId || !isDefaultConversationTitle(title)) return;
      const next = autoTitleFromFirstMessage(content);
      if (isDefaultConversationTitle(next)) return;
      applyConversationTitle(conversationId, next);
    },
    [applyConversationTitle, conversationId, title],
  );

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  async function openConversation(id: string) {
    const full = await apiFetch(conversationMessagesUrl(id), { schema: GetConvSchema });
    setConversationId(full.conversation.id);
    setTitle(full.conversation.title);
    setMessages(full.conversation.messages);
    setHasMore(Boolean(full.conversation.has_more));
    setPendingConfirm(null);
    setProposedPatch(null);
    setSeedTypewriterMessageId(null);
  }

  async function newChat() {
    // Clear prior transcript immediately so Chat|Work can show under the logo while create resolves.
    setMessages([]);
    setHasMore(false);
    setPendingConfirm(null);
    setProposedPatch(null);
    setSeedTypewriterMessageId(null);
    const created = await createOwnerConversation();
    setConversationId(created.conversation.id);
    setTitle(created.conversation.title);
    setMessages(created.conversation.messages);
    setHasMore(false);
    setSeedTypewriterMessageId(seedTypewriterId(created.conversation.messages));
  }

  const loadOlder = useCallback(async () => {
    if (!enabled || !conversationId || !hasMoreRef.current || loadingMoreRef.current) return;
    const oldest = messagesRef.current[0]?.id;
    if (!oldest || oldest.startsWith('local-')) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const page = await apiFetch(
        conversationMessagesUrl(conversationId, { limit: OWNER_MESSAGE_PAGE, before: oldest }),
        { schema: GetConvSchema },
      );
      setMessages((prev) => prependOlderUnique(prev, page.conversation.messages));
      setHasMore(Boolean(page.conversation.has_more));
    } catch {
      /* keep current window; user can scroll again */
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, [conversationId, enabled]);

  async function renameConversation(id: string, nextTitle: string) {
    await apiFetch(`/api/owner-ai/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title: nextTitle }),
      schema: z.object({ success: z.literal(true) }),
    });
    setHistory((prev) => prev.map((h) => (h.id === id ? { ...h, title: nextTitle } : h)));
    if (id === conversationId) setTitle(nextTitle);
  }

  async function setArchived(id: string, archived: boolean) {
    await apiFetch(`/api/owner-ai/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ archived }),
      schema: z.object({ success: z.literal(true) }),
    });
    setHistory((prev) => prev.map((h) => (h.id === id ? { ...h, archived } : h)));
  }

  async function deleteConversation(id: string) {
    await apiFetch(`/api/owner-ai/conversations/${id}`, {
      method: 'DELETE',
      schema: z.object({ success: z.literal(true) }),
    });
    setHistory((prev) => prev.filter((h) => h.id !== id));
    if (id === conversationId) await newChat();
  }

  function appendOptimisticUser(content: string, localImageUris?: string[]) {
    const id = `local-${Date.now()}`;
    const activeId = conversationId;
    setSeedTypewriterMessageId(null);
    if (activeId) {
      setHistory((prev) => upsertStartedHistoryEntry(prev, { id: activeId, title }));
    }
    setMessages((prev) => [
      ...prev,
      {
        id,
        role: 'user',
        content,
        created_at: Date.now() / 1000,
        local_image_uris: localImageUris?.length ? localImageUris : undefined,
      },
    ]);
    return id;
  }

  function removeOptimisticUser(id: string) {
    const activeId = conversationId;
    setMessages((prev) => {
      const next = prev.filter((m) => m.id !== id);
      setHistory((h) => dropUnstartedHistoryEntry(h, activeId, next));
      return next;
    });
  }

  const clearSeedTypewriter = useCallback(() => {
    setSeedTypewriterMessageId(null);
  }, []);

  return {
    conversationId,
    title,
    messages,
    history,
    loading,
    loadingMore,
    hasMore,
    sending,
    error,
    pendingConfirm,
    proposedPatch,
    quickActions,
    seedTypewriterMessageId,
    clearSeedTypewriter,
    bootstrap,
    syncAfterTurn,
    applyConversationTitle,
    autoTitleFromOutgoing,
    openConversation,
    newChat,
    loadOlder,
    renameConversation,
    setArchived,
    deleteConversation,
    appendOptimisticUser,
    removeOptimisticUser,
    setError,
    setProposedPatch,
    setPendingConfirm,
    setSending,
    setQuickActions,
  };
}
