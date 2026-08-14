import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { colors, fonts, spacing, useTheme } from '../../theme';
import { ConversationRow } from './ConversationRow';
import { InboxChannelChips } from './InboxChannelChips';
import { InboxFilterPills } from './InboxFilterPills';
import { InboxSearchBar } from './InboxSearchBar';
import type { LiveChatItem } from './liveChatTypes';
import { useLiveChatInbox } from './useLiveChatInbox';

type Props = {
  onOpenChat: (chat: LiveChatItem) => void;
  inbox: ReturnType<typeof useLiveChatInbox>;
};

export function LiveChatInbox({ onOpenChat, inbox }: Props) {
  const { colors: theme } = useTheme();
  const {
    chats,
    loading,
    refreshing,
    loadingMore,
    error,
    errorKind,
    search,
    setSearch,
    filter,
    setFilter,
    channel,
    setChannel,
    hasMore,
    refresh,
    loadMore,
  } = inbox;

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  if (errorKind === 'forbidden') {
    return (
      <EmptyState
        title="Live Chat permission required"
        body="Your account needs Live Chat access. Ask a workspace owner to grant permission."
      />
    );
  }

  if (errorKind === 'auth') {
    return (
      <EmptyState title="Session expired" body="Sign in again to open the operator inbox." />
    );
  }

  return (
    <View style={styles.flex}>
      <InboxSearchBar value={search} onChange={setSearch} />
      <InboxChannelChips selected={channel} onSelect={setChannel} />
      <InboxFilterPills selected={filter} onSelect={setFilter} />
      {error ? <Text style={[styles.error, { color: theme.danger }]}>{error}</Text> : null}
      <FlatList
        style={styles.flex}
        data={chats}
        keyExtractor={(item) => item.conversation_id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
        contentContainerStyle={styles.list}
        onEndReached={() => {
          if (hasMore) loadMore();
        }}
        onEndReachedThreshold={0.4}
        ListEmptyComponent={
          <EmptyState
            title={channel === 'tiktok' ? 'No TikTok conversations' : 'No conversations yet'}
            body={
              channel === 'tiktok'
                ? 'TikTok threads appear here when TikTok is connected. None are created as placeholders.'
                : 'When customers message on WhatsApp, Instagram, or Messenger, they appear here. Pull to refresh.'
            }
          />
        }
        ListFooterComponent={
          loadingMore ? (
            <ActivityIndicator color={colors.accent} style={styles.footer} />
          ) : null
        }
        renderItem={({ item }) => (
          <ConversationRow item={item} onPress={() => onOpenChat(item)} />
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  list: { paddingBottom: 40, flexGrow: 1 },
  footer: { marginVertical: 12 },
  error: { fontFamily: fonts.body, marginBottom: spacing.sm, fontSize: 13 },
});
