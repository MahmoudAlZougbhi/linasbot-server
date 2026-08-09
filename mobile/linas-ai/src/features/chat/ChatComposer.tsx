import { useEffect, useRef, type RefObject } from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, fonts, radii, spacing } from '../../theme';
import type { VoiceState } from './useVoiceDraft';

type Props = {
  draft: string;
  onChangeDraft: (v: string) => void;
  onSend: () => void;
  onPlus: () => void;
  onToggleVoice: () => void;
  sending: boolean;
  voiceState: VoiceState;
  metering?: number | null;
  inputRef?: RefObject<TextInput | null>;
};

function MicBars({ metering }: { metering: number | null | undefined }) {
  // expo-audio metering is roughly -160..0 dB; map to 3 bar heights.
  const level = metering == null ? 0.35 : Math.min(1, Math.max(0.15, (metering + 50) / 50));
  const heights = [0.45, 1, 0.65].map((w) => 6 + level * 14 * w);
  return (
    <View style={styles.bars}>
      {heights.map((h, i) => (
        <View key={i} style={[styles.bar, { height: h }]} />
      ))}
    </View>
  );
}

export function ChatComposer({
  draft,
  onChangeDraft,
  onSend,
  onPlus,
  onToggleVoice,
  sending,
  voiceState,
  metering,
  inputRef,
}: Props) {
  const insets = useSafeAreaInsets();
  const pulse = useRef(new Animated.Value(1)).current;
  const recording = voiceState === 'recording';
  const transcribing = voiceState === 'transcribing';

  useEffect(() => {
    if (!recording) {
      pulse.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1.12, duration: 420, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 420, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [recording, pulse]);

  return (
    <View style={[styles.wrap, { paddingBottom: Math.max(insets.bottom, 10) }]}>
      <Pressable style={styles.round} onPress={onPlus} accessibilityLabel="More actions">
        <Text style={styles.roundText}>+</Text>
      </Pressable>
      <TextInput
        ref={inputRef}
        style={styles.input}
        placeholder={recording ? 'Listening…' : transcribing ? 'Transcribing…' : 'Message Linas AI'}
        placeholderTextColor={colors.textDim}
        value={draft}
        onChangeText={onChangeDraft}
        multiline
        editable={!transcribing}
      />
      <Animated.View style={{ transform: [{ scale: pulse }] }}>
        <Pressable
          style={[styles.round, recording && styles.micActive, transcribing && styles.micBusy]}
          onPress={onToggleVoice}
          disabled={transcribing}
          accessibilityLabel={recording ? 'Stop recording' : 'Start voice input'}
        >
          {transcribing ? (
            <ActivityIndicator color={colors.accent} size="small" />
          ) : recording ? (
            <MicBars metering={metering} />
          ) : (
            <Text style={styles.roundText}>🎙</Text>
          )}
        </Pressable>
      </Animated.View>
      <Pressable
        style={[styles.send, (!draft.trim() || sending || recording || transcribing) && styles.sendDisabled]}
        onPress={onSend}
        disabled={sending || !draft.trim() || recording || transcribing}
        accessibilityLabel="Send message"
      >
        {sending ? (
          <ActivityIndicator color={colors.onAccent} />
        ) : (
          <Text style={styles.sendText}>↑</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.borderSoft,
    backgroundColor: colors.bgElevated,
  },
  round: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  micActive: {
    backgroundColor: colors.accentSoft,
    borderColor: colors.accent,
  },
  micBusy: {
    opacity: 0.85,
  },
  roundText: { color: colors.accent, fontSize: 18, fontWeight: '700' },
  bars: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    height: 22,
  },
  bar: {
    width: 3,
    borderRadius: 2,
    backgroundColor: colors.accent,
  },
  input: {
    flex: 1,
    minHeight: 42,
    maxHeight: 120,
    backgroundColor: colors.input,
    borderRadius: radii.lg,
    color: colors.text,
    fontFamily: fonts.body,
    fontSize: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: colors.border,
  },
  send: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendDisabled: { opacity: 0.45 },
  sendText: { color: colors.onAccent, fontSize: 20, fontWeight: '800' },
});
