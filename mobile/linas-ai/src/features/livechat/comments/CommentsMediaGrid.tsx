import type { ReactElement } from 'react';
import { FlatList, Image, Pressable, RefreshControl, StyleSheet, Text, useWindowDimensions, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { fonts, useTheme } from '../../../theme';
import type { CommentMediaItem } from './commentsInboxTypes';

type Props = {
  posts: CommentMediaItem[];
  onOpen?: (post: CommentMediaItem) => void;
  pickIds?: string[];
  onPick?: (post: CommentMediaItem) => void;
  kindLabel: (kind: CommentMediaItem['kind']) => string;
  refreshing?: boolean;
  onRefresh?: () => void;
  onEndReached?: () => void;
  header?: ReactElement | null;
  empty?: ReactElement | null;
};

function Tile({
  post,
  onOpen,
  onPick,
  picked,
  kindLabel,
  tileWidth,
}: {
  post: CommentMediaItem;
  onOpen?: () => void;
  onPick?: () => void;
  picked: boolean;
  kindLabel: string;
  tileWidth: number;
}) {
  const { colors } = useTheme();
  const picking = Boolean(onPick);
  return (
    <View style={[styles.tile, { width: tileWidth }]}>
      <Pressable
        onPress={onPick || onOpen}
        accessibilityRole="button"
        accessibilityLabel={kindLabel}
        style={styles.press}
      >
        {post.thumbnail ? (
          <Image source={{ uri: post.thumbnail }} style={styles.image} />
        ) : (
          <View style={[styles.image, styles.fallback, { backgroundColor: colors.surfaceAlt }]}>
            <AppIcon icon={feather('image')} size={22} color={colors.textMuted} />
          </View>
        )}
        <View style={styles.kind}>
          <Text style={styles.kindText}>{kindLabel}</Text>
        </View>
        <View style={styles.count}>
          <AppIcon icon={feather('message-circle')} size={12} color="#FFFFFF" />
          <Text style={styles.countText}>{post.comment_count}</Text>
        </View>
        {picking ? (
          <View style={[styles.check, picked ? styles.checkOn : styles.checkOff]}>
            <AppIcon icon={feather(picked ? 'check' : 'plus')} size={14} color={picked ? '#FFFFFF' : '#111827'} />
          </View>
        ) : null}
      </Pressable>
    </View>
  );
}

export function CommentsMediaGrid({
  posts,
  onOpen,
  pickIds,
  onPick,
  kindLabel,
  refreshing = false,
  onRefresh,
  onEndReached,
  header,
  empty,
}: Props) {
  const { width } = useWindowDimensions();
  const tileWidth = Math.floor((width - GAP * 2) / 3);
  return (
    <FlatList
      data={posts}
      numColumns={3}
      keyExtractor={(item) => item.id}
      columnWrapperStyle={posts.length ? styles.row : undefined}
      contentContainerStyle={posts.length ? styles.list : styles.empty}
      refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} /> : undefined}
      onEndReached={onEndReached}
      onEndReachedThreshold={0.4}
      ListHeaderComponent={header}
      ListEmptyComponent={empty}
      renderItem={({ item }) => (
        <Tile
          post={item}
          tileWidth={tileWidth}
          kindLabel={kindLabel(item.kind)}
          picked={Boolean(pickIds?.includes(item.id))}
          onOpen={onOpen ? () => onOpen(item) : undefined}
          onPick={onPick ? () => onPick(item) : undefined}
        />
      )}
    />
  );
}

const GAP = 3;

const styles = StyleSheet.create({
  list: { paddingBottom: 28 },
  empty: { flexGrow: 1 },
  row: { gap: GAP, marginBottom: GAP },
  tile: { aspectRatio: 1, position: 'relative' },
  press: { flex: 1, overflow: 'hidden', backgroundColor: '#111827' },
  image: { width: '100%', height: '100%' },
  fallback: { alignItems: 'center', justifyContent: 'center' },
  kind: {
    position: 'absolute',
    top: 6,
    left: 6,
    backgroundColor: 'rgba(0,0,0,0.55)',
    borderRadius: 8,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  kindText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 10, fontWeight: '700' },
  count: {
    position: 'absolute',
    bottom: 6,
    left: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  countText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 12, fontWeight: '700' },
  check: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkOn: { backgroundColor: '#0D9488' },
  checkOff: { backgroundColor: 'rgba(255,255,255,0.88)' },
});
