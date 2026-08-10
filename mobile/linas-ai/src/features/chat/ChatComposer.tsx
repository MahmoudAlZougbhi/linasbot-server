import { useEffect, useRef, useState, type RefObject } from 'react';
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
import { formatVoiceElapsed, StopGlyph } from './ComposerGlyphs';
import { LinEffortSheet } from './LinEffortSheet';
import { modelChipLabel, type OwnerChatMode } from './ownerChatMode';
import type { VoiceState } from './useVoiceDraft';
import { VoiceComposerControls } from './VoiceComposerControls';

type Props = {
  draft: string;
  onChangeDraft: (v: string) => void;
  onSend: () => void;
  onPlus?: () => void;
  onToggleVoice?: () => void;
  onResumeVoice?: () => void;
  onConfirmVoice?: () => void;
  onDiscardVoice?: () => void;
  onStop?: () => void;
  sending: boolean;
  canSendWithAttachment?: boolean;
  voiceState?: VoiceState;
  elapsedMs?: number;
  metering?: number | null;
  inputRef?: RefObject<TextInput | null>;
  showPlus?: boolean;
  showMic?: boolean;
  showDisclaimer?: boolean;
  autoFocus?: boolean;
  ownerMode?: OwnerChatMode;
  onOwnerModeChange?: (mode: OwnerChatMode) => void;
  showModelChip?: boolean;
};

/**
 * ChatGPT-style pill: + | TextInput | chip | mic/send in one row.
 * Stacking the field above the toolbar let an empty multiline TextInput collapse
 * to a ~0 hit target (looked like a blank bar / "blocked" composer).
 */
export function ChatComposer({
  draft,
  onChangeDraft,
  onSend,
  onPlus,
  onToggleVoice,
  onResumeVoice,
  onConfirmVoice,
  onDiscardVoice,
  onStop,
  sending,
  canSendWithAttachment = false,
  voiceState = 'idle',
  elapsedMs = 0,
  metering: _metering,
  inputRef,
  showPlus = false,
  showMic = false,
  showDisclaimer = true,
  autoFocus = false,
  ownerMode = 'chat',
  onOwnerModeChange,
  showModelChip = false,
}: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const [effortOpen, setEffortOpen] = useState(false);
  const pulse = useRef(new Animated.Value(1)).current;
  const ring = useRef(new Animated.Value(0.55)).current;
  const recording = voiceState === 'recording';
  const paused = voiceState === 'paused';
  const transcribing = voiceState === 'transcribing';
  const voiceBusy = recording || paused || transcribing;
  const canSend = Boolean(draft.trim() || canSendWithAttachment);
  const streamingStop = Boolean(onStop && sending);
  const showVoiceControl =
    Boolean(showMic && onToggleVoice && !streamingStop && (voiceBusy || !canSend));
  const showSend = streamingStop || (canSend && !paused);
  const chipTappable = Boolean(showModelChip && onOwnerModeChange);

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
    if (sending || !canSend || voiceBusy) return;
    inputRef?.current?.blur();
    Keyboard.dismiss();
    onSend();
  }

  const placeholder = recording
    ? `Listening… ${formatVoiceElapsed(elapsedMs)}`
    : paused
      ? `Paused · ${formatVoiceElapsed(elapsedMs)}`
      : transcribing
        ? 'Transcribing…'
        : 'Message Linas';

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

        <TextInput
          ref={inputRef}
          style={[styles.input, { color: colors.text }]}
          placeholder={placeholder}
          placeholderTextColor={colors.textDim}
          value={draft}
          onChangeText={onChangeDraft}
          multiline
          editable={!voiceBusy}
          autoFocus={autoFocus}
          blurOnSubmit={false}
          accessibilityLabel="Message Linas"
        />

        <View style={styles.trailing}>
          {showModelChip ? (
            <Pressable
              style={[styles.chip, { backgroundColor: colors.surfaceAlt }]}
              onPress={() => {
                if (!chipTappable) return;
                inputRef?.current?.blur();
                Keyboard.dismiss();
                setEffortOpen(true);
              }}
              disabled={!chipTappable}
              accessibilityRole="button"
              accessibilityLabel={modelChipLabel(ownerMode)}
              accessibilityHint={chipTappable ? 'Choose Low or High' : undefined}
            >
              {ownerMode === 'work' ? (
                <Text style={[styles.chipBolt, { color: colors.text }]}>⚡</Text>
              ) : null}
              <Text style={[styles.chipText, { color: colors.text }]} numberOfLines={1}>
                {modelChipLabel(ownerMode)}
              </Text>
            </Pressable>
          ) : null}

          {showVoiceControl ? (
            <VoiceComposerControls
              voiceState={voiceState}
              elapsedMs={elapsedMs}
              pulse={pulse}
              ring={ring}
              onToggleVoice={onToggleVoice}
              onResumeVoice={onResumeVoice}
              onConfirmVoice={onConfirmVoice}
              onDiscardVoice={onDiscardVoice}
              onBeforeStart={() => {
                inputRef?.current?.blur();
                Keyboard.dismiss();
              }}
            />
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
                  (sending || voiceBusy) && styles.sendDisabled,
                ]}
                onPress={handleSend}
                disabled={sending || !canSend || voiceBusy}
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
      {showDisclaimer ? (
        <Text style={[styles.disclaimer, { color: colors.textDim }]}>
          Linas can make mistakes. Check important details.
        </Text>
      ) : null}
      {chipTappable ? (
        <LinEffortSheet
          open={effortOpen}
          mode={ownerMode}
          onClose={() => setEffortOpen(false)}
          onSelect={onOwnerModeChange!}
        />
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
    flexDirection: 'row',
    alignItems: 'flex-end',
    borderRadius: radii.xl + 4,
    borderWidth: StyleSheet.hairlineWidth,
    paddingVertical: 8,
    paddingHorizontal: 8,
    minHeight: 56,
  },
  input: {
    flex: 1,
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: 22,
    minHeight: 36,
    maxHeight: 110,
    paddingHorizontal: 8,
    paddingTop: 8,
    paddingBottom: 8,
  },
  trailing: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flexShrink: 0,
  },
  iconHit: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
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
