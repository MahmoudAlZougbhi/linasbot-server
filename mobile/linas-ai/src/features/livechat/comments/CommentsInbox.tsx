import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { LiveChatSseEvent } from '../liveChatSseParse';

import { cacheGet, cacheSet, isCacheFresh } from '../../../cache/queryCache';
import { queryKeys } from '../../../cache/queryKeys';
import { QUERY_TTL } from '../../../cache/queryTtl';
import { EmptyState } from '../../../components/EmptyState';
import { LinasLoadingIndicator } from '../../../components/LinasLoadingIndicator';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, useTheme } from '../../../theme';
import { CommentsMediaGrid } from './CommentsMediaGrid';
import { allowedCommentPlatforms, CommentsPlatformChips } from './CommentsPlatformChips';
import { fetchCommentMedia } from './commentsInboxApi';
import { applyCommentGridEvent } from './commentsSseMerge';
import type { CommentMediaItem, CommentPlatform } from './commentsInboxTypes';

type Props = {
  onOpenThread: (platform: CommentPlatform, post: CommentMediaItem) => void;
  allowedChannels?: string[] | null;
  realtimeEvent?: { seq: number; event: LiveChatSseEvent } | null;
};

type CommentsSnapshot = {
  posts: CommentMediaItem[];
  nextAfter: string;
  accountName: string;
  status: string;
  error: string;
};

export function CommentsInbox({ onOpenThread, allowedChannels = null, realtimeEvent = null }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const allowedKey = allowedChannels ? allowedChannels.join(',') : '*';
  const [platform, setPlatform] = useState<CommentPlatform>(
    () => allowedCommentPlatforms(allowedChannels)[0] || 'instagram',
  );
  const seeded = cacheGet<CommentsSnapshot>(queryKeys.commentsInbox(platform));
  const [posts, setPosts] = useState<CommentMediaItem[]>(seeded?.data.posts ?? []);
  const [nextAfter, setNextAfter] = useState(seeded?.data.nextAfter ?? '');
  const [accountName, setAccountName] = useState(seeded?.data.accountName ?? '');
  const [status, setStatus] = useState(seeded?.data.status ?? 'loading');
  const [error, setError] = useState(seeded?.data.error ?? '');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async (after = '', append = false, force = false) => {
      const key = queryKeys.commentsInbox(platform);
      const hit = cacheGet<CommentsSnapshot>(key);
      if (hit && !append) {
        setPosts(hit.data.posts);
        setNextAfter(hit.data.nextAfter);
        setAccountName(hit.data.accountName);
        setStatus(hit.data.status);
        setError(hit.data.error);
      }
      if (!append && !after && !force && hit && isCacheFresh(key, QUERY_TTL.commentsInbox)) return;
      if (!append && !hit) setStatus('loading');
      if (!append) setError('');
      try {
        const result = await fetchCommentMedia({ platform, after });
        setPosts((current) => {
          const rows = append ? [...current, ...result.posts] : result.posts;
          if (!append) {
            cacheSet(key, {
              posts: rows,
              nextAfter: result.nextAfter,
              accountName: result.accountName,
              status: result.status,
              error: result.error,
            });
          }
          return rows;
        });
        setNextAfter(result.nextAfter);
        setAccountName(result.accountName);
        setStatus(result.status);
        if (result.error) setError(result.error);
      } catch {
        setStatus(hit?.data.posts.length ? hit.data.status : 'error');
        setError(tr('liveCommentsError'));
        if (!append && !hit) setPosts([]);
      }
    },
    [platform, tr],
  );

  useEffect(() => {
    const next = allowedCommentPlatforms(allowedChannels);
    if (next.length && !next.includes(platform)) {
      setPlatform(next[0]);
    }
  }, [allowedKey, allowedChannels, platform]);

  useEffect(() => {
    const next = allowedCommentPlatforms(allowedChannels);
    if (!next.length) {
      setStatus('empty');
      setPosts([]);
      return;
    }
    void load();
  }, [load, allowedKey, allowedChannels]);

  useEffect(() => {
    if (!realtimeEvent || realtimeEvent.event.type !== 'comment_update') return;
    setPosts((current) => {
      const rows = applyCommentGridEvent(current, realtimeEvent.event.data, platform);
      cacheSet(queryKeys.commentsInbox(platform), {
        posts: rows,
        nextAfter,
        accountName,
        status,
        error,
      });
      return rows;
    });
    // Apply each pushed event once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [realtimeEvent?.seq, platform]);

  async function refresh() {
    setRefreshing(true);
    try {
      await load('', false, true);
    } finally {
      setRefreshing(false);
    }
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
        onOpen={(post) => onOpenThread(platform, post)}
        header={
          <View>
            <CommentsPlatformChips selected={platform} onSelect={setPlatform} allowed={allowedChannels} />
            <Text style={[styles.hint, { color: colors.textMuted }]}>{tr('liveCommentsSelectHint')}</Text>
            {accountName ? <Text style={[styles.account, { color: colors.text }]}>{accountName}</Text> : null}
            {error && status !== 'disconnected' ? <Text style={[styles.error, { color: colors.danger }]}>{error}</Text> : null}
            {status === 'loading' && posts.length === 0 ? <LinasLoadingIndicator variant="inline" /> : null}
          </View>
        }
        empty={status === 'loading' ? null : <EmptyState title={emptyTitle} body={tr('liveCommentsEmptyBody')} />}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, minHeight: 0 },
  hint: { fontFamily: fonts.body, fontSize: 13, marginBottom: 8 },
  account: { fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700', marginBottom: 8 },
  error: { fontFamily: fonts.body, fontSize: 13, marginBottom: 8 },
});
