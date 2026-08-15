import { ActivityIndicator, Animated, Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, useTheme } from '../../theme';
import {
  CheckGlyph,
  COMPOSER_ACTION_SIZE,
  DiscardGlyph,
  formatVoiceElapsed,
  MicGlyph,
  StopGlyph,
} from './ComposerGlyphs';
import type { VoiceState } from './useVoiceDraft';

type Props = {
  voiceState: VoiceState;
  elapsedMs: number;
  pulse: Animated.Value;
  ring: Animated.Value;
  onToggleVoice?: () => void;
  onResumeVoice?: () => void;
  onConfirmVoice?: () => void;
  onDiscardVoice?: () => void;
  onBeforeStart?: () => void;
};

/** Mic / stop / paused (discard·resume·confirm) cluster for the composer toolbar. */
export function VoiceComposerControls({
  voiceState,
  elapsedMs,
  pulse,
  ring,
  onToggleVoice,
  onResumeVoice,
  onConfirmVoice,
  onDiscardVoice,
  onBeforeStart,
}: Props) {
  const { colors } = useTheme();
  const recording = voiceState === 'recording';
  const paused = voiceState === 'paused';
  const transcribing = voiceState === 'transcribing';

  if (paused) {
    return (
      <View style={styles.pausedRow}>
        <Text style={[styles.timer, { color: colors.textDim }]} accessibilityLabel="Recording length">
          {formatVoiceElapsed(elapsedMs)}
        </Text>
        <Pressable
          style={styles.roundIn}
          onPress={() => onDiscardVoice?.()}
          accessibilityLabel="Discard recording"
          hitSlop={4}
        >
          <DiscardGlyph color={colors.textDim} />
        </Pressable>
        <Pressable
          style={[styles.roundIn, { backgroundColor: colors.surfaceAlt }]}
          onPress={() => onResumeVoice?.()}
          accessibilityLabel="Continue recording"
          hitSlop={4}
        >
          <MicGlyph color={colors.text} />
        </Pressable>
        <Pressable
          style={[styles.roundIn, { backgroundColor: colors.accent }]}
          onPress={() => onConfirmVoice?.()}
          accessibilityLabel="Use recording"
          hitSlop={4}
        >
          <CheckGlyph color={colors.onAccent} />
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.micSlot}>
      {recording ? (
        <>
          <Text
            style={[styles.timerBeside, { color: colors.danger }]}
            accessibilityLabel="Recording length"
          >
            {formatVoiceElapsed(elapsedMs)}
          </Text>
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
        </>
      ) : null}
      <Animated.View style={{ transform: [{ scale: pulse }] }}>
        <Pressable
          style={[styles.roundIn, recording && { backgroundColor: colors.danger }]}
          onPress={() => {
            if (!recording && !transcribing) onBeforeStart?.();
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
            <MicGlyph color={colors.text} size={20} />
          )}
        </Pressable>
      </Animated.View>
    </View>
  );
}

const PULSE_RING = COMPOSER_ACTION_SIZE + 8;

const styles = StyleSheet.create({
  micSlot: {
    minWidth: COMPOSER_ACTION_SIZE,
    height: COMPOSER_ACTION_SIZE,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  pausedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  timer: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    fontVariant: ['tabular-nums'],
    minWidth: 36,
    textAlign: 'right',
    marginRight: 2,
  },
  timerBeside: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    fontVariant: ['tabular-nums'],
    minWidth: 36,
    textAlign: 'right',
  },
  pulseRing: {
    position: 'absolute',
    right: -4,
    width: PULSE_RING,
    height: PULSE_RING,
    borderRadius: PULSE_RING / 2,
    borderWidth: 2,
  },
  roundIn: {
    width: COMPOSER_ACTION_SIZE,
    height: COMPOSER_ACTION_SIZE,
    borderRadius: COMPOSER_ACTION_SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
