import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { CM_BORDER, CM_ICON_SQ, CM_MUTED, CM_RADIUS, CM_TEAL, CM_TEAL_DARK, CM_TEAL_SOFT } from './commentChrome';
import { replyInLabelKey, replyInOf, replyTypeOf, uniquePostIds, type CommentRuleItem } from './commentModel';

type Props = {
  item: CommentRuleItem;
  untitled: string;
  onPress: () => void;
  tr: (key: StringKey) => string;
};

export function CommentCard({ item, untitled, onPress, tr }: Props) {
  const isAi = replyTypeOf(item) === 'ai';
  const selected = uniquePostIds(item).length > 0;
  const replyKey = replyInLabelKey(replyInOf(item));
  const count = item.attachments.length;
  const resources =
    count === 1 ? tr('commentsResourcesOne') : tr('commentsResourcesCount').replace('{count}', String(count));
  const meta = [
    tr(isAi ? 'commentsMetaAi' : 'commentsMetaAutomatic'),
    tr(isAi ? 'commentsMetaNote' : 'commentsMetaFixed'),
    tr(selected ? 'commentsMetaSelected' : 'commentsMetaAllPosts'),
  ].join(' · ');

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={item.name || untitled}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.top}>
        <View style={styles.iconSq}>
          <AppIcon icon={feather('message-circle')} size={20} color={CM_TEAL} />
        </View>
        <View style={styles.copy}>
          <Text style={styles.title} numberOfLines={1}>
            {item.name.trim() || untitled}
          </Text>
          <Text style={styles.meta} numberOfLines={2}>
            {meta}
          </Text>
        </View>
        <AppIcon icon={feather('chevron-right')} size={18} color={CM_MUTED} />
      </View>
      <View style={styles.divider} />
      <View style={styles.foot}>
        <View style={styles.footLeft}>
          <AppIcon icon={feather('message-circle')} size={12} color={CM_TEAL} />
          <Text style={styles.footText} numberOfLines={1}>
            {`${tr(replyKey)} · ${resources}`}
          </Text>
        </View>
        <Text style={styles.status}>{item.enabled ? tr('commentsActive') : tr('commentsInactive')}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderColor: CM_BORDER,
    borderWidth: 1,
    borderRadius: CM_RADIUS,
    padding: 14,
    gap: 10,
  },
  pressed: { opacity: 0.7 },
  top: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  iconSq: {
    width: CM_ICON_SQ,
    height: CM_ICON_SQ,
    borderRadius: 10,
    backgroundColor: CM_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 4 },
  title: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    fontWeight: '700',
  },
  meta: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: CM_BORDER },
  foot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  footLeft: { flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 },
  footText: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 12, flex: 1 },
  status: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 12 },
});
