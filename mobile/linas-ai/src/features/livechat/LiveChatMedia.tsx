import { useAudioPlayer, useAudioPlayerStatus, setAudioModeAsync } from 'expo-audio';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { tokenStore } from '../../auth/tokenStore';
import { AppIcon, feather } from '../../components/AppIcon';
import { API_BASE } from '../../config';
import { colors, fonts, radii } from '../../theme';

export function resolveMediaUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  if (raw.startsWith('http://') || raw.startsWith('https://') || raw.startsWith('data:')) return raw;
  if (raw.startsWith('/')) return `${API_BASE}${raw}`;
  return raw;
}

function needsAuth(url: string): boolean {
  return url.startsWith(API_BASE) && url.includes('/api/media/');
}

async function fetchAuthDataUri(url: string, fallbackType: string): Promise<string> {
  const access = await tokenStore.getAccessToken();
  const res = await fetch(url, {
    headers: access ? { Authorization: `Bearer ${access}` } : {},
  });
  if (!res.ok) throw new Error('media');
  const buf = await res.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  const ct = res.headers.get('content-type') || fallbackType;
  return `data:${ct};base64,${globalThis.btoa(binary)}`;
}

export function LiveChatAuthImage({ url }: { url: string }) {
  const [uri, setUri] = useState<string | null>(needsAuth(url) ? null : url);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!needsAuth(url)) {
      setUri(url);
      return;
    }
    let cancelled = false;
    void fetchAuthDataUri(url, 'image/jpeg')
      .then((next) => {
        if (!cancelled) setUri(next);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (failed) return <Text style={styles.mediaHint}>Image unavailable</Text>;
  if (!uri) return <ActivityIndicator color={colors.accent} />;
  return <Image source={{ uri }} style={styles.image} resizeMode="cover" />;
}

function VoicePlayer({ uri, onAccent }: { uri: string; onAccent?: boolean }) {
  const player = useAudioPlayer({ uri });
  const status = useAudioPlayerStatus(player);
  const playing = Boolean(status.playing);
  const ink = onAccent ? colors.onAccent : colors.text;

  useEffect(() => {
    void setAudioModeAsync({
      allowsRecording: false,
      playsInSilentMode: true,
      interruptionMode: 'mixWithOthers',
    });
  }, []);

  const toggle = () => {
    if (playing) {
      player.pause();
      return;
    }
    if (status.didJustFinish) {
      void player.seekTo(0);
    }
    player.play();
  };

  return (
    <Pressable
      onPress={toggle}
      accessibilityRole="button"
      accessibilityLabel={playing ? 'Pause voice message' : 'Play voice message'}
      style={styles.voiceRow}
    >
      <AppIcon icon={feather(playing ? 'pause' : 'play')} size={18} color={ink} />
      <Text style={[styles.voiceLabel, { color: ink }]}>Voice</Text>
    </Pressable>
  );
}

export function LiveChatVoicePlay({ url, onAccent }: { url: string; onAccent?: boolean }) {
  const [playUri, setPlayUri] = useState<string | null>(needsAuth(url) ? null : url);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!needsAuth(url)) {
      setPlayUri(url);
      return;
    }
    let cancelled = false;
    void fetchAuthDataUri(url, 'audio/mp4')
      .then((next) => {
        if (!cancelled) setPlayUri(next);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (failed) return <Text style={[styles.mediaHint, onAccent && styles.onAccentHint]}>Voice unavailable</Text>;
  if (!playUri) return <ActivityIndicator color={onAccent ? colors.onAccent : colors.accent} />;
  return <VoicePlayer key={playUri.slice(0, 48)} uri={playUri} onAccent={onAccent} />;
}

export function LiveChatVoiceUnavailable({ onAccent }: { onAccent?: boolean }) {
  return (
    <View style={styles.voiceRow}>
      <AppIcon icon={feather('mic')} size={16} color={onAccent ? colors.onAccent : colors.textMuted} />
      <Text style={[styles.mediaHint, onAccent && styles.onAccentHint]}>Voice unavailable</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  image: { width: 220, height: 160, borderRadius: radii.sm, marginBottom: 4 },
  mediaHint: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 },
  onAccentHint: { color: 'rgba(255,255,255,0.8)' },
  voiceRow: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 28, paddingVertical: 2 },
  voiceLabel: { fontFamily: fonts.bodyMedium, fontSize: 15 },
});
