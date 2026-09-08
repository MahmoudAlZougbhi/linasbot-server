import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { EmptyState } from '../../../components/EmptyState';
import { LinasLoadingIndicator } from '../../../components/LinasLoadingIndicator';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, useTheme } from '../../../theme';
import { CommentsMediaGrid } from './CommentsMediaGrid';
import { CommentsPlatformChips } from './CommentsPlatformChips';
import { fetchCommentMedia } from './commentsInboxApi';
import type { CommentMediaItem, CommentPlatform } from './commentsInboxTypes';

type Props = {
  onOpenThread: (platform: CommentPlatform, post: CommentMediaItem) => void;
};

export function CommentsInbox({ onOpenThread }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const [platform, setPlatform] = useState<CommentPlatform>('instagram');
  const [posts, setPosts] = useState<CommentMediaItem[]>([]);
  const [nextAfter, setNextAfter] = useState('');
  const [accountName, setAccountName] = useState('');
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async (after = '', append = false) => {
      if (!append) setError('');
      try {
        const result = await fetchCommentMedia({ platform, after });
        setPosts((current) => (append ? [...current, ...result.posts] : result.posts));
        setNextAfter(result.nextAfter);
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
            <CommentsPlatformChips selected={platform} onSelect={setPlatform} />
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
