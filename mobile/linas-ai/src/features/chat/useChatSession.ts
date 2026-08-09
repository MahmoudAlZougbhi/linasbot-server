import { useCallback, useEffect, useState } from 'react';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { ChatMessageSchema, ConversationSummarySchema, type ChatMessage } from '../../api/types';

const CreateConvSchema = z.object({
  success: z.literal(true),
  conversation: z.object({
    id: z.string(),
    title: z.string(),
    messages: z.array(ChatMessageSchema),
    setup_stage: z.string().optional(),
  }),
});

const GetConvSchema = z.object({
  success: z.literal(true),
  conversation: z.object({
    id: z.string(),
    title: z.string(),
    messages: z.array(ChatMessageSchema),
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
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<string | null>(null);
  const [proposedPatch, setProposedPatch] = useState<ProposedPatch | null>(null);
  const [quickActions, setQuickActions] = useState<{ id: string; label: string }[]>([]);

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
      const active = listed.conversations.find((c) => !c.archived) || listed.conversations[0];
      if (active) {
        const full = await apiFetch(`/api/owner-ai/conversations/${active.id}`, {
          schema: GetConvSchema,
        });
        setConversationId(full.conversation.id);
        setTitle(full.conversation.title);
        setMessages(full.conversation.messages);
      } else {
        const created = await apiFetch('/api/owner-ai/conversations', {
          method: 'POST',
          body: JSON.stringify({}),
          schema: CreateConvSchema,
        });
        setConversationId(created.conversation.id);
        setTitle(created.conversation.title);
        setMessages(created.conversation.messages);
        setHistory([{ id: created.conversation.id, title: created.conversation.title }]);
      }
    } catch {
      setError('retry');
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  /** Soft sync after a stream turn — refresh history + active thread without full-screen loading. */
  const syncAfterTurn = useCallback(async () => {
    if (!enabled) return;
    const activeId = conversationId;
    if (!activeId) return;
    try {
      const listed = await apiFetch('/api/owner-ai/conversations', { schema: ListConvSchema });
      setHistory(
        listed.conversations.map((c) => ({
          id: c.id,
          title: c.title,
          archived: Boolean(c.archived),
        })),
      );
      const full = await apiFetch(`/api/owner-ai/conversations/${activeId}`, {
        schema: GetConvSchema,
      });
      // Ignore if user switched chats while the request was in flight.
      setConversationId((current) => {
        if (current === activeId) {
          setTitle(full.conversation.title);
          setMessages(full.conversation.messages);
        }
        return current;
      });
    } catch {
      /* keep optimistic UI; user can retry via error banner */
    }
  }, [conversationId, enabled]);

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
    const full = await apiFetch(`/api/owner-ai/conversations/${id}`, { schema: GetConvSchema });
    setConversationId(full.conversation.id);
    setTitle(full.conversation.title);
    setMessages(full.conversation.messages);
    setPendingConfirm(null);
    setProposedPatch(null);
  }

  async function newChat() {
    const created = await apiFetch('/api/owner-ai/conversations', {
      method: 'POST',
      body: JSON.stringify({}),
      schema: CreateConvSchema,
    });
    setConversationId(created.conversation.id);
    setTitle(created.conversation.title);
    setMessages(created.conversation.messages);
    setHistory((prev) => [{ id: created.conversation.id, title: created.conversation.title }, ...prev]);
    setPendingConfirm(null);
    setProposedPatch(null);
  }

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

  return {
    conversationId,
    title,
    messages,
    history,
    loading,
    sending,
    error,
    pendingConfirm,
    proposedPatch,
    quickActions,
    bootstrap,
    syncAfterTurn,
    applyConversationTitle,
    autoTitleFromOutgoing,
    openConversation,
    newChat,
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
