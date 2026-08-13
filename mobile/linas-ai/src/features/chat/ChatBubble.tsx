import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { ChatMessage } from '../../api/types';
import { LinasStarMark } from '../../components/LinasStarMark';
import { useReduceMotion } from '../../hooks/useReduceMotion';
import {
  aiMessageColStyle,
  aiMessageRowStyle,
  isRtlText,
  textDirectionStyle,
} from '../../lib/textDirection';
import { fonts, radii, spacing, typography, useTheme } from '../../theme';
import { AiMessageBody } from './AiMessageBody';
import { MessageActions } from './MessageActions';
import { MessageImageThumbs } from './MessageImageThumbs';
import { useOnceTypewriter } from './useWelcomeTypewriter';

type Props = {
  message: ChatMessage;
  onRetry?: () => void;
  showActions?: boolean;
  imageUris?: string[];
  userLabel?: string;
  /** One-shot type the seeded New Chat greeting into this bubble. */
  typewriter?: boolean;
  onTypewriterDone?: () => void;
};

export function ChatBubble({
  message,
  onRetry,
  showActions = true,
  imageUris,
  userLabel = 'You',
  typewriter = false,
  onTypewriterDone,
}: Props) {
  const { colors } = useTheme();
  const reduceMotion = useReduceMotion();
  const isUser = message.role === 'user';
  const thumbs = imageUris?.length ? imageUris : message.local_image_uris;
  const hasText = Boolean(message.content?.trim());
  const dirStyle = hasText ? textDirectionStyle(message.content) : null;
  const aiRtl = !isUser && isRtlText(message.content);
  const animate = Boolean(typewriter && !isUser && hasText && !reduceMotion);
  const { shown, done, cursorOn } = useOnceTypewriter(message.content, animate);
  const displayText = animate && !done ? shown : message.content;

  useEffect(() => {
    if (!typewriter) return;
    if (reduceMotion || done) onTypewriterDone?.();
  }, [done, onTypewriterDone, reduceMotion, typewriter]);

  return (
    <View
      style={[
        styles.row,
        isUser ? styles.rowUser : aiMessageRowStyle(message.content),
      ]}
    >
      <View
        style={[
          styles.col,
          isUser ? styles.colUser : aiMessageColStyle(message.content),
        ]}
      >
        {isUser ? (
          <Text style={[styles.userLabel, { color: colors.textDim }]}>{userLabel}</Text>
        ) : (
          <View style={styles.aiLabelRow}>
            <LinasStarMark size={12} labeled label="Linas" labelColor={colors.accentDeep} />
          </View>
        )}
        <View
          style={[
            isUser
              ? [styles.bubble, { backgroundColor: colors.bubbleUser }]
              : styles.aiBody,
          ]}
        >
          {thumbs?.length ? <MessageImageThumbs uris={thumbs} /> : null}
          {hasText ? (
            isUser ? (
              <Text
                style={[
                  styles.textUser,
                  { color: colors.bubbleUserText },
                  dirStyle,
                ]}
                accessibilityLabel={message.content}
              >
                {displayText}
              </Text>
            ) : animate && !done ? (
              <Text
                style={[styles.textAi, { color: colors.bubbleAiText }, dirStyle]}
                accessibilityLabel={message.content}
              >
                {displayText}
                {cursorOn ? <Text style={{ color: colors.accent }}>|</Text> : null}
              </Text>
            ) : (
              <AiMessageBody content={displayText} />
            )
          ) : null}
        </View>
        {!isUser && showActions ? (
          <MessageActions text={message.content} onRetry={onRetry} edgeRtl={aiRtl} />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    marginBottom: spacing.md,
  },
  rowUser: { alignSelf: 'flex-end', maxWidth: '88%' },
  col: { flexShrink: 1 },
  colUser: { alignItems: 'flex-end' },
  userLabel: {
    fontFamily: fonts.body,
    fontSize: 12,
    marginBottom: 4,
    marginRight: 4,
  },
  aiLabelRow: {
    marginBottom: 4,
  },
  bubble: {
    borderRadius: radii.bubble,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md - 2,
  },
  aiBody: {
    paddingHorizontal: 2,
    paddingVertical: 2,
  },
  textAi: {
    ...typography.chatAi,
  },
  textUser: {
    ...typography.chatUser,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '500',
  },
});
