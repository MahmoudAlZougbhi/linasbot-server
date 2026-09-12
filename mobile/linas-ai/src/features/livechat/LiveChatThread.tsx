import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { EmptyState } from '../../components/EmptyState';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { LikeFeedbackModal } from './LikeFeedbackModal';
import { LiveChatAssignSheet } from './LiveChatAssignSheet';
import { LiveChatComposer } from './LiveChatComposer';
import { LiveChatMessageBubble } from './LiveChatMessageBubble';
import { LiveChatThreadActions } from './LiveChatThreadActions';
import { saveFaqFromLiveChat } from './liveChatApi';
import { chatChannel } from './liveChatHelpers';
import {
  type LiveChatItem,
  type LiveChatMessage,
  isLikeableAiReply,
  messageBody,
  messageKey,
  previousUserQuestion,
} from './liveChatTypes';
import { useLiveChatThread } from './useLiveChatThread';
import type { LiveChatSseEvent } from './liveChatSseParse';

type Props = {
  chat: LiveChatItem;
  onChatUpdated: () => void;
  realtimeEvent?: { seq: number; event: LiveChatSseEvent } | null;
  sseConnectedAt?: number;
};

export function LiveChatThread({
  chat,
  onChatUpdated,
  realtimeEvent = null,
  sseConnectedAt = 0,
}: Props) {
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  const thread = useLiveChatThread(chat, onChatUpdated);

  useEffect(() => {
    if (!realtimeEvent) return;
    thread.applyRealtime(realtimeEvent.event.data, realtimeEvent.event.type);
    // Apply each pushed event once; do not depend on applyRealtime identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [realtimeEvent?.seq]);

  useEffect(() => {
    if (!sseConnectedAt) return;
    thread.reloadQuiet();
    // Catch-up after SSE connect/reconnect only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sseConnectedAt]);
  const [assignOpen, setAssignOpen] = useState(false);
  const [likeTarget, setLikeTarget] = useState<LiveChatMessage | null>(null);
  const [likeBusy, setLikeBusy] = useState(false);
  const [likeError, setLikeError] = useState<string | null>(null);
  const [awayFromLatest, setAwayFromLatest] = useState(false);
  const [unseenIncoming, setUnseenIncoming] = useState(false);
  const listRef = useRef<FlatList<LiveChatMessage>>(null);
  const messageCountRef = useRef(0);

  const listData = useMemo(() => [...thread.messages].reverse(), [thread.messages]);
  useEffect(() => {
    if (thread.messages.length > messageCountRef.current && awayFromLatest) {
      setUnseenIncoming(true);
    }
    messageCountRef.current = thread.messages.length;
  }, [thread.messages.length, awayFromLatest]);
  const allowOperatorMedia = chatChannel(chat) !== 'tiktok' && chatChannel(chat) !== 'web';
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
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? insets.top + 68 : 0}
    >
      <LiveChatThreadActions
        chat={chat}
        localStatus={thread.localStatus}
        busy={thread.busy}
        onTakeover={() => void thread.takeover()}
        onRelease={() => void thread.release()}
        onAssign={() => setAssignOpen(true)}
      />

      {thread.error ? <Text style={styles.error}>{thread.error}</Text> : null}

      {thread.loading && !thread.messages.length ? (
        <View style={styles.center}>
          <LinasLoadingIndicator variant="screen" />
        </View>
      ) : (
        <FlatList
          ref={listRef}
          style={styles.flex}
          inverted
          data={listData}
          keyExtractor={(m, i) => messageKey(m, i)}
          contentContainerStyle={styles.messages}
          keyboardShouldPersistTaps="handled"
          maintainVisibleContentPosition={{ minIndexForVisible: 0 }}
          onScroll={(e) => {
            const away = e.nativeEvent.contentOffset.y > 140;
            setAwayFromLatest(away);
            if (!away) setUnseenIncoming(false);
          }}
          scrollEventThrottle={64}
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
              <LinasLoadingIndicator variant="inline" style={styles.olderSpinner} />
            ) : thread.hasMore ? (
              <Text style={styles.olderHint}>Scroll up for older messages</Text>
            ) : thread.messages.length > 0 ? (
              <Text style={styles.olderHint}>Beginning of conversation</Text>
            ) : null
          }
          renderItem={({ item }) => (
            <LiveChatMessageBubble
              message={item}
              onRetry={
                item.delivery_status === 'failed' && !item.is_user
                  ? () => {
                      thread.retryFailedSend(item);
                    }
                  : undefined
              }
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

      {unseenIncoming && awayFromLatest ? (
        <Text
          onPress={() => {
            listRef.current?.scrollToOffset({ offset: 0, animated: true });
            setUnseenIncoming(false);
            setAwayFromLatest(false);
          }}
          style={styles.newMsg}
        >
          New messages
        </Text>
      ) : null}

      <LiveChatComposer
        onSend={(text) => thread.sendText(text)}
        onSendMedia={
          allowOperatorMedia
            ? (base64, type, mime) => thread.sendMedia(base64, type, mime)
            : undefined
        }
        busy={thread.busy || (thread.loading && !thread.messages.length)}
      />

      <LiveChatAssignSheet
        visible={assignOpen}
        busy={thread.busy}
        onClose={() => setAssignOpen(false)}
        onPick={(staff) => {
          setAssignOpen(false);
          void thread.takeover(staff.id);
        }}
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
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
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
  newMsg: {
    alignSelf: 'center',
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: colors.accent,
    color: colors.onAccent,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
  },
});
