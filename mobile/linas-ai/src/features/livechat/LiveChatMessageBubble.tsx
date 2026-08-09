import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, StyleSheet, Text, View } from 'react-native';

import { tokenStore } from '../../auth/tokenStore';
import { API_BASE } from '../../config';
import { colors, fonts, radii, spacing } from '../../theme';
import type { LiveChatMessage } from './liveChatTypes';
import { messageBody } from './liveChatTypes';

type Props = { message: LiveChatMessage };

function resolveMediaUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  if (raw.startsWith('http://') || raw.startsWith('https://') || raw.startsWith('data:')) return raw;
  if (raw.startsWith('/')) return `${API_BASE}${raw}`;
  return raw;
}

function needsAuth(url: string): boolean {
  return url.startsWith(API_BASE) && url.includes('/api/media/');
}

function AuthImage({ url }: { url: string }) {
  const [uri, setUri] = useState<string | null>(needsAuth(url) ? null : url);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!needsAuth(url)) {
      setUri(url);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const access = await tokenStore.getAccessToken();
        const res = await fetch(url, {
          headers: access ? { Authorization: `Bearer ${access}` } : {},
        });
        if (!res.ok) throw new Error('media');
        const buf = await res.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        const b64 = globalThis.btoa(binary);
        const ct = res.headers.get('content-type') || 'image/jpeg';
        if (!cancelled) setUri(`data:${ct};base64,${b64}`);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (failed) return <Text style={styles.mediaHint}>Image unavailable</Text>;
  if (!uri) return <ActivityIndicator color={colors.accent} />;
  return <Image source={{ uri }} style={styles.image} resizeMode="cover" />;
}

export function LiveChatMessageBubble({ message }: Props) {
  const isUser = Boolean(message.is_user);
  const handled = String(message.handled_by || message.role || '').toLowerCase();
  const isOperator = !isUser && (handled.includes('operator') || handled.includes('human'));
  const type = String(message.type || 'text').toLowerCase();
  const imageUrl = resolveMediaUrl(message.image_url || (type === 'image' ? message.media_url : null));
  const body = messageBody(message);

  return (
    <View style={[styles.wrap, isUser ? styles.userWrap : styles.botWrap]}>
      <View
        style={[
          styles.bubble,
          isUser && styles.userBubble,
          !isUser && isOperator && styles.opBubble,
          !isUser && !isOperator && styles.aiBubble,
        ]}
      >
        {imageUrl ? <AuthImage url={imageUrl} /> : null}
        {type === 'voice' || type === 'audio' ? (
          <Text style={[styles.text, isUser && styles.userText]}>🎤 {body}</Text>
        ) : (
          <Text style={[styles.text, isUser && styles.userText]}>{body}</Text>
        )}
        <Text style={[styles.meta, isUser && styles.userMeta]}>
          {isUser ? 'Customer' : isOperator ? 'Operator' : 'AI'}
          {message.timestamp ? ` · ${String(message.timestamp).slice(11, 16)}` : ''}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: spacing.sm, maxWidth: '88%' },
  userWrap: { alignSelf: 'flex-end' },
  botWrap: { alignSelf: 'flex-start' },
  bubble: {
    borderRadius: radii.bubble,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    borderWidth: 1,
    gap: 4,
  },
  userBubble: { backgroundColor: colors.bubbleUser, borderColor: colors.bubbleUser },
  opBubble: { backgroundColor: colors.mintSoft, borderColor: '#99F6E4' },
  aiBubble: { backgroundColor: colors.bubbleAi, borderColor: colors.border },
  text: { color: colors.text, fontFamily: fonts.body, fontSize: 15, lineHeight: 21 },
  userText: { color: colors.bubbleUserText },
  meta: { color: colors.textDim, fontFamily: fonts.body, fontSize: 11, marginTop: 2 },
  userMeta: { color: 'rgba(255,255,255,0.75)' },
  image: { width: 220, height: 160, borderRadius: radii.sm, marginBottom: 4 },
  mediaHint: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 },
});
