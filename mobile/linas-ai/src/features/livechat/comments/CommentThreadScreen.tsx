import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { EmptyState } from '../../../components/EmptyState';
import { LinasLoadingIndicator } from '../../../components/LinasLoadingIndicator';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import { fetchCommentThreads } from './commentsInboxApi';
import type { CommentMediaItem, CommentPlatform, CommentThreadItem } from './commentsInboxTypes';

type Props = {
  platform: CommentPlatform;
  post: CommentMediaItem;
};

export function CommentThreadScreen({ platform, post }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<CommentThreadItem[]>([]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void fetchCommentThreads({ platform, postId: post.id })
      .then((rows) => {
        if (alive) setItems(rows);
      })
      .catch(() => {
        if (alive) setItems([]);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [platform, post.id]);

  if (loading) return <LinasLoadingIndicator variant="screen" />;
  if (!items.length) {
    return <EmptyState title={tr('liveCommentsNoReplies')} body={tr('liveCommentsNoRepliesBody')} />;
  }

  return (
    <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
      {items.map((item) => (
        <View key={item.comment_id || item.comment} style={styles.block}>
          <View style={[styles.bubble, styles.customer, { backgroundColor: colors.surfaceAlt }]}>
            <Text style={[styles.who, { color: colors.textMuted }]}>{item.author || tr('liveCommentsCustomer')}</Text>
            <Text style={[styles.body, { color: colors.text }]}>{item.comment}</Text>
          </View>
          <View style={[styles.bubble, styles.ai, { backgroundColor: colors.accentSoft }]}>
            <Text style={[styles.who, { color: colors.accent }]}>{tr('liveCommentsAiReply')}</Text>
            <Text style={[styles.body, { color: colors.text }]}>{item.ai_reply}</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 32, gap: 16 },
  block: { gap: 8 },
  bubble: { borderRadius: radii.lg, padding: spacing.md, gap: 4 },
  customer: { marginRight: 36 },
  ai: { marginLeft: 36 },
  who: { fontFamily: fonts.bodyMedium, fontSize: 12, fontWeight: '700' },
  body: { fontFamily: fonts.body, fontSize: 15, lineHeight: 21 },
});
