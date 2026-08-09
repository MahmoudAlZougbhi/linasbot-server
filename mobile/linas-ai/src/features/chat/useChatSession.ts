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

const SendSchema = z.object({
  success: z.literal(true),
  message: ChatMessageSchema.nullable(),
  pending_confirmation: z.string().nullable().optional(),
});

export function useChatSession() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [title, setTitle] = useState('Linas AI');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [history, setHistory] = useState<{ id: string; title: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<string | null>(null);

  const bootstrap = useCallback(async () => {
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
      setError('Could not load chat. Tap Retry.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  async function openConversation(id: string) {
    const full = await apiFetch(`/api/owner-ai/conversations/${id}`, { schema: GetConvSchema });
    setConversationId(full.conversation.id);
    setTitle(full.conversation.title);
    setMessages(full.conversation.messages);
    setPendingConfirm(null);
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
    } catch {
      setError('Message failed. You can retry.');
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
    bootstrap,
    openConversation,
    newChat,
    send,
    setError,
  };
}
