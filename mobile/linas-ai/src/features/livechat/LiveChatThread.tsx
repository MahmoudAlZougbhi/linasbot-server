import { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { StatusChip } from '../../components/StatusChip';
import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { LikeFeedbackModal } from './LikeFeedbackModal';
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

  const [likeTarget, setLikeTarget] = useState<LiveChatMessage | null>(null);
  const [likeBusy, setLikeBusy] = useState(false);
  const [likeError, setLikeError] = useState<string | null>(null);

  // V2: Live Chat is strictly read-only — no composer, takeover, release, or end.
  const readOnlyReason =
    'Live Chat is read-only. Use System Copilot for diagnosis and Content Management fixes.';

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
          <View style={styles.readOnlyChip}>
            <AppIcon icon={feather('lock')} size={12} color={colors.textMuted} />
            <StatusChip label="Read-only" tone="soon" />
          </View>
        </View>
      </View>

      {thread.error ? <Text style={styles.error}>{thread.error}</Text> : null}
      <View style={styles.readOnlyBannerRow} accessibilityLabel={readOnlyReason}>
        <AppIcon icon={feather('lock')} size={14} color={colors.textMuted} />
        <Text style={styles.readOnlyBanner}>{readOnlyReason}</Text>
      </View>

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
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, alignItems: 'center' },
  readOnlyChip: { flexDirection: 'row', alignItems: 'center', gap: 4 },
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
  readOnlyBannerRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginBottom: spacing.sm,
  },
  readOnlyBanner: {
    flex: 1,
    color: colors.textMuted,
    fontFamily: fonts.body,
    fontSize: 12,
  },
});
