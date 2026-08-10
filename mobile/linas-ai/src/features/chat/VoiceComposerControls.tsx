import { ActivityIndicator, Animated, Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, useTheme } from '../../theme';
import {
  CheckGlyph,
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
            <MicGlyph color={colors.text} />
          )}
        </Pressable>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  micSlot: {
    minWidth: 36,
    height: 36,
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
});
