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

import { fonts, radii, spacing, useTheme } from '../../theme';
import { modelChipLabel, type OwnerChatMode } from './ownerChatMode';
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
  showPlus?: boolean;
  showMic?: boolean;
  showDisclaimer?: boolean;
  autoFocus?: boolean;
  ownerMode?: OwnerChatMode;
  showModelChip?: boolean;
};

function MicGlyph({ color, size = 20 }: { color: string; size?: number }) {
  const headW = size * 0.38;
  const headH = size * 0.52;
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <View
        style={{
          width: headW,
          height: headH,
          borderRadius: headW / 2,
          borderWidth: 2,
          borderColor: color,
          backgroundColor: 'transparent',
        }}
      />
      <View
        style={{
          position: 'absolute',
          bottom: size * 0.18,
          width: size * 0.55,
          height: size * 0.28,
          borderWidth: 2,
          borderTopWidth: 0,
          borderColor: color,
          borderBottomLeftRadius: size * 0.28,
          borderBottomRightRadius: size * 0.28,
        }}
      />
      <View
        style={{
          position: 'absolute',
          bottom: size * 0.08,
          width: 2,
          height: size * 0.14,
          backgroundColor: color,
          borderRadius: 1,
        }}
      />
      <View
        style={{
          position: 'absolute',
          bottom: size * 0.06,
          width: size * 0.28,
          height: 2,
          backgroundColor: color,
          borderRadius: 1,
        }}
      />
    </View>
  );
}

function StopGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: 12, height: 12, borderRadius: 2.5, backgroundColor: color }} />
  );
}

/** Pill composer: + / chip / mic / send|stop all inside the bar. */
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
  ownerMode = 'chat',
  showModelChip = false,
}: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const pulse = useRef(new Animated.Value(1)).current;
  const ring = useRef(new Animated.Value(0.55)).current;
  const recording = voiceState === 'recording';
  const transcribing = voiceState === 'transcribing';
  const canSend = Boolean(draft.trim() || canSendWithAttachment);
  const streamingStop = Boolean(onStop && sending);
  const showVoiceControl =
    Boolean(showMic && onToggleVoice && !streamingStop && (recording || transcribing || !canSend));
  const showSend = streamingStop || canSend;

  useEffect(() => {
    if (!recording) {
      pulse.setValue(1);
      ring.setValue(0.55);
      return;
    }
    const scaleLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1.06, duration: 480, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 480, useNativeDriver: true }),
      ]),
    );
    const ringLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(ring, { toValue: 1, duration: 700, useNativeDriver: true }),
        Animated.timing(ring, { toValue: 0.4, duration: 700, useNativeDriver: true }),
      ]),
    );
    scaleLoop.start();
    ringLoop.start();
    return () => {
      scaleLoop.stop();
      ringLoop.stop();
    };
  }, [recording, pulse, ring]);

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
          backgroundColor: colors.bgElevated,
        },
      ]}
    >
      <View
        style={[
          styles.pill,
          {
            backgroundColor: colors.bgElevated,
            borderColor: colors.border,
          },
        ]}
      >
        <TextInput
          ref={inputRef}
          style={[styles.input, { color: colors.text }]}
          placeholder={recording ? 'Listening…' : transcribing ? 'Transcribing…' : 'Message Linas'}
          placeholderTextColor={colors.textDim}
          value={draft}
          onChangeText={onChangeDraft}
          multiline
          editable={!recording && !transcribing}
          autoFocus={autoFocus}
          blurOnSubmit={false}
          accessibilityLabel="Message Linas"
        />
        <View style={styles.toolbar}>
          {showPlus && onPlus ? (
            <Pressable
              style={styles.iconHit}
              onPress={onPlus}
              accessibilityLabel="More actions"
              hitSlop={6}
            >
              <Text style={{ color: colors.text, fontSize: 22, fontWeight: '500', lineHeight: 24 }}>
                +
              </Text>
            </Pressable>
          ) : (
            <View style={styles.iconHit} />
          )}

          <View style={styles.toolbarRight}>
            {showModelChip ? (
              <View
                style={[styles.chip, { backgroundColor: colors.surfaceAlt }]}
                accessibilityLabel={modelChipLabel(ownerMode)}
              >
                <Text style={[styles.chipBolt, { color: colors.text }]}>⚡</Text>
                <Text style={[styles.chipText, { color: colors.text }]} numberOfLines={1}>
                  {modelChipLabel(ownerMode)}
                </Text>
              </View>
            ) : null}

            {showVoiceControl ? (
              <View style={styles.micSlot}>
                {recording ? (
                  <Animated.View
                    pointerEvents="none"
                    style={[
                      styles.pulseRing,
                      {
                        borderColor: colors.danger,
                        opacity: ring,
                        transform: [{ scale: pulse }],
                      },
                    ]}
                  />
                ) : null}
                <Animated.View style={{ transform: [{ scale: pulse }] }}>
                  <Pressable
                    style={[styles.roundIn, recording && { backgroundColor: colors.danger }]}
                    onPress={() => {
                      if (!recording && !transcribing) {
                        inputRef?.current?.blur();
                        Keyboard.dismiss();
                      }
                      onToggleVoice?.();
                    }}
                    disabled={transcribing}
                    accessibilityLabel={
                      recording ? 'Stop recording' : transcribing ? 'Transcribing' : 'Start voice input'
                    }
                  >
                    {transcribing ? (
                      <ActivityIndicator color={colors.accent} size="small" />
                    ) : recording ? (
                      <StopGlyph color="#FFFFFF" />
                    ) : (
                      <MicGlyph color={colors.text} />
                    )}
                  </Pressable>
                </Animated.View>
              </View>
            ) : null}

            {showSend ? (
              streamingStop ? (
                <Pressable
                  style={[styles.sendIn, { backgroundColor: colors.accent }]}
                  onPress={onStop}
                  accessibilityLabel="Stop generating"
                >
                  <StopGlyph color={colors.onAccent} />
                </Pressable>
              ) : (
                <Pressable
                  style={[
                    styles.sendIn,
                    { backgroundColor: colors.accent },
                    (sending || recording || transcribing) && styles.sendDisabled,
                  ]}
                  onPress={handleSend}
                  disabled={sending || !canSend || recording || transcribing}
                  accessibilityLabel="Send message"
                >
                  {sending ? (
                    <ActivityIndicator color={colors.onAccent} />
                  ) : (
                    <Text style={{ color: colors.onAccent, fontSize: 18, fontWeight: '800' }}>↑</Text>
                  )}
                </Pressable>
              )
            ) : null}
          </View>
        </View>
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
    paddingTop: spacing.sm,
  },
  pill: {
    borderRadius: radii.xl + 4,
    borderWidth: StyleSheet.hairlineWidth,
    paddingTop: 10,
    paddingBottom: 8,
    paddingHorizontal: 10,
    minHeight: 56,
  },
  input: {
    fontFamily: fonts.body,
    fontSize: 16,
    minHeight: 24,
    maxHeight: 110,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 4,
    minHeight: 36,
  },
  toolbarRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flexShrink: 1,
  },
  iconHit: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radii.pill,
    maxWidth: 160,
  },
  chipBolt: { fontSize: 12 },
  chipText: {
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
  },
  micSlot: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pulseRing: {
    position: 'absolute',
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 2,
  },
  roundIn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendIn: {
    width: 34,
    height: 34,
    borderRadius: 17,
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
