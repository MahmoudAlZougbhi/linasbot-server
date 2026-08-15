import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { fonts, spacing, useTheme } from '../../theme';
import { ConversationRow } from './ConversationRow';
import { InboxChannelChips } from './InboxChannelChips';
import { InboxFilterPills } from './InboxFilterPills';
import { InboxSearchBar } from './InboxSearchBar';
import type { LiveChatItem } from './liveChatTypes';
import { matchesChannelFilter } from './liveChatTypes';
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
    hasLoadedOnce,
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
    indexRebuild,
  } = inbox;

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

  if (!hasLoadedOnce && loading) {
    return (
      <View style={styles.flex}>
        <LinasLoadingIndicator variant="screen" />
      </View>
    );
  }

  const visibleChats = chats.filter((item) => matchesChannelFilter(item, channel));
  const emptyTitle =
    channel === 'tiktok'
      ? 'No TikTok conversations'
      : indexRebuild
        ? 'Inbox index is empty'
        : 'No conversations yet';
  const emptyBody =
    channel === 'tiktok'
      ? 'TikTok threads appear here when TikTok is connected. None are created as placeholders.'
      : indexRebuild
        ? 'Customer threads appear after the live chat index is rebuilt. Pull to refresh. This screen does not invent conversations.'
        : 'When customers message on WhatsApp, Instagram, or Messenger, they appear here. Pull to refresh.';

  return (
    <View style={styles.flex}>
      <View style={styles.toolbar}>
        <InboxSearchBar value={search} onChange={setSearch} />
        <InboxChannelChips selected={channel} onSelect={setChannel} />
        <InboxFilterPills selected={filter} onSelect={setFilter} />
        {error ? <Text style={[styles.error, { color: theme.danger }]}>{error}</Text> : null}
      </View>
      <View style={styles.listWrap}>
        <FlatList
          style={styles.flex}
          data={visibleChats}
          keyExtractor={(item) => item.conversation_id}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
          contentContainerStyle={visibleChats.length ? styles.listPad : styles.listEmpty}
          onEndReached={() => {
            if (hasMore) loadMore();
          }}
          onEndReachedThreshold={0.4}
          ListEmptyComponent={
            <EmptyState title={emptyTitle} body={emptyBody} />
          }
          ListFooterComponent={
            loadingMore ? (
              <LinasLoadingIndicator variant="inline" style={styles.footer} />
            ) : null
          }
          renderItem={({ item }) => (
            <ConversationRow item={item} onPress={() => onOpenChat(item)} />
          )}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, minHeight: 0 },
  toolbar: { flexGrow: 0, flexShrink: 0 },
  listWrap: { flex: 1, minHeight: 0 },
  center: { paddingVertical: 48, alignItems: 'center', justifyContent: 'center' },
  listPad: { paddingBottom: 40 },
  listEmpty: { paddingBottom: 40, flexGrow: 1 },
  footer: { marginVertical: 12 },
  error: { fontFamily: fonts.body, marginBottom: spacing.sm, fontSize: 13 },
});
