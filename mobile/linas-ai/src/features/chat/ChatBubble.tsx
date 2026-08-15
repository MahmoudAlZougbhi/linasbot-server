import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { ChatMessage } from '../../api/types';
import { LinasStarMark } from '../../components/LinasStarMark';
import { useReduceMotion } from '../../hooks/useReduceMotion';
import {
  aiMessageColStyle,
  aiMessageHeaderStyle,
  aiMessageRowStyle,
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
  linasLabel?: string;
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
  linasLabel = 'Linas',
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
    <View
      style={[
        styles.row,
        isUser ? styles.rowUser : [styles.rowAi, aiMessageRowStyle(message.content)],
      ]}
    >
      <View style={[styles.col, isUser ? styles.colUser : styles.colAi]}>
        {isUser ? (
          <Text style={[styles.userLabel, { color: colors.textDim }]}>{userLabel}</Text>
        ) : (
          <View style={[styles.aiLabelRow, aiMessageHeaderStyle]}>
            <LinasStarMark
              size={16}
              labelSize={13}
              labeled
              label={linasLabel}
              labelColor={colors.text}
            />
          </View>
        )}
        {isUser ? (
          <View style={[styles.bubble, { backgroundColor: colors.bubbleUser }]}>
            {thumbs?.length ? <MessageImageThumbs uris={thumbs} /> : null}
            {hasText ? (
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
            ) : null}
          </View>
        ) : (
          <View style={[styles.aiBodyCol, aiMessageColStyle(message.content)]}>
            <View style={styles.aiBody}>
              {thumbs?.length ? <MessageImageThumbs uris={thumbs} /> : null}
              {hasText ? (
                animate && !done ? (
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
            {showActions ? <MessageActions text={message.content} onRetry={onRetry} /> : null}
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    marginBottom: spacing.md,
  },
  rowUser: { alignSelf: 'flex-end', maxWidth: '88%' },
  rowAi: { alignSelf: 'flex-start', maxWidth: '88%' },
  col: { flexShrink: 1 },
  colUser: { alignItems: 'flex-end' },
  colAi: { width: '100%' },
  userLabel: {
    fontFamily: fonts.body,
    fontSize: 12,
    marginBottom: 4,
    marginRight: 4,
  },
  aiLabelRow: {
    alignSelf: 'flex-start',
    paddingTop: 4,
    paddingBottom: 2,
    marginBottom: 4,
    overflow: 'visible',
  },
  aiBodyCol: {
    width: '100%',
    alignSelf: 'stretch',
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
  },
});
