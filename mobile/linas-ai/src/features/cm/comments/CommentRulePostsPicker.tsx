import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { EmptyState } from '../../../components/EmptyState';
import { ScreenSkeleton } from '../../../components/ScreenSkeleton';
import type { StringKey } from '../../../i18n';
import { fonts, useTheme } from '../../../theme';
import { CommentsMediaGrid } from '../../livechat/comments/CommentsMediaGrid';
import { CommentsPlatformChips } from '../../livechat/comments/CommentsPlatformChips';
import { fetchCommentMedia } from '../../livechat/comments/commentsInboxApi';
import type { CommentMediaItem, CommentPlatform } from '../../livechat/comments/commentsInboxTypes';
import type { SelectedCommentPost } from './commentPostSnapshots';

type Props = {
  selected: SelectedCommentPost[];
  onChange: (posts: SelectedCommentPost[]) => void;
  tr: (key: StringKey) => string;
};

function firstPlatform(posts: SelectedCommentPost[]): CommentPlatform {
  const raw = posts[0]?.platform;
  if (raw === 'facebook' || raw === 'tiktok' || raw === 'instagram') return raw;
  return 'instagram';
}

export function CommentRulePostsPicker({ selected, onChange, tr }: Props) {
  const { colors } = useTheme();
  const [platform, setPlatform] = useState<CommentPlatform>(() => firstPlatform(selected));
  const [posts, setPosts] = useState<CommentMediaItem[]>([]);
  const [nextAfter, setNextAfter] = useState('');
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');

  const load = useCallback(
    async (after = '', append = false) => {
      if (!append) setError('');
      try {
        const result = await fetchCommentMedia({ platform, after });
        setPosts((current) => (append ? [...current, ...result.posts] : result.posts));
        setNextAfter(result.nextAfter);
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

  function toggle(post: CommentMediaItem) {
    const key = `${platform}:${post.id}`;
    if (selected.some((row) => `${row.platform}:${row.id}` === key)) {
      onChange(selected.filter((row) => `${row.platform}:${row.id}` !== key));
      return;
    }
    onChange([
      ...selected,
      {
        id: post.id,
        platform,
        thumbnail: post.thumbnail,
        caption: post.caption,
        permalink: post.permalink,
        kind: post.kind,
      },
    ]);
  }

  const kindLabel = (kind: CommentMediaItem['kind']) =>
    kind === 'reel' ? tr('liveCommentsReel') : kind === 'video' ? tr('liveCommentsVideo') : tr('liveCommentsPost');
  const emptyTitle =
    status === 'disconnected'
      ? tr('liveCommentsDisconnected')
      : status === 'error'
        ? tr('liveCommentsError')
        : tr('liveCommentsEmpty');
  const pickIds = selected.filter((row) => row.platform === platform).map((row) => row.id);

  return (
    <View style={styles.flex}>
      <CommentsMediaGrid
        posts={posts}
        kindLabel={kindLabel}
        pickIds={pickIds}
        onPick={toggle}
        onEndReached={() => {
          if (nextAfter) void load(nextAfter, true);
        }}
        header={
          <View>
            <CommentsPlatformChips selected={platform} onSelect={setPlatform} />
            <Text style={[styles.hint, { color: colors.textMuted }]}>{tr('commentsPickerHint')}</Text>
            {error && status !== 'disconnected' ? (
              <Text style={[styles.error, { color: colors.danger }]}>{error}</Text>
            ) : null}
            {status === 'loading' && posts.length === 0 ? <ScreenSkeleton variant="cards" rows={4} /> : null}
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
  error: { fontFamily: fonts.body, fontSize: 13, marginBottom: 8 },
});
