import { StyleSheet, Text, View } from 'react-native';

import type { ChatMessage } from '../../api/types';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { MessageActions } from './MessageActions';
import { MessageImageThumbs } from './MessageImageThumbs';

type Props = {
  message: ChatMessage;
  onRetry?: () => void;
  showActions?: boolean;
  /** Extra local preview URIs (e.g. after bootstrap rematch). */
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
      {!isUser ? (
        <Text style={{ color: colors.accent, fontSize: 14, marginBottom: 4 }}>✦</Text>
      ) : null}
      <View style={[styles.col, isUser && styles.colUser]}>
        {!isUser ? (
          <Text style={[styles.aiLabel, { color: colors.textDim }]}>Linas</Text>
        ) : null}
        <View
          style={[
            styles.bubble,
            isUser
              ? { backgroundColor: colors.bubbleUser, borderBottomRightRadius: 6 }
              : { backgroundColor: colors.bubbleAi, borderBottomLeftRadius: 6, borderColor: colors.border, borderWidth: 1 },
          ]}
        >
          {thumbs?.length ? <MessageImageThumbs uris={thumbs} /> : null}
          {hasText ? (
            <Text
              style={[
                styles.text,
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
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
  },
  rowUser: { alignSelf: 'flex-end' },
  rowAi: { alignSelf: 'flex-start' },
  col: { flexShrink: 1 },
  colUser: { alignItems: 'flex-end' },
  aiLabel: {
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
  text: {
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: 23,
  },
  rtl: { textAlign: 'right', writingDirection: 'rtl' },
});
