import { useEffect, useRef, type RefObject } from 'react';
import {
  ActivityIndicator,
  Animated,
  Keyboard,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { HIT, fonts, radii, spacing, useTheme } from '../../theme';
import type { VoiceState } from './useVoiceDraft';

type Props = {
  draft: string;
  onChangeDraft: (v: string) => void;
  onSend: () => void;
  onPlus?: () => void;
  onToggleVoice?: () => void;
  onStop?: () => void;
  sending: boolean;
  canSendWithAttachment?: boolean;
  voiceState?: VoiceState;
  metering?: number | null;
  inputRef?: RefObject<TextInput | null>;
  /** Hide non-working controls (guest Plus/Mic incomplete → hidden). */
  showPlus?: boolean;
  showMic?: boolean;
  showDisclaimer?: boolean;
  autoFocus?: boolean;
};

export function ChatComposer({
  draft,
  onChangeDraft,
  onSend,
  onPlus,
  onToggleVoice,
  onStop,
  sending,
  canSendWithAttachment = false,
  voiceState = 'idle',
  metering: _metering,
  inputRef,
  showPlus = false,
  showMic = false,
  showDisclaimer = true,
  autoFocus = false,
}: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const pulse = useRef(new Animated.Value(1)).current;
  const recording = voiceState === 'recording';
  const transcribing = voiceState === 'transcribing';
  const canSend = Boolean(draft.trim() || canSendWithAttachment);
  const streamingStop = Boolean(onStop && sending);

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

  useEffect(() => {
    if (!autoFocus) return;
    const t = setTimeout(() => inputRef?.current?.focus(), 120);
    return () => clearTimeout(t);
  }, [autoFocus, inputRef]);

  function handleSend() {
    if (sending || !canSend || recording || transcribing) return;
    inputRef?.current?.blur();
    Keyboard.dismiss();
    onSend();
  }

  return (
    <View
      style={[
        styles.wrap,
        {
          paddingBottom: Math.max(insets.bottom, 10),
          borderTopColor: colors.borderSoft,
          backgroundColor: colors.bgElevated,
        },
      ]}
    >
      <View style={styles.row}>
        {showPlus && onPlus ? (
          <Pressable
            style={[styles.round, { backgroundColor: colors.surface, borderColor: colors.border }]}
            onPress={onPlus}
            accessibilityLabel="More actions"
          >
            <Text style={{ color: colors.accent, fontSize: 18, fontWeight: '700' }}>+</Text>
          </Pressable>
        ) : null}
        <TextInput
          ref={inputRef}
          style={[
            styles.input,
            {
              backgroundColor: colors.input,
              color: colors.text,
              borderColor: colors.border,
            },
          ]}
          placeholder={recording ? 'Listening…' : transcribing ? 'Transcribing…' : 'Message Linas'}
          placeholderTextColor={colors.textDim}
          value={draft}
          onChangeText={onChangeDraft}
          multiline
          editable={!transcribing}
          autoFocus={autoFocus}
          blurOnSubmit={false}
          accessibilityLabel="Message Linas"
        />
        {showMic && onToggleVoice && !canSend && !streamingStop ? (
          <Animated.View style={{ transform: [{ scale: pulse }] }}>
            <Pressable
              style={[
                styles.round,
                { backgroundColor: colors.surface, borderColor: colors.border },
                recording && { backgroundColor: colors.accentSoft, borderColor: colors.accent },
              ]}
              onPress={onToggleVoice}
              disabled={transcribing}
              accessibilityLabel={recording ? 'Stop recording' : 'Start voice input'}
            >
              {transcribing ? (
                <ActivityIndicator color={colors.accent} size="small" />
              ) : (
                <Text style={{ color: colors.accent, fontSize: 16 }}>🎙</Text>
              )}
            </Pressable>
          </Animated.View>
        ) : null}
        {streamingStop ? (
          <Pressable
            style={[styles.send, { backgroundColor: colors.accent }]}
            onPress={onStop}
            accessibilityLabel="Stop generating"
          >
            <Text style={{ color: colors.onAccent, fontSize: 18, fontWeight: '800' }}>■</Text>
          </Pressable>
        ) : (
          <Pressable
            style={[
              styles.send,
              { backgroundColor: colors.accent },
              (!canSend || sending || recording || transcribing) && styles.sendDisabled,
            ]}
            onPress={handleSend}
            disabled={sending || !canSend || recording || transcribing}
            accessibilityLabel="Send message"
          >
            {sending ? (
              <ActivityIndicator color={colors.onAccent} />
            ) : (
              <Text style={{ color: colors.onAccent, fontSize: 20, fontWeight: '800' }}>↑</Text>
            )}
          </Pressable>
        )}
      </View>
      {showDisclaimer ? (
        <Text style={[styles.disclaimer, { color: colors.textDim }]}>
          Linas can make mistakes. Check important details.
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
  },
  row: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 },
  round: {
    width: HIT,
    height: HIT,
    borderRadius: HIT / 2,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  input: {
    flex: 1,
    minHeight: HIT,
    maxHeight: 120,
    borderRadius: radii.lg,
    fontFamily: fonts.body,
    fontSize: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderWidth: 1,
  },
  send: {
    width: HIT,
    height: HIT,
    borderRadius: HIT / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendDisabled: { opacity: 0.45 },
  disclaimer: {
    fontFamily: fonts.body,
    fontSize: 11,
    textAlign: 'center',
    marginTop: 8,
  },
});
