import { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { StatusChip } from '../../components/StatusChip';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { LikeFeedbackModal } from './LikeFeedbackModal';
import { LiveChatComposer } from './LiveChatComposer';
import { LiveChatMessageBubble } from './LiveChatMessageBubble';
import { saveFaqFromLiveChat } from './liveChatApi';
import {
  type LiveChatItem,
  type LiveChatMessage,
  isLikeableAiReply,
  messageBody,
  messageKey,
  normalizeStatus,
  previousUserQuestion,
  statusLabel,
  statusTone,
} from './liveChatTypes';
import { useLiveChatThread } from './useLiveChatThread';

type Props = {
  chat: LiveChatItem;
  onChatUpdated: () => void;
};

export function LiveChatThread({ chat, onChatUpdated }: Props) {
  const { tr } = useI18n();
  const thread = useLiveChatThread(chat, onChatUpdated);
  const status = normalizeStatus({ ...chat, status: thread.localStatus });
  const canMutate = !thread.social;
  const isHuman = status === 'human' || status === 'waiting_human';

  const [likeTarget, setLikeTarget] = useState<LiveChatMessage | null>(null);
  const [likeBusy, setLikeBusy] = useState(false);
  const [likeError, setLikeError] = useState<string | null>(null);

  const readOnlyReason = thread.social
    ? 'Instagram/Facebook conversations are read-only. Use WhatsApp for operator replies.'
    : status === 'bot' || status === 'closed'
      ? 'Take over this conversation to reply as a human.'
      : null;

  // Newest-first for inverted FlatList (WhatsApp: open at latest, scroll up = older).
  const listData = useMemo(() => [...thread.messages].reverse(), [thread.messages]);

  const likeInitialQuestion = likeTarget
    ? previousUserQuestion(thread.messages, likeTarget)
    : '';
  const likeInitialAnswer = likeTarget ? messageBody(likeTarget) : '';

  const submitLikeFaq = async (question: string, answer: string) => {
    setLikeBusy(true);
    setLikeError(null);
    try {
      await saveFaqFromLiveChat({
        question,
        answer,
        language: chat.language || 'ar',
      });
      setLikeTarget(null);
      Alert.alert(tr('likeFaqSavedTitle'), tr('likeFaqSavedBody'));
    } catch (err) {
      const msg = err instanceof Error ? err.message : tr('likeFaqSaveError');
      setLikeError(msg || tr('faqQuotaUpgrade'));
    } finally {
      setLikeBusy(false);
    }
  };

  return (
    <View style={styles.flex}>
      <View style={styles.toolbar}>
        <View style={styles.chips}>
          <StatusChip label={statusLabel(status)} tone={statusTone(status)} />
        </View>
        {canMutate ? (
          <View style={styles.actions}>
            {status !== 'human' ? (
              <Pressable
                style={[styles.actionBtn, styles.primary]}
                disabled={thread.busy}
                onPress={() => void thread.takeover()}
              >
                <Text style={styles.primaryLabel}>Take over</Text>
              </Pressable>
            ) : (
              <Pressable
                style={[styles.actionBtn, styles.ghost]}
                disabled={thread.busy}
                onPress={() => void thread.release()}
              >
                <Text style={styles.ghostLabel}>Return to AI</Text>
              </Pressable>
            )}
            {isHuman ? (
              <Pressable
                style={[styles.actionBtn, styles.danger]}
                disabled={thread.busy}
                onPress={() => void thread.end()}
              >
                <Text style={styles.dangerLabel}>End</Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}
      </View>

      {thread.error ? <Text style={styles.error}>{thread.error}</Text> : null}

      {thread.loading && !thread.messages.length ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : (
        <FlatList
          style={styles.flex}
          inverted
          data={listData}
          keyExtractor={(m, i) => messageKey(m, i)}
          contentContainerStyle={styles.messages}
          keyboardShouldPersistTaps="handled"
          onEndReached={() => {
            if (thread.hasMore && !thread.loadingMore) void thread.loadOlder();
          }}
          onEndReachedThreshold={0.2}
          ListEmptyComponent={
            <View style={styles.emptyFlip}>
              <EmptyState
                title="No messages yet"
                body="This conversation has no messages in the loaded window."
              />
            </View>
          }
          ListFooterComponent={
            thread.loadingMore ? (
              <ActivityIndicator color={colors.accent} style={styles.olderSpinner} />
            ) : thread.hasMore ? (
              <Text style={styles.olderHint}>Scroll up for older messages</Text>
            ) : thread.messages.length > 0 ? (
              <Text style={styles.olderHint}>Beginning of conversation</Text>
            ) : null
          }
          renderItem={({ item }) => (
            <LiveChatMessageBubble
              message={item}
              onLike={
                isLikeableAiReply(item)
                  ? () => {
                      setLikeError(null);
                      setLikeTarget(item);
                    }
                  : undefined
              }
            />
          )}
        />
      )}

      <LiveChatComposer
        busy={thread.busy}
        disabled={!canMutate || status === 'bot' || status === 'closed'}
        readOnlyReason={
          thread.social
            ? readOnlyReason
            : status === 'bot' || status === 'closed'
              ? readOnlyReason
              : null
        }
        onSendText={thread.sendText}
        onSendMedia={thread.sendMedia}
      />

      <LikeFeedbackModal
        visible={Boolean(likeTarget)}
        initialQuestion={likeInitialQuestion}
        initialAnswer={likeInitialAnswer}
        busy={likeBusy}
        error={likeError}
        onClose={() => {
          if (likeBusy) return;
          setLikeTarget(null);
          setLikeError(null);
        }}
        onSubmit={(q, a) => void submitLikeFaq(q, a)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: spacing.sm,
    paddingBottom: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  actionBtn: {
    borderRadius: radii.md,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  primary: { backgroundColor: colors.accent },
  ghost: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  danger: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.danger },
  primaryLabel: { color: colors.onAccent, fontFamily: fonts.bodyMedium, fontSize: 13 },
  ghostLabel: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 13 },
  dangerLabel: { color: colors.danger, fontFamily: fonts.bodyMedium, fontSize: 13 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  messages: { flexGrow: 1, paddingVertical: spacing.sm },
  olderSpinner: { marginVertical: 12 },
  olderHint: {
    textAlign: 'center',
    color: colors.textDim,
    fontFamily: fonts.body,
    fontSize: 12,
    paddingVertical: 10,
  },
  emptyFlip: { transform: [{ scaleY: -1 }] },
  error: { color: colors.danger, fontFamily: fonts.body, fontSize: 13, marginBottom: spacing.sm },
});
