import { StyleSheet, Text, View } from 'react-native';

import type { ChatMessage } from '../../api/types';
import { LinasStarMark } from '../../components/LinasStarMark';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, typography, useTheme } from '../../theme';
import { MessageActions } from './MessageActions';
import { MessageImageThumbs } from './MessageImageThumbs';

type Props = {
  message: ChatMessage;
  onRetry?: () => void;
  showActions?: boolean;
  imageUris?: string[];
};

function detectRtl(text: string): boolean {
  return /[\u0600-\u06FF]/.test(text) && !/^[A-Za-z0-9\s.,!?'"()-]+$/.test(text.trim());
}

export function ChatBubble({ message, onRetry, showActions = true, imageUris }: Props) {
  const { isRtl } = useI18n();
  const { colors } = useTheme();
  const isUser = message.role === 'user';
  const rtl = isRtl || detectRtl(message.content);
  const thumbs = imageUris?.length ? imageUris : message.local_image_uris;
  const hasText = Boolean(message.content?.trim());

  return (
    <View style={[styles.row, isUser ? styles.rowUser : styles.rowAi]}>
      <View style={[styles.col, isUser && styles.colUser]}>
        {isUser ? (
          <Text style={[styles.userLabel, { color: colors.textDim }]}>You</Text>
        ) : (
          <View style={styles.aiLabelRow}>
            <LinasStarMark size={12} labeled label="Linas" />
          </View>
        )}
        <View
          style={[
            isUser
              ? [styles.bubble, { backgroundColor: colors.bubbleUser, borderBottomRightRadius: 6 }]
              : styles.aiBody,
          ]}
        >
          {thumbs?.length ? <MessageImageThumbs uris={thumbs} /> : null}
          {hasText ? (
            <Text
              style={[
                isUser ? styles.textUser : styles.textAi,
                { color: isUser ? colors.bubbleUserText : colors.bubbleAiText },
                rtl && styles.rtl,
              ]}
            >
              {message.content}
            </Text>
          ) : null}
        </View>
        {!isUser && showActions ? (
          <MessageActions text={message.content} onRetry={onRetry} />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    marginBottom: spacing.md,
    maxWidth: '94%',
  },
  rowUser: { alignSelf: 'flex-end' },
  rowAi: { alignSelf: 'flex-start' },
  col: { flexShrink: 1 },
  colUser: { alignItems: 'flex-end' },
  userLabel: {
    fontFamily: fonts.body,
    fontSize: 11,
    marginBottom: 4,
    marginRight: 6,
  },
  aiLabelRow: {
    marginBottom: 4,
    marginLeft: 2,
  },
  bubble: {
    borderRadius: radii.bubble,
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: spacing.md,
  },
  aiBody: {
    paddingHorizontal: 4,
    paddingVertical: 2,
  },
  textAi: {
    ...typography.chatAi,
  },
  textUser: {
    ...typography.chatUser,
  },
  rtl: { textAlign: 'right', writingDirection: 'rtl' },
});
