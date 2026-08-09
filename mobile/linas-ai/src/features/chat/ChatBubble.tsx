import { Image, StyleSheet, Text, View } from 'react-native';

import type { ChatMessage } from '../../api/types';
import { linasAssets } from '../linas/avatarAssets';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';

type Props = {
  message: ChatMessage;
};

export function ChatBubble({ message }: Props) {
  const { isRtl } = useI18n();
  const isUser = message.role === 'user';
  return (
    <View style={[styles.row, isUser ? styles.rowUser : styles.rowAi]}>
      {!isUser ? (
        <Image source={linasAssets.portrait} style={styles.avatar} />
      ) : null}
      <View style={[styles.col, isUser && styles.colUser]}>
        {!isUser ? <Text style={styles.aiLabel}>Linas</Text> : null}
        <View style={[styles.bubble, isUser ? styles.user : styles.ai]}>
          <Text
            style={[
              styles.text,
              isUser ? styles.userText : styles.aiText,
              isRtl && styles.rtl,
            ]}
          >
            {message.content}
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    marginBottom: spacing.md,
    maxWidth: '94%',
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
  },
  rowUser: { alignSelf: 'flex-end' },
  rowAi: { alignSelf: 'flex-start' },
  avatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    marginBottom: 2,
  },
  col: { flexShrink: 1 },
  colUser: { alignItems: 'flex-end' },
  aiLabel: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    marginBottom: 4,
    marginLeft: 6,
  },
  bubble: {
    borderRadius: radii.bubble,
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: spacing.md,
  },
  user: {
    backgroundColor: colors.bubbleUser,
    borderBottomRightRadius: 6,
  },
  ai: {
    backgroundColor: colors.bubbleAi,
    borderBottomLeftRadius: 6,
  },
  text: {
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: 23,
  },
  aiText: { color: colors.bubbleAiText },
  userText: { color: colors.bubbleUserText },
  rtl: { textAlign: 'right', writingDirection: 'rtl' },
});
