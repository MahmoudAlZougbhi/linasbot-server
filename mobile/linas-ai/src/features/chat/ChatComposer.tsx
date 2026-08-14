import { useEffect, useRef, useState, type RefObject } from 'react';
import {
  ActivityIndicator,
  Animated,
  Keyboard,
  Platform,
  Pressable,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { textDirectionStyle } from '../../lib/textDirection';
import { useI18n } from '../../i18n/LanguageContext';
import { useTheme } from '../../theme';
import { ComposerEditChip } from './ComposerEditChip';
import {
  formatVoiceElapsed,
  PlusCircleGlyph,
  SendArrowGlyph,
  StopGlyph,
} from './ComposerGlyphs';
import { ComposerModelChip } from './ComposerModelChip';
import { composerStyles as styles } from './composerStyles';
import { LinEffortSheet } from './LinEffortSheet';
import type { OwnerChatMode } from './ownerChatMode';
import {
  useComposerInputAutoGrow,
  COMPOSER_INPUT_MIN_H,
  COMPOSER_IOS_PAD_TOP,
} from './useComposerInputAutoGrow';
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
  editChipActive?: boolean;
  onClearEditChip?: () => void;
};

/**
 * Design handoff composer: model chip above right, white pill (+ | input | mic | send).
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
  editChipActive = false,
  onClearEditChip,
}: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { tr } = useI18n();
  const [effortOpen, setEffortOpen] = useState(false);
  const pulse = useRef(new Animated.Value(1)).current;
  const ring = useRef(new Animated.Value(0.55)).current;
  const suppressFocusRef = useRef(false);
  const {
    inputHeight,
    atMaxHeight,
    localInputRef,
    assignInputRef,
    handleContentSizeChange,
    handleChangeText,
  } = useComposerInputAutoGrow(draft, inputRef);
  const recording = voiceState === 'recording';
  const paused = voiceState === 'paused';
  const transcribing = voiceState === 'transcribing';
  const voiceBusy = recording || paused || transcribing;
  const canSend = Boolean(draft.trim() || canSendWithAttachment);
  const streamingStop = Boolean(onStop && sending);
  const showVoiceControl = Boolean(showMic && onToggleVoice && !streamingStop);
  const chipTappable = Boolean(showModelChip && onOwnerModeChange);
  const draftDir = textDirectionStyle(draft);
  const draftEmpty = !draft.trim();
  const singleLine = inputHeight <= COMPOSER_INPUT_MIN_H;
  const inputTextAlign = draftEmpty ? 'left' : draftDir.textAlign;

  function dismissKeyboard() {
    localInputRef.current?.blur();
    Keyboard.dismiss();
  }

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
    if (!autoFocus || suppressFocusRef.current) return;
    const t = setTimeout(() => {
      if (suppressFocusRef.current) return;
      localInputRef.current?.focus();
    }, 120);
    return () => clearTimeout(t);
  }, [autoFocus]);

  function handleSend() {
    if (sending || !canSend || voiceBusy) return;
    suppressFocusRef.current = true;
    dismissKeyboard();
    onSend();
    requestAnimationFrame(dismissKeyboard);
    setTimeout(dismissKeyboard, 80);
  }

  const idlePlaceholder =
    ownerMode === 'work' ? tr('composerPlaceholderWork') : tr('composerPlaceholderChat');
  const placeholder = recording
    ? `${tr('composerListening')} ${formatVoiceElapsed(elapsedMs)}`
    : paused
      ? `${tr('composerPaused')} · ${formatVoiceElapsed(elapsedMs)}`
      : transcribing
        ? tr('composerTranscribing')
        : idlePlaceholder;

  const sendBtn = streamingStop ? (
    <Pressable
      style={[styles.sendInside, { backgroundColor: colors.accentDeep }]}
      onPress={onStop}
      accessibilityLabel={tr('composerStop')}
    >
      <StopGlyph color={colors.onAccent} />
    </Pressable>
  ) : (
    <Pressable
      style={[
        styles.sendInside,
        { backgroundColor: colors.accentDeep },
        sending && styles.sendBusy,
      ]}
      onPress={handleSend}
      disabled={sending || !canSend || voiceBusy}
      accessibilityLabel={tr('composerSend')}
    >
      {sending ? (
        <ActivityIndicator color={colors.onAccent} size="small" />
      ) : (
        <SendArrowGlyph color={colors.onAccent} size={18} />
      )}
    </Pressable>
  );

  return (
    <View
      style={[
        styles.wrap,
        {
          paddingBottom: Math.max(insets.bottom, 10),
          backgroundColor: colors.bg,
        },
      ]}
    >
      <ComposerEditChip active={Boolean(editChipActive)} onClear={onClearEditChip} />

      {showModelChip ? (
        <ComposerModelChip
          mode={ownerMode}
          tappable={chipTappable}
          open={effortOpen}
          onOpen={() => {
            dismissKeyboard();
            setEffortOpen(true);
          }}
        />
      ) : null}

      <View
        style={[
          styles.pill,
          singleLine ? styles.pillSingle : styles.pillGrow,
          {
            backgroundColor: colors.surface,
            shadowColor: colors.text,
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
            <PlusCircleGlyph
              color={colors.text}
              backgroundColor={colors.featuredIconBg}
              borderColor={colors.featuredIconBorder}
            />
          </Pressable>
        ) : null}

        <View style={styles.inputSlot}>
          {draftEmpty ? (
            <View pointerEvents="none" style={styles.placeholderWrap}>
              <Text style={[styles.placeholderText, { color: colors.textDim }]}>
                {placeholder}
              </Text>
            </View>
          ) : null}
          <TextInput
            ref={assignInputRef}
            style={[
              styles.input,
              {
                color: colors.text,
                height: inputHeight,
                textAlign: inputTextAlign,
                writingDirection: draftEmpty ? 'ltr' : draftDir.writingDirection,
                paddingTop: Platform.OS === 'ios' && singleLine ? COMPOSER_IOS_PAD_TOP : 0,
              },
            ]}
            placeholder=""
            value={draft}
            onChangeText={(v) => handleChangeText(v, onChangeDraft)}
            onContentSizeChange={(e) => {
              let h = e.nativeEvent.contentSize.height;
              if (Platform.OS === 'ios' && singleLine) h -= COMPOSER_IOS_PAD_TOP;
              handleContentSizeChange(h);
            }}
            multiline
            scrollEnabled={atMaxHeight}
            editable={!voiceBusy}
            autoFocus={false}
            blurOnSubmit={false}
            textAlignVertical={singleLine ? 'center' : 'top'}
            accessibilityLabel={idlePlaceholder}
          />
        </View>

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

        {sendBtn}
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
