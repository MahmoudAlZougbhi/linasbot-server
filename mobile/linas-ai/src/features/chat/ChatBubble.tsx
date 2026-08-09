import { StyleSheet, Text, View } from 'react-native';

import type { ChatMessage } from '../../api/types';
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
      {!isUser ? <Text style={styles.aiLabel}>Linas</Text> : null}
      <View style={[styles.bubble, isUser ? styles.user : styles.ai]}>
        <Text style={[styles.text, isRtl && styles.rtl]}>{message.content}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { marginBottom: spacing.md, maxWidth: '92%' },
  rowUser: { alignSelf: 'flex-end' },
  rowAi: { alignSelf: 'flex-start' },
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
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderBottomLeftRadius: 6,
  },
  text: {
    color: colors.text,
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: 23,
  },
  rtl: { textAlign: 'right', writingDirection: 'rtl' },
});
