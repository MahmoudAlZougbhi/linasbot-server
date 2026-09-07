import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { AppModal } from '../../../components/AppModal';
import { ModalScrim } from '../../../components/ModalScrim';
import { PrimaryButton } from '../../../components/PrimaryButton';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { CommentMediaItem } from './commentsInboxTypes';

type Props = {
  post: CommentMediaItem | null;
  accountName: string;
  onClose: () => void;
  onView: () => void;
  onOpenThread: () => void;
  onToggleWatch: () => void;
};

export function CommentPostSheet({ post, accountName, onClose, onView, onOpenThread, onToggleWatch }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  if (!post) return null;
  const kind =
    post.kind === 'reel' ? tr('liveCommentsReel') : post.kind === 'video' ? tr('liveCommentsVideo') : tr('liveCommentsPost');
  return (
    <AppModal visible onRequestClose={onClose}>
      <ModalScrim onPress={onClose} justify="flex-end" accessibilityLabel={tr('liveCommentsClose')}>
        <Pressable style={[styles.sheet, { backgroundColor: colors.surface }]} onPress={(event) => event.stopPropagation()}>
          <View style={styles.handle} />
          {post.thumbnail ? <Image source={{ uri: post.thumbnail }} style={styles.hero} /> : null}
          <Text style={[styles.name, { color: colors.text }]}>{accountName || tr('liveCommentsUntitled')}</Text>
          <Text style={[styles.badge, { color: colors.accent }]}>{kind}</Text>
          <Text style={[styles.caption, { color: colors.text }]} numberOfLines={6}>
            {post.caption || tr('liveCommentsNoCaption')}
          </Text>
          <Text style={[styles.meta, { color: colors.textMuted }]}>
            {post.comment_count === 1
              ? tr('liveCommentsCountOne')
              : tr('liveCommentsCount').replace('{count}', String(post.comment_count))}
          </Text>
          <Pressable
            onPress={onToggleWatch}
            style={[styles.watch, { borderColor: post.watched ? colors.accent : colors.border }]}
            accessibilityRole="switch"
            accessibilityState={{ checked: post.watched }}
          >
            <AppIcon icon={feather(post.watched ? 'check-circle' : 'circle')} size={18} color={colors.accent} />
            <Text style={[styles.watchText, { color: colors.text }]}>
              {post.watched ? tr('liveCommentsReplyOn') : tr('liveCommentsReplyOff')}
            </Text>
          </Pressable>
          <View style={styles.actions}>
            <PrimaryButton label={tr('liveCommentsView')} onPress={onView} style={styles.action} />
            <PrimaryButton label={tr('liveCommentsOpenThread')} onPress={onOpenThread} style={styles.action} />
          </View>
        </Pressable>
      </ModalScrim>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  sheet: {
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    padding: spacing.lg,
    gap: 8,
  },
  handle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#D1D5DB',
    marginBottom: 4,
  },
  hero: { width: '100%', height: 180, borderRadius: radii.md, backgroundColor: '#111827' },
  name: { fontFamily: fonts.bodyMedium, fontSize: 18, fontWeight: '700' },
  badge: { fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '700' },
  caption: { fontFamily: fonts.body, fontSize: 15, lineHeight: 21 },
  meta: { fontFamily: fonts.body, fontSize: 13 },
  watch: {
    minHeight: 44,
    borderWidth: 1.5,
    borderRadius: radii.md,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  watchText: { fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '600' },
  actions: { flexDirection: 'row', gap: 8, marginTop: 4 },
  action: { flex: 1 },
});
