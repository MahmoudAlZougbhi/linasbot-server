import { useEffect, useRef, useState, type RefObject } from 'react';
import {
  ActivityIndicator,
  Animated,
  Keyboard,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { textDirectionStyle } from '../../lib/textDirection';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { formatVoiceElapsed, StopGlyph } from './ComposerGlyphs';
import { LinEffortSheet } from './LinEffortSheet';
import { OWNER_LIN_DISPLAY, type OwnerChatMode } from './ownerChatMode';
import type { VoiceState } from './useVoiceDraft';
import { VoiceComposerControls } from './VoiceComposerControls';

/** Keep a real tap target; grow modestly like ChatGPT (≈4 lines). */
const INPUT_MIN_H = 36;
const INPUT_MAX_H = 88;

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
 * to a near-zero hit target (blank bar / “blocked” composer next to the Ok bubble).
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
  const { tr } = useI18n();
  const [effortOpen, setEffortOpen] = useState(false);
  const [inputHeight, setInputHeight] = useState(INPUT_MIN_H);
  const pulse = useRef(new Animated.Value(1)).current;
  const ring = useRef(new Animated.Value(0.55)).current;
  /** After Send, block one-shot autofocus / remount races from reopening the keyboard. */
  const suppressFocusRef = useRef(false);
  const recording = voiceState === 'recording';
  const paused = voiceState === 'paused';
  const transcribing = voiceState === 'transcribing';
  const voiceBusy = recording || paused || transcribing;
  const canSend = Boolean(draft.trim() || canSendWithAttachment);
  const streamingStop = Boolean(onStop && sending);
  // Keep mic available with typed draft so voice can append (not replace).
  const showVoiceControl = Boolean(showMic && onToggleVoice && !streamingStop);
  const showSend = streamingStop || (canSend && !voiceBusy);
  const chipTappable = Boolean(showModelChip && onOwnerModeChange);
  const chipLabel = `${OWNER_LIN_DISPLAY} ${
    ownerMode === 'work' ? tr('linEffortHigh') : tr('linEffortLow')
  }`;
  const draftDir = textDirectionStyle(draft);

  function dismissKeyboard() {
    inputRef?.current?.blur();
    Keyboard.dismiss();
  }

  useEffect(() => {
    if (!draft.trim()) setInputHeight(INPUT_MIN_H);
  }, [draft]);

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

  // One-shot open focus (ChatGPT-style). Avoid native autoFocus — draft-clear
  // height shrink on Send can re-open the keyboard if the field stays focused.
  useEffect(() => {
    if (!autoFocus || suppressFocusRef.current) return;
    const t = setTimeout(() => {
      if (suppressFocusRef.current) return;
      inputRef?.current?.focus();
    }, 120);
    return () => clearTimeout(t);
  }, [autoFocus, inputRef]);

  function handleSend() {
    if (sending || !canSend || voiceBusy) return;
    suppressFocusRef.current = true;
    dismissKeyboard();
    onSend();
    // Draft clear + inputHeight shrink re-layout can leave the field focused.
    requestAnimationFrame(dismissKeyboard);
    setTimeout(dismissKeyboard, 80);
  }

  const placeholder = recording
    ? `${tr('composerListening')} ${formatVoiceElapsed(elapsedMs)}`
    : paused
      ? `${tr('composerPaused')} · ${formatVoiceElapsed(elapsedMs)}`
      : transcribing
        ? tr('composerTranscribing')
        : tr('composerPlaceholder');

  return (
    <View
      style={[
        styles.wrap,
        {
          paddingBottom: Math.max(insets.bottom, 10),
          // Match chat canvas — no elevated/green chrome slab above the pill.
          backgroundColor: colors.bg,
        },
      ]}
    >
      <View
        style={[
          styles.pill,
          {
            backgroundColor: colors.surface,
            borderColor: colors.border,
          },
        ]}
      >
        {showPlus && onPlus ? (
          <Pressable
            style={styles.iconHit}
            onPress={onPlus}
            accessibilityLabel={tr('composerMoreActions')}
            hitSlop={6}
          >
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '500', lineHeight: 22 }}>
              +
            </Text>
          </Pressable>
        ) : (
          <View style={styles.iconHit} />
        )}

        <TextInput
          ref={inputRef}
          style={[styles.input, { color: colors.text, height: inputHeight }, draftDir]}
          placeholder={placeholder}
          placeholderTextColor={colors.textDim}
          value={draft}
          onChangeText={onChangeDraft}
          onContentSizeChange={(e) => {
            const next = Math.ceil(e.nativeEvent.contentSize.height);
            setInputHeight(Math.min(INPUT_MAX_H, Math.max(INPUT_MIN_H, next)));
          }}
          multiline
          scrollEnabled={inputHeight >= INPUT_MAX_H}
          editable={!voiceBusy}
          autoFocus={false}
          blurOnSubmit={false}
          textAlign={draftDir.textAlign}
          textAlignVertical={Platform.OS === 'android' ? 'center' : undefined}
          accessibilityLabel={tr('composerPlaceholder')}
        />

        <View style={styles.trailing}>
          {showModelChip ? (
            <Pressable
              style={[styles.chip, { backgroundColor: colors.surfaceAlt }]}
              onPress={() => {
                if (!chipTappable) return;
                dismissKeyboard();
                setEffortOpen(true);
              }}
              disabled={!chipTappable}
              accessibilityRole="button"
              accessibilityLabel={chipLabel}
              accessibilityHint={chipTappable ? tr('composerChooseEffort') : undefined}
            >
              {ownerMode === 'work' ? (
                <Text style={[styles.chipBolt, { color: colors.text }]}>⚡</Text>
              ) : null}
              <Text style={[styles.chipText, { color: colors.text }]} numberOfLines={1}>
                {chipLabel}
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
              onBeforeStart={dismissKeyboard}
            />
          ) : null}

          {showSend ? (
            streamingStop ? (
              <Pressable
                style={[styles.sendIn, { backgroundColor: colors.accent }]}
                onPress={onStop}
                accessibilityLabel={tr('composerStop')}
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
                accessibilityLabel={tr('composerSend')}
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
          {tr('composerDisclaimer')}
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
    paddingVertical: 6,
    paddingHorizontal: 8,
    minHeight: 48,
  },
  input: {
    flex: 1,
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: 22,
    paddingHorizontal: 8,
    paddingVertical: 0,
  },
  trailing: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flexShrink: 0,
  },
  iconHit: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radii.pill,
    maxWidth: 160,
  },
  chipBolt: { fontSize: 12 },
  chipText: {
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
  },
  sendIn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendDisabled: { opacity: 0.45 },
  disclaimer: {
    fontFamily: fonts.body,
    fontSize: 11,
    textAlign: 'center',
    marginTop: 6,
  },
});
