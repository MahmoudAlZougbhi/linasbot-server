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

const CreativeDraftSchema = z
  .object({
    status: z.string().optional(),
    kind: z.string().optional(),
    text: z.string().optional(),
    prompt: z.string().optional(),
    reason: z.string().optional(),
    job_id: z.string().optional(),
    model: z.string().optional(),
    task_options: z.array(z.object({ id: z.string(), label: z.string() })).optional(),
    actions: z
      .object({
        edit: z.boolean().optional(),
        regenerate: z.boolean().optional(),
        schedule: z.boolean().optional(),
        publish: z.boolean().optional(),
        publish_reason: z.string().optional(),
      })
      .optional(),
  })
  .nullable()
  .optional();

const SendSchema = z.object({
  success: z.literal(true),
  message: ChatMessageSchema.nullable(),
  pending_confirmation: z.string().nullable().optional(),
  proposed_patch: ProposedPatchSchema,
  creative_draft: CreativeDraftSchema,
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
  const [creativeDraft, setCreativeDraft] = useState<CreativeDraft | null>(null);
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
    setCreativeDraft(null);
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
    setCreativeDraft(null);
  }

  async function send(
    content: string,
    confirmTool?: string,
    toolArgs?: Record<string, unknown>,
  ) {
    if (!conversationId || (!content.trim() && !confirmTool)) {
      return;
    }
    setSending(true);
    setError(null);
    const trimmed = content.trim();
    // High-impact confirms keep a visible "Confirm: …" line; tool-only actions may send empty content.
    const apiContent = confirmTool
      ? trimmed || (confirmTool.startsWith('approve_') || confirmTool === 'publish_cm' ? `Confirm: ${confirmTool}` : '')
      : trimmed;
    if (!confirmTool && trimmed) {
      setMessages((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}`,
          role: 'user',
          content: trimmed,
          created_at: Date.now() / 1000,
        },
      ]);
    }
    try {
      const result = await apiFetch(`/api/owner-ai/conversations/${conversationId}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          content: apiContent,
          confirm_tool: confirmTool ?? null,
          tool_args: toolArgs ?? null,
        }),
        schema: SendSchema,
      });
      if (result.message) {
        setMessages((prev) => [...prev, result.message as ChatMessage]);
      }
      setPendingConfirm(result.pending_confirmation ?? null);
      setProposedPatch(result.proposed_patch ?? null);
      if (result.creative_draft) {
        setCreativeDraft(result.creative_draft);
      }
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
    creativeDraft,
    quickActions,
    bootstrap,
    openConversation,
    newChat,
    send,
    setError,
    setProposedPatch,
    setPendingConfirm,
    setCreativeDraft,
  };
}
