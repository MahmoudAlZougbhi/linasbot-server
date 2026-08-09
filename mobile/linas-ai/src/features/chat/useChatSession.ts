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
  quick_actions: z
    .array(z.object({ id: z.string(), label: z.string() }))
    .optional(),
  setup_stage: z.string().nullable().optional(),
});

export type ProposedPatch = {
  proposal_id?: string;
  confirmation_token?: string;
  preview?: Record<string, unknown>;
};

export function useChatSession(enabled = true) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [title, setTitle] = useState('Linas AI');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [history, setHistory] = useState<{ id: string; title: string }[]>([]);
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
      setHistory(listed.conversations.map((c) => ({ id: c.id, title: c.title })));
      if (listed.conversations[0]) {
        const full = await apiFetch(`/api/owner-ai/conversations/${listed.conversations[0].id}`, {
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

  async function send(content: string, confirmTool?: string) {
    if (!conversationId || (!content.trim() && !confirmTool)) {
      return;
    }
    setSending(true);
    setError(null);
    const body = confirmTool ? `Confirm: ${confirmTool}` : content.trim();
    if (!confirmTool) {
      setMessages((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}`,
          role: 'user',
          content: body,
          created_at: Date.now() / 1000,
        },
      ]);
    }
    try {
      const result = await apiFetch(`/api/owner-ai/conversations/${conversationId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content: body, confirm_tool: confirmTool ?? null }),
        schema: SendSchema,
      });
      if (result.message) {
        setMessages((prev) => [...prev, result.message as ChatMessage]);
      }
      setPendingConfirm(result.pending_confirmation ?? null);
      setProposedPatch(result.proposed_patch ?? null);
      if (result.quick_actions?.length) {
        setQuickActions(result.quick_actions);
      }
    } catch {
      setError('messageFailed');
    } finally {
      setSending(false);
    }
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
    openConversation,
    newChat,
    send,
    setError,
    setProposedPatch,
    setPendingConfirm,
  };
}
