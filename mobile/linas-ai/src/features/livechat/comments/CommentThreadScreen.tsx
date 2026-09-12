import { useEffect, useState } from 'react';
import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { EmptyState } from '../../../components/EmptyState';
import { LinasLoadingIndicator } from '../../../components/LinasLoadingIndicator';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { LiveChatSseEvent } from '../liveChatSseParse';
import { fetchCommentThreads } from './commentsInboxApi';
import { applyCommentThreadEvent } from './commentsSseMerge';
import type { CommentMediaItem, CommentPlatform, CommentThreadItem } from './commentsInboxTypes';

type Props = {
  platform: CommentPlatform;
  post: CommentMediaItem;
  realtimeEvent?: { seq: number; event: LiveChatSseEvent } | null;
  sseConnectedAt?: number;
};

function PostHero({ post }: { post: CommentMediaItem }) {
  const { colors } = useTheme();
  const tall = post.kind === 'reel' || post.kind === 'video';
  const size = { aspectRatio: tall ? 4 / 5 : 1 };
  if (!post.thumbnail) {
    return (
      <View style={[styles.hero, size, styles.heroFallback, { backgroundColor: colors.surfaceAlt }]}>
        <AppIcon icon={feather('image')} size={36} color={colors.textMuted} />
      </View>
    );
  }
  return <Image source={{ uri: post.thumbnail }} style={[styles.hero, size]} accessibilityIgnoresInvertColors />;
}

export function CommentThreadScreen({
  platform,
  post,
  realtimeEvent = null,
  sseConnectedAt = 0,
}: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [items, setItems] = useState<CommentThreadItem[]>([]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError('');
    void fetchCommentThreads({ platform, postId: post.id })
      .then((result) => {
        if (!alive) return;
        setItems(result.items);
        setError(result.error);
      })
      .catch(() => {
        if (!alive) return;
        setItems([]);
        setError(tr('liveCommentsThreadError'));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [platform, post.id, tr, sseConnectedAt]);

  useEffect(() => {
    if (!realtimeEvent || realtimeEvent.event.type !== 'comment_update') return;
    setItems((current) => applyCommentThreadEvent(current, realtimeEvent.event.data, post.id, platform));
    // Apply each pushed event once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [realtimeEvent?.seq]);

  return (
    <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
      <PostHero post={post} />
      {loading ? <LinasLoadingIndicator variant="inline" /> : null}
      {!loading && error && !items.length ? (
        <EmptyState title={tr('liveCommentsThreadError')} body={tr('liveCommentsThreadErrorBody')} />
      ) : null}
      {!loading && !error && !items.length ? (
        <EmptyState title={tr('liveCommentsNoComments')} body={tr('liveCommentsNoCommentsBody')} />
      ) : null}
      {items.map((item) => (
        <View key={item.comment_id || item.comment} style={styles.block}>
          <View style={[styles.bubble, styles.customer, { backgroundColor: colors.surfaceAlt }]}>
            <Text style={[styles.who, { color: colors.textMuted }]}>{item.author || tr('liveCommentsCustomer')}</Text>
            <Text style={[styles.body, { color: colors.text }]}>{item.comment}</Text>
          </View>
          {item.ai_reply ? (
            <View style={[styles.bubble, styles.ai, { backgroundColor: colors.accentSoft }]}>
              <Text style={[styles.who, { color: colors.accent }]}>{tr('liveCommentsAiReply')}</Text>
              <Text style={[styles.body, { color: colors.text }]}>{item.ai_reply}</Text>
            </View>
          ) : (
            <Text style={[styles.wait, { color: colors.textMuted }]}>{tr('liveCommentsWaitingReply')}</Text>
          )}
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 32, gap: 16 },
  hero: {
    alignSelf: 'stretch',
    marginHorizontal: -spacing.lg,
    backgroundColor: '#111827',
  },
  heroFallback: { alignItems: 'center', justifyContent: 'center' },
  block: { gap: 8 },
  bubble: { borderRadius: radii.lg, padding: spacing.md, gap: 4 },
  customer: { marginRight: 36 },
  ai: { marginLeft: 36 },
  who: { fontFamily: fonts.bodyMedium, fontSize: 12, fontWeight: '700' },
  body: { fontFamily: fonts.body, fontSize: 15, lineHeight: 21 },
  wait: { fontFamily: fonts.body, fontSize: 13, marginLeft: 36 },
});
