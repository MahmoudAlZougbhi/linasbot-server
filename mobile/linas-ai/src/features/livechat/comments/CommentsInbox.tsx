import { useCallback, useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { EmptyState } from '../../../components/EmptyState';
import { LinasLoadingIndicator } from '../../../components/LinasLoadingIndicator';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, useTheme } from '../../../theme';
import { CommentPostSheet } from './CommentPostSheet';
import { CommentsMediaGrid } from './CommentsMediaGrid';
import { CommentsPlatformChips } from './CommentsPlatformChips';
import { fetchCommentMedia, patchCommentWatch } from './commentsInboxApi';
import type { CommentMediaItem, CommentPlatform, CommentWatch } from './commentsInboxTypes';

type Props = {
  onOpenThread: (platform: CommentPlatform, post: CommentMediaItem) => void;
};

export function CommentsInbox({ onOpenThread }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const [platform, setPlatform] = useState<CommentPlatform>('instagram');
  const [posts, setPosts] = useState<CommentMediaItem[]>([]);
  const [nextAfter, setNextAfter] = useState('');
  const [watch, setWatch] = useState<CommentWatch>({ mode: 'all', post_ids: [] });
  const [accountName, setAccountName] = useState('');
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState<CommentMediaItem | null>(null);

  const load = useCallback(
    async (after = '', append = false) => {
      if (!append) setError('');
      try {
        const result = await fetchCommentMedia({ platform, after });
        setPosts((current) => (append ? [...current, ...result.posts] : result.posts));
        setNextAfter(result.nextAfter);
        setWatch(result.watch);
        setAccountName(result.accountName);
        setStatus(result.status);
        if (result.error) setError(result.error);
      } catch {
        setStatus('error');
        setError(tr('liveCommentsError'));
        if (!append) setPosts([]);
      }
    },
    [platform, tr],
  );

  useEffect(() => {
    setStatus('loading');
    setPosts([]);
    setSelected(null);
    void load();
  }, [load]);

  async function refresh() {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  }

  async function setMode(mode: CommentWatch['mode']) {
    const next = await patchCommentWatch({ platform, mode });
    setWatch(next);
    setPosts((current) => current.map((row) => ({ ...row, watched: mode === 'all' ? true : next.post_ids.includes(row.id) })));
  }

  async function toggleWatch(post: CommentMediaItem) {
    const next = await patchCommentWatch({
      platform,
      postId: post.id,
      selected: !post.watched,
      knownIds: posts.map((row) => row.id),
    });
    setWatch(next);
    setPosts((current) =>
      current.map((row) => ({
        ...row,
        watched: next.mode !== 'selected' || next.post_ids.includes(row.id),
      })),
    );
    setSelected((current) =>
      current && current.id === post.id
        ? { ...current, watched: next.mode !== 'selected' || next.post_ids.includes(post.id) }
        : current,
    );
  }

  const kindLabel = (kind: CommentMediaItem['kind']) =>
    kind === 'reel' ? tr('liveCommentsReel') : kind === 'video' ? tr('liveCommentsVideo') : tr('liveCommentsPost');

  const emptyTitle =
    status === 'disconnected'
      ? tr('liveCommentsDisconnected')
      : status === 'error'
        ? tr('liveCommentsError')
        : tr('liveCommentsEmpty');

  return (
    <View style={styles.flex}>
      <CommentsMediaGrid
        posts={posts}
        refreshing={refreshing}
        onRefresh={() => void refresh()}
        onEndReached={() => {
          if (nextAfter) void load(nextAfter, true);
        }}
        kindLabel={kindLabel}
        onOpen={setSelected}
        onToggleWatch={(post) => void toggleWatch(post)}
        header={
          <View>
            <CommentsPlatformChips selected={platform} onSelect={setPlatform} />
            <Text style={[styles.hint, { color: colors.textMuted }]}>{tr('liveCommentsSelectHint')}</Text>
            <View style={styles.modes}>
              {(['all', 'selected'] as const).map((mode) => {
                const on = watch.mode === mode;
                return (
                  <Pressable
                    key={mode}
                    onPress={() => void setMode(mode)}
                    style={[
                      styles.mode,
                      {
                        backgroundColor: on ? colors.accentSoft : colors.surface,
                        borderColor: on ? colors.accent : colors.border,
                      },
                    ]}
                  >
                    <Text style={[styles.modeText, { color: on ? colors.text : colors.textMuted }]}>
                      {mode === 'all' ? tr('liveCommentsAllPosts') : tr('liveCommentsChosenPosts')}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            {accountName ? <Text style={[styles.account, { color: colors.text }]}>{accountName}</Text> : null}
            {error && status !== 'disconnected' ? <Text style={[styles.error, { color: colors.danger }]}>{error}</Text> : null}
            {status === 'loading' && posts.length === 0 ? <LinasLoadingIndicator variant="inline" /> : null}
          </View>
        }
        empty={status === 'loading' ? null : <EmptyState title={emptyTitle} body={tr('liveCommentsEmptyBody')} />}
      />
      <CommentPostSheet
        post={selected}
        accountName={accountName}
        onClose={() => setSelected(null)}
        onView={() => {
          if (selected?.permalink) void Linking.openURL(selected.permalink);
        }}
        onOpenThread={() => {
          if (!selected) return;
          const post = selected;
          setSelected(null);
          onOpenThread(platform, post);
        }}
        onToggleWatch={() => {
          if (selected) void toggleWatch(selected);
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, minHeight: 0 },
  hint: { fontFamily: fonts.body, fontSize: 13, marginBottom: 8 },
  modes: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  mode: {
    flex: 1,
    minHeight: 40,
    borderWidth: 1.5,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  modeText: { fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '700' },
  account: { fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700', marginBottom: 8 },
  error: { fontFamily: fonts.body, fontSize: 13, marginBottom: 8 },
});
