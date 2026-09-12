import { useEffect } from 'react';
import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { ScreenSkeleton } from '../../components/ScreenSkeleton';
import { fonts, spacing, useTheme } from '../../theme';
import { ConversationRow } from './ConversationRow';
import { InboxChannelChips } from './InboxChannelChips';
import { InboxSearchBar } from './InboxSearchBar';
import type { AccessChannelId } from '../users/usersAccess';
import type { LiveChatItem } from './liveChatTypes';
import { matchesAllowedChannels, matchesChannelFilter } from './liveChatTypes';
import { useLiveChatInbox } from './useLiveChatInbox';

type Props = {
  onOpenChat: (chat: LiveChatItem) => void;
  inbox: ReturnType<typeof useLiveChatInbox>;
  allowedChannels?: AccessChannelId[] | null;
};

export function LiveChatInbox({ onOpenChat, inbox, allowedChannels = null }: Props) {
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
    channel,
    setChannel,
    hasMore,
    refresh,
    loadMore,
    indexRebuild,
  } = inbox;

  useEffect(() => {
    if (!allowedChannels) return;
    if (channel !== 'all' && !allowedChannels.includes(channel)) {
      setChannel(allowedChannels[0] ?? 'all');
    }
  }, [allowedChannels, channel, setChannel]);

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

  const cold = !hasLoadedOnce && loading && chats.length === 0;

  const visibleChats = chats
    .filter((item) => matchesAllowedChannels(item, allowedChannels))
    .filter((item) => matchesChannelFilter(item, channel));
  const emptyTitle =
    filter === 'waiting'
      ? 'No one waiting for a human'
      : channel === 'tiktok'
        ? 'No TikTok conversations'
        : indexRebuild
          ? 'Inbox index is empty'
          : 'No conversations yet';
  const emptyBody =
    filter === 'waiting'
      ? 'Customers who ask for a human appear here. Tap the person icon again to see every chat.'
      : channel === 'tiktok'
        ? 'TikTok threads appear here when TikTok is connected. None are created as placeholders.'
        : indexRebuild
          ? 'Customer threads appear after the live chat index is rebuilt. Pull to refresh. This screen does not invent conversations.'
          : 'When customers message on WhatsApp, Instagram, or Messenger, they appear here. Pull to refresh.';

  return (
    <View style={styles.flex}>
      <View style={styles.toolbar}>
        <InboxSearchBar value={search} onChange={setSearch} />
        <InboxChannelChips selected={channel} onSelect={setChannel} allowed={allowedChannels} />
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
            cold ? (
              <ScreenSkeleton variant="inbox" />
            ) : (
              <EmptyState title={emptyTitle} body={emptyBody} />
            )
          }
          ListFooterComponent={
            loadingMore ? (
              <LinasLoadingIndicator variant="inline" style={styles.footer} />
            ) : null
          }
          renderItem={({ item, index }) => (
            <ConversationRow
              item={item}
              onPress={() => onOpenChat(item)}
              showDivider={index < visibleChats.length - 1}
            />
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
