import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, useTheme } from '../../theme';
import { PlatformChannelIcon } from './PlatformChannelIcon';
import {
  type LiveChatItem,
  assigneeLabel,
  chatChannel,
  chatLastAt,
  chatPreview,
  chatTitle,
  formatInboxTime,
} from './liveChatTypes';

type Props = {
  item: LiveChatItem;
  onPress: () => void;
};

export function ConversationRow({ item, onPress }: Props) {
  const { colors } = useTheme();
  const unread = item.unread_count ?? 0;
  const time = formatInboxTime(chatLastAt(item));
  const assignee = assigneeLabel(item);
  const badge = unread > 0 ? (unread > 99 ? '99+' : String(unread)) : null;

  return (
    <Pressable
      style={[styles.row, { borderBottomColor: colors.borderSoft }]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={chatTitle(item)}
    >
      <PlatformChannelIcon channel={chatChannel(item)} />
      <View style={styles.middle}>
        <Text style={[styles.name, { color: colors.text }]} numberOfLines={1}>
          {chatTitle(item)}
        </Text>
        <Text style={[styles.preview, { color: colors.textMuted }]} numberOfLines={1}>
          {chatPreview(item)}
        </Text>
      </View>
      <View style={styles.meta}>
        {time ? (
          <Text style={[styles.time, { color: colors.textDim }]}>{time}</Text>
        ) : null}
        {badge ? (
          <View style={[styles.badge, { backgroundColor: colors.accentDeep }]}>
            <Text style={[styles.badgeText, { color: colors.onAccent }]}>{badge}</Text>
          </View>
        ) : (
          <View style={styles.badgeSpacer} />
        )}
        <Text style={[styles.assignee, { color: colors.textDim }]} numberOfLines={1}>
          {assignee}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  middle: { flex: 1, minWidth: 0, gap: 4, justifyContent: 'center' },
  name: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  preview: { fontFamily: fonts.body, fontSize: 14 },
  meta: { alignItems: 'flex-end', justifyContent: 'center', gap: 4, minWidth: 56 },
  time: { fontFamily: fonts.body, fontSize: 12 },
  badge: {
    minWidth: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { fontFamily: fonts.bodyMedium, fontSize: 11 },
  badgeSpacer: { height: 4 },
  assignee: { fontFamily: fonts.body, fontSize: 12, maxWidth: 88 },
});
