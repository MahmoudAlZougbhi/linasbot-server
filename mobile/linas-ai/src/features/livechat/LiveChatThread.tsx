import { useMemo, useState } from 'react';
import {
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  View,
} from 'react-native';

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
import {
  type LiveChatItem,
  type LiveChatMessage,
  isLikeableAiReply,
  messageBody,
  messageKey,
  previousUserQuestion,
} from './liveChatTypes';
import { useLiveChatThread } from './useLiveChatThread';

type Props = {
  chat: LiveChatItem;
  onChatUpdated: () => void;
};

export function LiveChatThread({ chat, onChatUpdated }: Props) {
  const { tr } = useI18n();
  const thread = useLiveChatThread(chat, onChatUpdated);
  const [assignOpen, setAssignOpen] = useState(false);
  const [likeTarget, setLikeTarget] = useState<LiveChatMessage | null>(null);
  const [likeBusy, setLikeBusy] = useState(false);
  const [likeError, setLikeError] = useState<string | null>(null);

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
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={88}
    >
      <LiveChatThreadActions
        chat={chat}
        localStatus={thread.localStatus}
        busy={thread.busy}
        social={thread.social}
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

      {!thread.social ? (
        <LiveChatComposer
          onSend={(text) => thread.sendText(text)}
          busy={thread.busy}
        />
      ) : null}

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
});
