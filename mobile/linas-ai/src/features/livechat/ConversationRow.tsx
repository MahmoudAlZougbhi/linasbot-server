import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fonts } from '../../theme';
import {
  type LiveChatItem,
  channelLabel,
  chatAvatarLetter,
  chatLastAt,
  chatPreview,
  chatTitle,
  formatInboxTime,
  normalizeStatus,
} from './liveChatTypes';

type Props = {
  item: LiveChatItem;
  onPress: () => void;
};

export function ConversationRow({ item, onPress }: Props) {
  const unread = item.unread_count ?? 0;
  const status = normalizeStatus(item);
  const time = formatInboxTime(chatLastAt(item));
  const waiting = status === 'waiting_human';

  return (
    <Pressable style={styles.row} onPress={onPress}>
      <View style={[styles.avatar, waiting && styles.avatarWaiting]}>
        <Text style={styles.avatarText}>{chatAvatarLetter(item)}</Text>
      </View>
      <View style={styles.body}>
        <View style={styles.top}>
          <Text style={[styles.title, unread > 0 && styles.titleUnread]} numberOfLines={1}>
            {chatTitle(item)}
          </Text>
          {time ? (
            <Text style={[styles.time, unread > 0 && styles.timeUnread]}>{time}</Text>
          ) : null}
        </View>
        <View style={styles.bottom}>
          <Text style={[styles.preview, unread > 0 && styles.previewUnread]} numberOfLines={1}>
            {chatPreview(item)}
          </Text>
          {unread > 0 ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{unread > 99 ? '99+' : unread}</Text>
            </View>
          ) : (
            <Text style={styles.channel}>{channelLabel(item)}</Text>
          )}
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 12,
    paddingHorizontal: 4,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.accentSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarWaiting: { backgroundColor: '#FDE68A' },
  avatarText: { color: colors.accentDeep, fontFamily: fonts.bodyMedium, fontSize: 18 },
  body: { flex: 1, minWidth: 0, gap: 3 },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  title: { flex: 1, color: colors.text, fontFamily: fonts.body, fontSize: 16 },
  titleUnread: { fontFamily: fonts.bodyMedium },
  time: { color: colors.textDim, fontFamily: fonts.body, fontSize: 12 },
  timeUnread: { color: colors.accent, fontFamily: fonts.bodyMedium },
  bottom: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  preview: { flex: 1, color: colors.textMuted, fontFamily: fonts.body, fontSize: 14 },
  previewUnread: { color: colors.text, fontFamily: fonts.bodyMedium },
  channel: { color: colors.textDim, fontFamily: fonts.body, fontSize: 11 },
  badge: {
    minWidth: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { color: colors.onAccent, fontFamily: fonts.bodyMedium, fontSize: 11 },
});
