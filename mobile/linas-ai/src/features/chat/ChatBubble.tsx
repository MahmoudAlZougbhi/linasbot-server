import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { ChatMessage } from '../../api/types';
import { LinasStarMark } from '../../components/LinasStarMark';
import { useReduceMotion } from '../../hooks/useReduceMotion';
import { textDirectionStyle } from '../../lib/textDirection';
import { fonts, radii, spacing, typography, useTheme } from '../../theme';
import { MessageActions } from './MessageActions';
import { MessageImageThumbs } from './MessageImageThumbs';
import { useOnceTypewriter } from './useWelcomeTypewriter';

type Props = {
  message: ChatMessage;
  onRetry?: () => void;
  showActions?: boolean;
  imageUris?: string[];
  /** One-shot type the seeded New Chat greeting into this bubble. */
  typewriter?: boolean;
  onTypewriterDone?: () => void;
};

export function ChatBubble({
  message,
  onRetry,
  showActions = true,
  imageUris,
  typewriter = false,
  onTypewriterDone,
}: Props) {
  const { colors } = useTheme();
  const reduceMotion = useReduceMotion();
  const isUser = message.role === 'user';
  const thumbs = imageUris?.length ? imageUris : message.local_image_uris;
  const hasText = Boolean(message.content?.trim());
  const dirStyle = hasText ? textDirectionStyle(message.content) : null;
  const animate = Boolean(typewriter && !isUser && hasText && !reduceMotion);
  const { shown, done, cursorOn } = useOnceTypewriter(message.content, animate);
  const displayText = animate && !done ? shown : message.content;

  useEffect(() => {
    if (!typewriter) return;
    if (reduceMotion || done) onTypewriterDone?.();
  }, [done, onTypewriterDone, reduceMotion, typewriter]);

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
                dirStyle,
              ]}
              accessibilityLabel={message.content}
            >
              {displayText}
              {animate && !done && cursorOn ? (
                <Text style={{ color: colors.accent }}>|</Text>
              ) : null}
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
});
