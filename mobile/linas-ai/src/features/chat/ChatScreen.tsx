import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { ChatMessageSchema, ConversationSummarySchema, type ChatMessage } from '../../api/types';
import { colors } from '../../theme/colors';

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

type Props = {
  onOpenControlCenter: () => void;
};

export function ChatScreen({ onOpenControlCenter }: Props) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
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
        setMessages(full.conversation.messages);
      } else {
        const created = await apiFetch('/api/owner-ai/conversations', {
          method: 'POST',
          body: JSON.stringify({}),
          schema: CreateConvSchema,
        });
        setConversationId(created.conversation.id);
        setMessages(created.conversation.messages);
        setHistory([{ id: created.conversation.id, title: created.conversation.title }]);
      }
    } catch {
      setError('Could not load chat. Pull to retry.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  async function send(confirmTool?: string) {
    if (!conversationId || (!draft.trim() && !confirmTool)) {
      return;
    }
    setSending(true);
    setError(null);
    const content = confirmTool ? `Confirm: ${confirmTool}` : draft.trim();
    if (!confirmTool) {
      setMessages((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}`,
          role: 'user',
          content,
          created_at: Date.now() / 1000,
        },
      ]);
      setDraft('');
    }
    try {
      const result = await apiFetch(`/api/owner-ai/conversations/${conversationId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content, confirm_tool: confirmTool ?? null }),
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

  async function newChat() {
    const created = await apiFetch('/api/owner-ai/conversations', {
      method: 'POST',
      body: JSON.stringify({}),
      schema: CreateConvSchema,
    });
    setConversationId(created.conversation.id);
    setMessages(created.conversation.messages);
    setHistory((prev) => [{ id: created.conversation.id, title: created.conversation.title }, ...prev]);
    setHistoryOpen(false);
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  return (
    <View style={styles.root}>
      <View style={styles.topBar}>
        <Pressable onPress={() => setHistoryOpen((v) => !v)}>
          <Text style={styles.topAction}>History</Text>
        </Pressable>
        <Text style={styles.title}>Linas AI</Text>
        <Pressable onPress={onOpenControlCenter}>
          <Text style={styles.topAction}>Control</Text>
        </Pressable>
      </View>

      {historyOpen ? (
        <View style={styles.drawer}>
          <Pressable onPress={newChat}>
            <Text style={styles.newChat}>+ New Chat</Text>
          </Pressable>
          {history.map((item) => (
            <Pressable
              key={item.id}
              onPress={async () => {
                const full = await apiFetch(`/api/owner-ai/conversations/${item.id}`, {
                  schema: GetConvSchema,
                });
                setConversationId(full.conversation.id);
                setMessages(full.conversation.messages);
                setHistoryOpen(false);
              }}
            >
              <Text style={styles.historyItem}>{item.title}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <FlatList
        data={messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <View style={[styles.bubble, item.role === 'user' ? styles.userBubble : styles.aiBubble]}>
            <Text style={styles.bubbleText}>{item.content}</Text>
          </View>
        )}
      />

      {pendingConfirm ? (
        <Pressable style={styles.confirm} onPress={() => void send(pendingConfirm)}>
          <Text style={styles.confirmText}>Confirm {pendingConfirm}</Text>
        </Pressable>
      ) : null}

      <View style={styles.composer}>
        <TextInput
          style={styles.input}
          placeholder="Message Linas AI"
          placeholderTextColor={colors.textMuted}
          value={draft}
          onChangeText={setDraft}
          multiline
        />
        <Pressable style={styles.send} onPress={() => void send()} disabled={sending}>
          {sending ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.sendText}>Send</Text>}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' },
  topBar: {
    paddingTop: 56,
    paddingHorizontal: 16,
    paddingBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  title: { color: colors.text, fontSize: 18, fontWeight: '700' },
  topAction: { color: colors.accent, fontWeight: '600' },
  drawer: { backgroundColor: colors.surface, padding: 16, maxHeight: 220 },
  newChat: { color: colors.accent, marginBottom: 12, fontWeight: '700' },
  historyItem: { color: colors.text, paddingVertical: 8 },
  list: { padding: 16, paddingBottom: 24 },
  bubble: { borderRadius: 16, padding: 12, marginBottom: 10, maxWidth: '90%' },
  userBubble: { alignSelf: 'flex-end', backgroundColor: colors.accentSoft },
  aiBubble: { alignSelf: 'flex-start', backgroundColor: colors.surfaceAlt },
  bubbleText: { color: colors.text, fontSize: 16, lineHeight: 22 },
  composer: {
    flexDirection: 'row',
    gap: 8,
    padding: 12,
    borderTopColor: colors.border,
    borderTopWidth: 1,
    alignItems: 'flex-end',
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    backgroundColor: colors.input,
    borderRadius: 12,
    color: colors.text,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  send: {
    backgroundColor: colors.accent,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  sendText: { color: colors.bg, fontWeight: '700' },
  error: { color: colors.danger, paddingHorizontal: 16, paddingTop: 8 },
  confirm: {
    marginHorizontal: 16,
    marginBottom: 8,
    backgroundColor: colors.surfaceAlt,
    borderRadius: 12,
    padding: 12,
    borderColor: colors.accent,
    borderWidth: 1,
  },
  confirmText: { color: colors.accent, fontWeight: '700', textAlign: 'center' },
});
