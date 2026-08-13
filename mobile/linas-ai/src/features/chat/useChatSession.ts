import { useCallback, useEffect, useRef, useState } from 'react';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { getStoredAppLanguage } from '../../i18n/languageStore';
import { ChatMessageSchema, ConversationSummarySchema, type ChatMessage } from '../../api/types';
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
import { clearPreferFreshOwnerChat, isPreferFreshOwnerChat } from './preferFreshOwnerChat';

const CreateConvSchema = z.object({
  success: z.literal(true),
  conversation: z.object({
    id: z.string(),
    title: z.string(),
    messages: z.array(ChatMessageSchema),
    setup_stage: z.string().optional(),
    greeting_language: z.string().optional(),
    welcome_chips: z
      .array(
        z.object({
          id: z.string(),
          label: z.string(),
          mode: z.enum(['chat', 'work']),
          prompt: z.string(),
        }),
      )
      .optional(),
  }),
});

const GetConvSchema = z.object({
  success: z.literal(true),
  conversation: z.object({
    id: z.string(),
    title: z.string(),
    messages: z.array(ChatMessageSchema),
    has_more: z.boolean().optional(),
    total_messages: z.number().optional(),
  }),
});

const ListConvSchema = z.object({
  success: z.literal(true),
  conversations: z.array(ConversationSummarySchema),
});

const ProposedPatchSchema = z
  .object({
    proposal_id: z.string().optional(),
    confirmation_token: z.string().optional(),
    preview: z.record(z.string(), z.unknown()).optional(),
  })
  .nullable()
  .optional();

const SendSchema = z.object({
  success: z.literal(true),
  message: ChatMessageSchema.nullable(),
  pending_confirmation: z.string().nullable().optional(),
  proposed_patch: ProposedPatchSchema,
  quick_actions: z.array(z.object({ id: z.string(), label: z.string() })).optional(),
  setup_stage: z.string().nullable().optional(),
});

export type ProposedPatch = {
  proposal_id?: string;
  confirmation_token?: string;
  preview?: Record<string, unknown>;
};

/** @deprecated Creative Studio cancelled — type retained only so dead UI files typecheck. */
export type CreativeDraft = {
  status?: string;
  kind?: string;
  text?: string;
  prompt?: string;
  reason?: string;
  job_id?: string;
  model?: string;
  task_options?: { id: string; label: string }[];
  actions?: {
    edit?: boolean;
    regenerate?: boolean;
    schedule?: boolean;
    publish?: boolean;
    publish_reason?: string;
  };
};

export type HistoryEntry = { id: string; title: string; archived?: boolean };

const DEFAULT_TITLES = new Set(['New chat', 'Chat', 'Untitled', 'Linas AI', '']);

export function isDefaultConversationTitle(title: string | null | undefined): boolean {
  return DEFAULT_TITLES.has((title || '').trim());
}

/** Match server auto_title_from_first_message — first user text, single line, max 60. */
export function autoTitleFromFirstMessage(content: string, maxLen = 60): string {
  const cleaned = String(content || '')
    .replace(/\r/g, '\n')
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');
  if (!cleaned) return 'New chat';
  if (cleaned.length <= maxLen) return cleaned;
  return cleaned.slice(0, maxLen).trimEnd();
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
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const listed = await apiFetch('/api/owner-ai/conversations', { schema: ListConvSchema });
      setHistory(
        listed.conversations.map((c) => ({
          id: c.id,
          title: c.title,
          archived: Boolean(c.archived),
        })),
      );
      const preferFresh = await isPreferFreshOwnerChat();
      const active = listed.conversations.find((c) => !c.archived) || listed.conversations[0];
      if (active && !preferFresh) {
        const full = await apiFetch(conversationMessagesUrl(active.id), { schema: GetConvSchema });
        setConversationId(full.conversation.id);
        setTitle(full.conversation.title);
        setMessages(full.conversation.messages);
        setHasMore(Boolean(full.conversation.has_more));
        setSeedTypewriterMessageId(null);
      } else {
        const created = await apiFetch('/api/owner-ai/conversations', {
          method: 'POST',
          body: JSON.stringify({ language: getStoredAppLanguage() }),
          schema: CreateConvSchema,
        });
        if (preferFresh) {
          await clearPreferFreshOwnerChat();
        }
        setConversationId(created.conversation.id);
        setTitle(created.conversation.title);
        setMessages(created.conversation.messages);
        setHasMore(false);
        setHistory((prev) =>
          preferFresh && prev.length
            ? [{ id: created.conversation.id, title: created.conversation.title }, ...prev]
            : [{ id: created.conversation.id, title: created.conversation.title }],
        );
        const seed = created.conversation.messages[0];
        setSeedTypewriterMessageId(
          seed?.role === 'assistant' && created.conversation.messages.length === 1 ? seed.id : null,
        );
      }
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
          setHistory(
            listed.conversations.map((c) => ({
              id: c.id,
              title: c.title,
              archived: Boolean(c.archived),
            })),
          );
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
      setHistory((prev) =>
        prev.map((h) => {
          if (h.id !== id) return h;
          if (opts?.onlyIfDefault && !isDefaultConversationTitle(h.title)) return h;
          return { ...h, title: cleaned };
        }),
      );
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
    const created = await apiFetch('/api/owner-ai/conversations', {
      method: 'POST',
      body: JSON.stringify({ language: getStoredAppLanguage() }),
      schema: CreateConvSchema,
    });
    setConversationId(created.conversation.id);
    setTitle(created.conversation.title);
    setMessages(created.conversation.messages);
    setHasMore(false);
    setHistory((prev) => [{ id: created.conversation.id, title: created.conversation.title }, ...prev]);
    const seed = created.conversation.messages[0];
    setSeedTypewriterMessageId(
      seed?.role === 'assistant' && created.conversation.messages.length === 1 ? seed.id : null,
    );
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
    setSeedTypewriterMessageId(null);
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
    setMessages((prev) => prev.filter((m) => m.id !== id));
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
