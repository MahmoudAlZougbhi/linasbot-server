import { Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';
import {
  type LiveChatItem,
  channelLabel,
  chatPreview,
  chatTitle,
  normalizeStatus,
  statusLabel,
  statusTone,
} from './liveChatTypes';

type Props = {
  item: LiveChatItem;
  onPress: () => void;
};

export function ConversationRow({ item, onPress }: Props) {
  const status = normalizeStatus(item);
  const unread = item.unread_count ?? 0;
  return (
    <Pressable style={styles.row} onPress={onPress}>
      <View style={styles.top}>
        <Text style={styles.title} numberOfLines={1}>
          {chatTitle(item)}
        </Text>
        {unread > 0 ? (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{unread > 99 ? '99+' : unread}</Text>
          </View>
        ) : null}
      </View>
      <Text style={styles.preview} numberOfLines={2}>
        {chatPreview(item)}
      </Text>
      <View style={styles.meta}>
        <StatusChip label={statusLabel(status)} tone={statusTone(status)} />
        <StatusChip label={channelLabel(item)} tone="neutral" />
        {item.is_new_customer ? <StatusChip label="New" tone="warn" /> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: 6,
  },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  title: { flex: 1, color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16 },
  preview: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  badge: {
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { color: colors.onAccent, fontFamily: fonts.bodyMedium, fontSize: 11 },
});
