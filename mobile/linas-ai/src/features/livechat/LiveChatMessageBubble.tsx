import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { textDirectionStyle } from '../../lib/textDirection';
import { colors, fonts, radii, spacing } from '../../theme';
import {
  LiveChatAuthImage,
  LiveChatVoicePlay,
  LiveChatVoiceUnavailable,
  resolveMediaUrl,
} from './LiveChatMedia';
import type { LiveChatMessage } from './liveChatTypes';
import { formatBubbleTime, isLikeableAiReply, isVoiceMessage, messageBody } from './liveChatTypes';

type Props = {
  message: LiveChatMessage;
  onLike?: () => void;
};

export function LiveChatMessageBubble({ message, onLike }: Props) {
  const { tr } = useI18n();
  const isCustomer = Boolean(message.is_user);
  const handled = String(message.handled_by || message.role || '').toLowerCase();
  const isOperator = !isCustomer && (handled.includes('operator') || handled.includes('human'));
  const type = String(message.type || 'text').toLowerCase();
  const voice = isVoiceMessage(message);
  const imageUrl = resolveMediaUrl(message.image_url || (type === 'image' ? message.media_url : null));
  const audioUrl = resolveMediaUrl(message.audio_url || (voice ? message.media_url : null));
  const body = messageBody(message);
  const dirStyle = textDirectionStyle(body);
  const time = formatBubbleTime(message.timestamp || undefined);
  const showLike = Boolean(onLike) && isLikeableAiReply(message);

  return (
    <View style={[styles.wrap, isCustomer ? styles.inWrap : styles.outWrap]}>
      <View
        style={[
          styles.bubble,
          isCustomer && styles.inBubble,
          !isCustomer && isOperator && styles.opBubble,
          !isCustomer && !isOperator && styles.aiBubble,
        ]}
      >
        {imageUrl ? <LiveChatAuthImage url={imageUrl} /> : null}
        {voice ? (
          audioUrl ? (
            <LiveChatVoicePlay url={audioUrl} onAccent={isOperator} />
          ) : (
            <LiveChatVoiceUnavailable onAccent={isOperator} />
          )
        ) : (
          <Text style={[styles.text, isOperator && styles.opText, dirStyle]}>{body}</Text>
        )}
        <Text style={[styles.meta, isOperator && styles.opMeta]}>
          {isCustomer ? 'Customer' : isOperator ? 'You' : 'AI'}
          {time ? ` · ${time}` : ''}
        </Text>
      </View>
      {showLike ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={tr('likeFaqTitle')}
          hitSlop={8}
          onPress={onLike}
          style={styles.likeBtn}
        >
          <Text style={styles.likeLabel}>👍 {tr('likeFaqAction')}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: spacing.sm, maxWidth: '88%' },
  inWrap: { alignSelf: 'flex-start' },
  outWrap: { alignSelf: 'flex-end' },
  bubble: {
    borderRadius: radii.bubble,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    borderWidth: 1,
    gap: 4,
  },
  inBubble: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderBottomLeftRadius: 4,
  },
  opBubble: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    backgroundColor: colors.bubbleAi,
    borderColor: colors.border,
    borderBottomRightRadius: 4,
  },
  text: { color: colors.text, fontFamily: fonts.body, fontSize: 15, lineHeight: 21 },
  opText: { color: colors.onAccent },
  meta: { color: colors.textDim, fontFamily: fonts.body, fontSize: 11, marginTop: 2 },
  opMeta: { color: 'rgba(255,255,255,0.75)' },
  likeBtn: {
    alignSelf: 'flex-end',
    marginTop: 4,
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderRadius: radii.sm,
    backgroundColor: colors.surfaceAlt,
    borderWidth: 1,
    borderColor: colors.border,
  },
  likeLabel: { color: colors.accentDeep, fontFamily: fonts.bodyMedium, fontSize: 12 },
});
