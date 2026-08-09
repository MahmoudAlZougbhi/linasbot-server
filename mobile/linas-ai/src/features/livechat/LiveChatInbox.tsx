import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { TextField } from '../../components/TextField';
import { colors, fonts, radii, spacing } from '../../theme';
import { ConversationRow } from './ConversationRow';
import type { InboxFilter, LiveChatItem } from './liveChatTypes';
import { useLiveChatInbox } from './useLiveChatInbox';

const FILTERS: { id: InboxFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'waiting', label: 'Waiting' },
  { id: 'with_operator', label: 'Human' },
  { id: 'bot', label: 'AI' },
  { id: 'closed', label: 'Closed' },
];

type Props = {
  onOpenChat: (chat: LiveChatItem) => void;
  inbox: ReturnType<typeof useLiveChatInbox>;
};

export function LiveChatInbox({ onOpenChat, inbox }: Props) {
  const {
    sections,
    loading,
    refreshing,
    loadingMore,
    error,
    errorKind,
    search,
    setSearch,
    filter,
    setFilter,
    hasMore,
    total,
    refresh,
    loadMore,
  } = inbox;

  const flatData = sections.flatMap((section) => {
    const rows: Array<{ kind: 'header'; title: string } | { kind: 'chat'; item: LiveChatItem }> = [];
    if (section.title) rows.push({ kind: 'header', title: section.title });
    for (const item of section.data) rows.push({ kind: 'chat', item });
    return rows;
  });

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
        body="Your account needs the liveChat permission (operator/admin). Ask an owner to grant access."
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
      <TextField
        value={search}
        onChangeText={setSearch}
        placeholder="Search name or phone…"
        autoCapitalize="none"
        autoCorrect={false}
        style={styles.search}
      />
      <View style={styles.filters}>
        {FILTERS.map((f) => {
          const active = filter === f.id;
          return (
            <Pressable
              key={f.id}
              style={[styles.chip, active && styles.chipActive]}
              onPress={() => setFilter(f.id)}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>{f.label}</Text>
            </Pressable>
          );
        })}
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Text style={styles.count}>{total} conversation{total === 1 ? '' : 's'}</Text>
      <FlatList
        data={flatData}
        keyExtractor={(row, index) =>
          row.kind === 'header' ? `h-${row.title}-${index}` : row.item.conversation_id
        }
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
        contentContainerStyle={styles.list}
        onEndReached={() => {
          if (hasMore) loadMore();
        }}
        onEndReachedThreshold={0.4}
        ListEmptyComponent={
          <EmptyState
            title="No conversations yet"
            body="When customers message on WhatsApp (or social), they appear here. Pull to refresh."
          />
        }
        ListFooterComponent={
          loadingMore ? <ActivityIndicator color={colors.accent} style={{ marginVertical: 12 }} /> : null
        }
        renderItem={({ item: row }) => {
          if (row.kind === 'header') {
            return <Text style={styles.section}>{row.title}</Text>;
          }
          return <ConversationRow item={row.item} onPress={() => onOpenChat(row.item)} />;
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  search: { marginBottom: spacing.sm },
  filters: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: spacing.sm },
  chip: {
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  chipActive: { backgroundColor: colors.accentSoft, borderColor: colors.accent },
  chipText: { color: colors.textMuted, fontFamily: fonts.bodyMedium, fontSize: 12 },
  chipTextActive: { color: colors.accent },
  count: { color: colors.textDim, fontFamily: fonts.body, fontSize: 12, marginBottom: spacing.sm },
  list: { gap: spacing.sm, paddingBottom: 40 },
  section: {
    color: colors.textMuted,
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    marginTop: spacing.sm,
    marginBottom: 2,
  },
  error: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm, fontSize: 13 },
});
