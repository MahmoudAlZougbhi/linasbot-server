import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';
import { LiveChatComposer } from './LiveChatComposer';
import { LiveChatMessageBubble } from './LiveChatMessageBubble';
import {
  type LiveChatItem,
  channelLabel,
  chatTitle,
  normalizeStatus,
  statusLabel,
  statusTone,
} from './liveChatTypes';
import { useLiveChatThread } from './useLiveChatThread';

type Props = {
  chat: LiveChatItem;
  onBack: () => void;
  onChatUpdated: () => void;
};

export function LiveChatThread({ chat, onBack, onChatUpdated }: Props) {
  const thread = useLiveChatThread(chat, onChatUpdated);
  const status = normalizeStatus({ ...chat, status: thread.localStatus });
  const canMutate = !thread.social;
  const isHuman = status === 'human' || status === 'waiting_human';

  const readOnlyReason = thread.social
    ? 'Instagram/Facebook conversations are read-only. Use WhatsApp for operator replies.'
    : status === 'bot' || status === 'closed'
      ? 'Take over this conversation to reply as a human.'
      : null;

  return (
    <View style={styles.flex}>
      <View style={styles.header}>
        <Pressable onPress={onBack}>
          <Text style={styles.back}>← Inbox</Text>
        </Pressable>
        <Text style={styles.title} numberOfLines={1}>
          {chatTitle(chat)}
        </Text>
        <View style={styles.chips}>
          <StatusChip label={statusLabel(status)} tone={statusTone(status)} />
          <StatusChip label={channelLabel(chat)} tone="neutral" />
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
          data={thread.messages}
          keyExtractor={(m, i) => m.message_id || `${m.timestamp}-${i}`}
          contentContainerStyle={styles.messages}
          ListEmptyComponent={
            <EmptyState title="No messages yet" body="This conversation has no messages in the loaded window." />
          }
          ListHeaderComponent={
            thread.hasMore ? (
              <Pressable style={styles.loadMore} onPress={() => void thread.loadOlder()} disabled={thread.loadingMore}>
                <Text style={styles.loadMoreText}>
                  {thread.loadingMore ? 'Loading…' : 'Load older messages'}
                </Text>
              </Pressable>
            ) : null
          }
          renderItem={({ item }) => <LiveChatMessageBubble message={item} />}
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
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: { gap: 8, marginBottom: spacing.md },
  back: { color: colors.accent, fontFamily: fonts.bodyMedium, marginBottom: 2 },
  title: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 18 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
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
  messages: { paddingBottom: spacing.md, flexGrow: 1 },
  loadMore: { alignItems: 'center', paddingVertical: spacing.sm },
  loadMoreText: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 13 },
  error: { color: colors.danger, fontFamily: fonts.body, fontSize: 13, marginBottom: spacing.sm },
});
